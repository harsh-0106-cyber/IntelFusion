"""
indexer.py — Persistent Local Image Indexing Service for ZLens

Provides transactional single-asset and batch indexing, SHA-256 duplicate detection,
perceptual hash storage, provenance tracking via asset_sources, and paginated query APIs.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

from zlens.database import DatabaseManager, DEFAULT_DB_PATH
from zlens.preprocessor import ImagePreprocessor, PreprocessedImage, ImageValidationError

logger = logging.getLogger("zlens.indexer")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class IndexResult:
    """Outcome of indexing a single image asset."""
    status: str            # 'indexed', 'duplicate', or 'error'
    asset_id: Optional[int] = None
    image_sha256: Optional[str] = None
    is_duplicate: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "asset_id": self.asset_id,
            "image_sha256": self.image_sha256,
            "is_duplicate": self.is_duplicate,
            "error_message": self.error_message,
        }


@dataclass
class BatchIndexReport:
    """Summary of a batch indexing operation."""
    total_files_discovered: int = 0
    indexed_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    duration_seconds: float = 0.0
    error_details: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files_discovered": self.total_files_discovered,
            "indexed_count": self.indexed_count,
            "duplicate_count": self.duplicate_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "duration_seconds": round(self.duration_seconds, 3),
            "error_details": self.error_details[:50],  # Cap reported error sample
        }


class PathSecurityError(ValueError):
    """Raised when an indexing request specifies an unapproved or traversing path."""
    pass


def validate_permitted_path(target_path: str, allowed_base_dir: str) -> str:
    """
    Ensures target_path resolves strictly within allowed_base_dir.
    Prevents path traversal and access to arbitrary server directories.
    """
    if not target_path or not allowed_base_dir:
        raise PathSecurityError("Target path and base directory must both be specified.")

    norm_base = os.path.realpath(os.path.abspath(allowed_base_dir))
    norm_target = os.path.realpath(os.path.abspath(target_path))

    # Common prefix check ensuring norm_target starts with norm_base
    if not norm_target.startswith(norm_base):
        raise PathSecurityError(
            f"Access denied: '{target_path}' is outside permitted directory '{allowed_base_dir}'."
        )

    if not os.path.exists(norm_target):
        raise PathSecurityError(f"Directory not found: '{target_path}'.")

    if not os.path.isdir(norm_target):
        raise PathSecurityError(f"Target path is not a directory: '{target_path}'.")

    return norm_target


class ZLensIndexer:
    """
    Service for persistent image asset indexing and metadata management.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        preprocessor: Optional[ImagePreprocessor] = None,
    ):
        self.db = db or DatabaseManager()
        self.preprocessor = preprocessor or ImagePreprocessor()

    # ──────────────────────────────────────────────────────────────────────────
    # Single Asset Indexing
    # ──────────────────────────────────────────────────────────────────────────

    def index_image(
        self,
        image_bytes: bytes,
        source_type: str = "local_upload",
        source_name: Optional[str] = None,
        source_page_url: Optional[str] = None,
        source_image_url: Optional[str] = None,
    ) -> IndexResult:
        """
        Validates, sanitizes, and indexes an image asset into SQLite.
        Detects existing SHA-256 duplicates idempotently and preserves provenance.
        """
        try:
            preprocessed = self.preprocessor.preprocess(image_bytes)
        except ImageValidationError as e:
            logger.warning("Image validation rejected during indexing: %s (%s)", e.message, e.code)
            return IndexResult(status="error", error_message=e.message)
        except Exception as e:
            logger.exception("Unexpected error preprocessing image for indexing")
            return IndexResult(status="error", error_message=f"Preprocessing failed: {str(e)}")

        now_utc = datetime.now(timezone.utc).isoformat()

        # Atomic transaction: check duplicate or insert
        with self.db.transaction() as conn:
            cursor = conn.cursor()

            # 1. Check for existing asset by SHA-256
            cursor.execute("SELECT id FROM assets WHERE image_sha256 = ?", (preprocessed.sha256,))
            existing = cursor.fetchone()

            if existing:
                asset_id = existing["id"]
                # Record new provenance source if distinct
                self._record_source_if_new(
                    cursor,
                    asset_id=asset_id,
                    source_type=source_type,
                    source_name=source_name,
                    source_page_url=source_page_url,
                    source_image_url=source_image_url,
                    discovered_at=now_utc,
                )
                return IndexResult(
                    status="duplicate",
                    asset_id=asset_id,
                    image_sha256=preprocessed.sha256,
                    is_duplicate=True,
                )

            # 2. Insert new asset
            cursor.execute(
                """
                INSERT INTO assets (
                    image_sha256, dhash, ahash, phash,
                    width, height, aspect_ratio, format,
                    file_size_bytes, created_at, indexed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
                """,
                (
                    preprocessed.sha256,
                    preprocessed.dhash,
                    preprocessed.ahash,
                    preprocessed.phash,
                    preprocessed.width,
                    preprocessed.height,
                    preprocessed.aspect_ratio,
                    preprocessed.format,
                    len(preprocessed.sanitized_bytes),
                    now_utc,
                    now_utc,
                ),
            )
            asset_id = cursor.lastrowid

            # 3. Insert initial provenance source
            self._insert_source(
                cursor,
                asset_id=asset_id,
                source_type=source_type,
                source_name=source_name,
                source_page_url=source_page_url,
                source_image_url=source_image_url,
                discovered_at=now_utc,
            )

            return IndexResult(
                status="indexed",
                asset_id=asset_id,
                image_sha256=preprocessed.sha256,
                is_duplicate=False,
            )

    def _insert_source(
        self,
        cursor,
        asset_id: int,
        source_type: str,
        source_name: Optional[str],
        source_page_url: Optional[str],
        source_image_url: Optional[str],
        discovered_at: str,
    ) -> None:
        """Inserts an asset source record into asset_sources table."""
        cursor.execute(
            """
            INSERT INTO asset_sources (
                asset_id, source_type, source_name,
                source_page_url, source_image_url, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                source_type,
                source_name,
                source_page_url,
                source_image_url,
                discovered_at,
            ),
        )

    def _record_source_if_new(
        self,
        cursor,
        asset_id: int,
        source_type: str,
        source_name: Optional[str],
        source_page_url: Optional[str],
        source_image_url: Optional[str],
        discovered_at: str,
    ) -> None:
        """Inserts an asset source if an identical source record does not already exist."""
        cursor.execute(
            """
            SELECT id FROM asset_sources 
            WHERE asset_id = ? 
              AND (source_page_url = ? OR (source_page_url IS NULL AND ? IS NULL))
              AND (source_type = ?)
            """,
            (asset_id, source_page_url, source_page_url, source_type),
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO asset_sources (
                    asset_id, source_type, source_name,
                    source_page_url, source_image_url, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    source_type,
                    source_name,
                    source_page_url,
                    source_image_url,
                    discovered_at,
                ),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Batch Directory Indexing
    # ──────────────────────────────────────────────────────────────────────────

    def index_directory(
        self,
        directory_path: str,
        source_name: str = "permitted_dataset",
        recursive: bool = True,
    ) -> BatchIndexReport:
        """
        Recursively scans and indexes supported images from a local directory.
        Operates incrementally and avoids loading the entire dataset into memory.
        """
        start_time = time.time()
        report = BatchIndexReport()

        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            report.error_count += 1
            report.error_details.append({
                "file": directory_path,
                "error": "Directory does not exist or is not a directory.",
            })
            report.duration_seconds = time.time() - start_time
            return report

        # Walk directory
        for root, _, files in os.walk(directory_path):
            for file_name in files:
                ext = os.path.splitext(file_name)[1].lower()
                full_path = os.path.join(root, file_name)

                if ext not in SUPPORTED_EXTENSIONS:
                    report.skipped_count += 1
                    continue

                report.total_files_discovered += 1

                try:
                    # Stream one file at a time
                    with open(full_path, "rb") as f:
                        file_bytes = f.read()

                    rel_path = os.path.relpath(full_path, directory_path).replace("\\", "/")

                    result = self.index_image(
                        image_bytes=file_bytes,
                        source_type="permitted_dataset",
                        source_name=source_name,
                        source_page_url=rel_path,
                        source_image_url=None,
                    )

                    if result.status == "indexed":
                        report.indexed_count += 1
                    elif result.status == "duplicate":
                        report.duplicate_count += 1
                    else:
                        report.error_count += 1
                        report.error_details.append({
                            "file": rel_path,
                            "error": result.error_message or "Unknown indexing error",
                        })

                except Exception as e:
                    logger.warning("Failed to index file %s: %s", file_name, e)
                    report.error_count += 1
                    report.error_details.append({
                        "file": file_name,
                        "error": str(e),
                    })

            if not recursive:
                break

        report.duration_seconds = time.time() - start_time
        return report

    # ──────────────────────────────────────────────────────────────────────────
    # Statistics and Paginated Retrieval
    # ──────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """
        Returns real database counts and status without exposing sensitive metadata.
        """
        with self.db.connection() as conn:
            # Asset count
            total_assets = conn.execute("SELECT COUNT(*) as count FROM assets").fetchone()["count"]

            # Source count
            total_sources = conn.execute("SELECT COUNT(*) as count FROM asset_sources").fetchone()["count"]

            # Format distribution
            format_rows = conn.execute(
                "SELECT format, COUNT(*) as count FROM assets GROUP BY format"
            ).fetchall()
            formats_breakdown = {row["format"]: row["count"] for row in format_rows}

            # Last indexed timestamp
            last_indexed_row = conn.execute(
                "SELECT MAX(indexed_at) as last_indexed FROM assets"
            ).fetchone()
            last_indexed = last_indexed_row["last_indexed"] if last_indexed_row else None

        db_size_bytes = 0
        if os.path.exists(self.db.db_path):
            try:
                db_size_bytes = os.path.getsize(self.db.db_path)
            except Exception:
                pass

        return {
            "status": "operational",
            "total_assets": total_assets,
            "total_sources": total_sources,
            "formats_breakdown": formats_breakdown,
            "last_indexed_at": last_indexed,
            "db_path": os.path.basename(self.db.db_path),  # Only expose filename, not full host path
            "db_size_bytes": db_size_bytes,
        }

    def get_assets(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """
        Returns a paginated list of indexed assets with attached provenance.
        Never exposes raw image bytes or absolute host filesystem paths.
        """
        limit = max(1, min(100, int(limit)))
        offset = max(0, int(offset))

        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, image_sha256, dhash, ahash, phash,
                       width, height, aspect_ratio, format,
                       file_size_bytes, indexed_at, status
                FROM assets
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            asset_rows = cursor.fetchall()

            results = []
            for a in asset_rows:
                asset_id = a["id"]
                # Fetch sources for this asset
                sources_cursor = conn.execute(
                    """
                    SELECT source_type, source_name, source_page_url, discovered_at
                    FROM asset_sources
                    WHERE asset_id = ?
                    ORDER BY id ASC
                    """,
                    (asset_id,),
                )
                sources = [dict(s) for s in sources_cursor.fetchall()]

                results.append({
                    "id": a["id"],
                    "image_sha256": a["image_sha256"],
                    "dhash": a["dhash"],
                    "ahash": a["ahash"],
                    "phash": a["phash"],
                    "width": a["width"],
                    "height": a["height"],
                    "aspect_ratio": a["aspect_ratio"],
                    "format": a["format"],
                    "file_size_bytes": a["file_size_bytes"],
                    "indexed_at": a["indexed_at"],
                    "status": a["status"],
                    "sources": sources,
                })

            return results

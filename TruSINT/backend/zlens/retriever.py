"""
retriever.py — ZLens Exact and Near-Duplicate Visual Image Retrieval Service

Performs genuine reverse-image search against the persistent local SQLite asset index:
1. Exact-match retrieval via bitwise SHA-256 equality.
2. Near-duplicate retrieval via deterministic pHash and dHash Hamming distance comparisons.
3. Candidate deduplication, precedence ranking, and source provenance attachment.
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

from zlens.database import DatabaseManager
from zlens.preprocessor import ImagePreprocessor, PreprocessedImage, ImageValidationError

logger = logging.getLogger("zlens.retriever")


class HashFormatError(ValueError):
    """Raised when a hash is invalid in length, format, or character set."""
    pass


def validate_hex_hash(hash_str: str, expected_length: int = 16) -> str:
    """
    Validates that a hash is a non-empty string of valid hexadecimal characters
    matching the expected length.
    """
    if not isinstance(hash_str, str):
        raise HashFormatError(f"Hash must be a string, got {type(hash_str).__name__}")
    
    clean = hash_str.strip().lower()
    if len(clean) != expected_length:
        raise HashFormatError(
            f"Invalid hash length: expected {expected_length} characters, got {len(clean)} ('{hash_str}')"
        )
    
    try:
        int(clean, 16)
    except ValueError as e:
        raise HashFormatError(f"Invalid hexadecimal string: '{hash_str}'") from e
    
    return clean


def calculate_hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculates the bitwise Hamming distance between two hexadecimal hash strings.
    Validates format, ensures consistent bit ordering, and returns the exact integer count
    of differing bits.

    Smaller Hamming distances generally indicate more perceptually similar hashes.
    A distance of 0 denotes identical perceptual hashes.
    """
    clean1 = validate_hex_hash(hash1)
    clean2 = validate_hex_hash(hash2)

    val1 = int(clean1, 16)
    val2 = int(clean2, 16)
    xor_val = val1 ^ val2
    return bin(xor_val).count("1")


@dataclass
class LocalSearchResult:
    """Structured result of a visual search against the local SQLite index."""
    status: str                         # 'matches_found', 'no_matches', 'index_empty', 'database_error'
    message: str
    total_indexed_assets: int = 0
    candidates_examined: int = 0
    exact_matches_count: int = 0
    near_duplicates_count: int = 0
    duration_seconds: float = 0.0
    matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "total_indexed_assets": self.total_indexed_assets,
            "candidates_examined": self.candidates_examined,
            "exact_matches_count": self.exact_matches_count,
            "near_duplicates_count": self.near_duplicates_count,
            "duration_seconds": round(self.duration_seconds, 4),
            "matches": self.matches,
        }


class ZLensRetriever:
    """
    Dedicated local visual retrieval service for exact SHA-256 and near-duplicate pHash/dHash searches.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        preprocessor: Optional[ImagePreprocessor] = None,
        strong_phash_threshold: int = 6,
        strong_dhash_threshold: int = 4,
        weak_phash_threshold: int = 8,
        weak_dhash_threshold: int = 8,
        permitted_dataset_dir: Optional[str] = None,
    ):
        self.db = db or DatabaseManager()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.strong_phash_threshold = strong_phash_threshold
        self.strong_dhash_threshold = strong_dhash_threshold
        self.weak_phash_threshold = weak_phash_threshold
        self.weak_dhash_threshold = weak_dhash_threshold
        self.permitted_dataset_dir = permitted_dataset_dir or os.getenv(
            "ZLENS_PERMITTED_DATASET_DIR",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "permitted_dataset")),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Exact-Match Retrieval
    # ──────────────────────────────────────────────────────────────────────────

    def find_exact_matches(self, query_sha256: str) -> list[dict[str, Any]]:
        """
        Queries SQLite for assets with the identical SHA-256 hash.
        Treats SHA-256 equality strictly as an exact byte match.
        """
        clean_sha = query_sha256.strip().lower()
        query_sql = """
            SELECT id, image_sha256, dhash, ahash, phash,
                   width, height, aspect_ratio, format,
                   file_size_bytes, indexed_at, status
            FROM assets
            WHERE image_sha256 = ?
        """
        rows = self.db.execute_query(query_sql, (clean_sha,))
        results = []
        for r in rows:
            asset_dict = dict(r)
            sources = self._get_asset_sources(asset_dict["id"])
            primary_source = sources[0] if sources else {}

            results.append({
                "asset_id": asset_dict["id"],
                "match_type": "exact_duplicate",
                "exact_match": True,
                "score_type": "sha256",
                "raw_similarity_score": 1.0,
                "display_score": "Exact File Byte Match (SHA-256)",
                "phash_distance": 0,
                "dhash_distance": 0,
                "retrieval_method": "exact_sha256",
                "verification_status": "source_verified",
                "badge_class": "match-high",
                "source_type": primary_source.get("source_type", "local_index"),
                "source_name": primary_source.get("source_name", "Indexed Asset"),
                "source_page_url": primary_source.get("source_page_url"),
                "sources": sources,
                "width": asset_dict["width"],
                "height": asset_dict["height"],
                "format": asset_dict["format"],
                "file_size_bytes": asset_dict["file_size_bytes"],
                "indexed_at": asset_dict["indexed_at"],
                "preview_url": f"/api/zlens/assets/{asset_dict['id']}/preview",
            })
        return results

    # ──────────────────────────────────────────────────────────────────────────
    # Near-Duplicate Retrieval
    # ──────────────────────────────────────────────────────────────────────────

    def find_near_duplicates(
        self,
        query_phash: str,
        query_dhash: str,
        exclude_asset_ids: set[int] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Performs near-duplicate candidate retrieval by scanning indexed hashes in SQLite.
        Calculates exact Hamming distance for both pHash and dHash.
        Returns matching candidates and total candidates examined.
        """
        exclude_ids = exclude_asset_ids or set()
        query_sql = """
            SELECT id, image_sha256, dhash, ahash, phash,
                   width, height, aspect_ratio, format,
                   file_size_bytes, indexed_at, status
            FROM assets
        """
        rows = self.db.execute_query(query_sql)
        candidates_examined = len(rows)
        matched_candidates = []

        for r in rows:
            asset_id = r["id"]
            if asset_id in exclude_ids:
                continue

            cand_phash = r["phash"]
            cand_dhash = r["dhash"]

            try:
                p_dist = calculate_hamming_distance(query_phash, cand_phash)
                d_dist = calculate_hamming_distance(query_dhash, cand_dhash)
            except HashFormatError as e:
                logger.warning(f"Corrupted or invalid hash in asset {asset_id}: {e}")
                continue

            # Classify candidate based on configurable thresholds
            is_strong = (p_dist <= self.strong_phash_threshold and d_dist <= self.strong_dhash_threshold)
            is_weak = (p_dist <= self.weak_phash_threshold and d_dist <= self.weak_dhash_threshold)

            if not (is_strong or is_weak):
                continue

            match_type = "strong_near_duplicate" if is_strong else "weak_near_duplicate"
            badge_class = "match-high" if is_strong else "match-med"
            label = "Strong Near-Duplicate" if is_strong else "Perceptual Variant"

            sources = self._get_asset_sources(asset_id)
            primary_source = sources[0] if sources else {}

            matched_candidates.append({
                "asset_id": asset_id,
                "match_type": match_type,
                "exact_match": False,
                "score_type": "hamming_distance",
                "raw_similarity_score": p_dist,
                "display_score": f"{label} (pHash: {p_dist}, dHash: {d_dist})",
                "phash_distance": p_dist,
                "dhash_distance": d_dist,
                "retrieval_method": "perceptual_hash",
                "verification_status": "source_verified",
                "badge_class": badge_class,
                "source_type": primary_source.get("source_type", "local_index"),
                "source_name": primary_source.get("source_name", "Indexed Asset"),
                "source_page_url": primary_source.get("source_page_url"),
                "sources": sources,
                "width": r["width"],
                "height": r["height"],
                "format": r["format"],
                "file_size_bytes": r["file_size_bytes"],
                "indexed_at": r["indexed_at"],
                "preview_url": f"/api/zlens/assets/{asset_id}/preview",
            })

        # Rank candidates by perceptual distance: p_dist + d_dist ascending
        matched_candidates.sort(key=lambda c: (
            0 if c["match_type"] == "strong_near_duplicate" else 1,
            c["phash_distance"] + c["dhash_distance"],
            c["phash_distance"],
        ))

        return matched_candidates, candidates_examined

    # ──────────────────────────────────────────────────────────────────────────
    # Master Local Index Search Pipeline
    # ──────────────────────────────────────────────────────────────────────────

    def search_local_index(
        self,
        query_image: PreprocessedImage,
        max_results: int = 50,
    ) -> LocalSearchResult:
        """
        Executes full retrieval pipeline over the persistent SQLite collection:
        1. Checks database availability and index emptiness.
        2. Exact SHA-256 retrieval.
        3. Near-duplicate perceptual hash retrieval with deduplication.
        4. Precedence ranking: exact duplicate > strong near-duplicate > weak variant.
        """
        start_time = time.time()

        # 1. Check database connectivity & index emptiness
        try:
            count_row = self.db.execute_one("SELECT COUNT(*) as count FROM assets")
            total_assets = count_row["count"] if count_row else 0
        except Exception as e:
            logger.exception("Database error while checking asset count")
            return LocalSearchResult(
                status="database_error",
                message=f"Database error accessing local index: {str(e)}",
                duration_seconds=time.time() - start_time,
            )

        if total_assets == 0:
            return LocalSearchResult(
                status="index_empty",
                message="The local image index is currently empty (0 assets). Please import a permitted image collection via /api/zlens/index/import before searching.",
                total_indexed_assets=0,
                candidates_examined=0,
                duration_seconds=time.time() - start_time,
            )

        # 2. Exact match retrieval
        exact_matches = self.find_exact_matches(query_image.sha256)
        exact_ids = {m["asset_id"] for m in exact_matches}

        # 3. Near-duplicate retrieval (excluding already matched exact asset IDs)
        near_matches, candidates_examined = self.find_near_duplicates(
            query_phash=query_image.phash,
            query_dhash=query_image.dhash,
            exclude_asset_ids=exact_ids,
        )

        # 4. Merge with precedence ranking: exact matches first, then near-duplicates
        all_matches = exact_matches + near_matches
        truncated_matches = all_matches[:max_results]

        duration = time.time() - start_time
        exact_count = len(exact_matches)
        near_count = len(near_matches)

        if not all_matches:
            message = f"Search completed: examined {candidates_examined} indexed assets from local collection. No exact or near-duplicate matches found within distance criteria."
            status = "no_matches"
        else:
            message = f"Search completed: found {len(all_matches)} matching candidate(s) ({exact_count} exact, {near_count} near-duplicate) across {candidates_examined} examined assets."
            status = "matches_found"

        return LocalSearchResult(
            status=status,
            message=message,
            total_indexed_assets=total_assets,
            candidates_examined=candidates_examined,
            exact_matches_count=exact_count,
            near_duplicates_count=near_count,
            duration_seconds=duration,
            matches=truncated_matches,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helper: Asset Sources and Preview Resolution
    # ──────────────────────────────────────────────────────────────────────────

    def _get_asset_sources(self, asset_id: int) -> list[dict[str, Any]]:
        """Fetches all provenance sources for a given asset."""
        query_sql = """
            SELECT source_type, source_name, source_page_url, source_image_url, discovered_at
            FROM asset_sources
            WHERE asset_id = ?
            ORDER BY id ASC
        """
        rows = self.db.execute_query(query_sql, (asset_id,))
        return [dict(r) for r in rows]

    def get_asset_preview_info(self, asset_id: int) -> Optional[tuple[str, str, str]]:
        """
        Resolves safe file path for previewing an indexed asset.
        Returns (directory_path, filename, mime_type) if valid file exists inside permitted dir.
        Prevents path traversal.
        """
        row = self.db.execute_one(
            """
            SELECT a.format, s.source_page_url 
            FROM assets a
            LEFT JOIN asset_sources s ON a.id = s.asset_id
            WHERE a.id = ?
            LIMIT 1
            """,
            (asset_id,),
        )
        if not row:
            return None

        source_url = row["source_page_url"]
        fmt = row["format"].lower()

        if not source_url:
            return None

        # Clean source relative path
        clean_rel = source_url.replace("\\", "/").lstrip("/")
        full_path = os.path.abspath(os.path.join(self.permitted_dataset_dir, clean_rel))

        # Security check: must reside inside permitted directory
        norm_base = os.path.realpath(os.path.abspath(self.permitted_dataset_dir))
        norm_target = os.path.realpath(full_path)

        if not norm_target.startswith(norm_base) or not os.path.exists(norm_target):
            return None

        mime_type = f"image/{fmt}" if fmt in ("jpeg", "png", "webp") else "application/octet-stream"
        return os.path.dirname(norm_target), os.path.basename(norm_target), mime_type

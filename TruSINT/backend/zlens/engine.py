"""
engine.py — Clean, Rock-Solid ZLens Local Visual Image Retrieval Engine
Based directly on ZLens_Local_Image_Retrieval_Starter reference implementation.

Provides:
- Exact duplicate detection via SHA-256 byte comparison
- Perceptual near-duplicate retrieval via pHash & dHash Hamming distances
- Robust SQLite persistence with connection leak prevention
- Safe asset retrieval preventing path traversal
- Zero fabricated similarity percentages or synthetic candidates
"""

from __future__ import annotations
import hashlib
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageOps, UnidentifiedImageError
import imagehash

# Base paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR
DATA_DIR = BACKEND_DIR / "data"
COLLECTION_DIR = DATA_DIR / "collection"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "zlens.sqlite3"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
PHASH_MAX_DISTANCE = 12
DHASH_MAX_DISTANCE = 14

# Ensure core directories exist
for folder in (DATA_DIR, COLLECTION_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@contextmanager
def connect_db(db_path: Optional[Path] = None):
    """
    Context manager that connects to SQLite, configures WAL mode,
    automatically commits transactions on success, and ALWAYS closes the connection
    to prevent file locks on Windows.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None):
    """Initializes the assets table and indexes."""
    with connect_db(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                phash TEXT NOT NULL,
                dhash TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(sha256)")


def validate_and_open(path: Path) -> Image.Image:
    """Validates image file extension, verifies integrity, strips EXIF and normalizes to RGB."""
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file extension. Allowed: JPG, PNG, WEBP, BMP, TIFF.")
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image dimensions exceed the safety limit (30 megapixels).")
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.load()
        return img


def hashes_for_image(img: Image.Image) -> tuple[str, str]:
    """Derives perceptual hashes from actual pixel luminance, not random or invented scores."""
    ph = str(imagehash.phash(img))
    dh = str(imagehash.dhash(img))
    return ph, dh


def sha256_file(path: Path) -> str:
    """Computes SHA-256 digest of file bytes."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def index_file(path: Path, root_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Indexes a single image file on disk into the SQLite asset index.
    Derives real SHA-256 and perceptual hashes directly from the file.
    """
    path = path.resolve()
    base_root = (root_dir or ROOT).resolve()
    try:
        rel = path.relative_to(base_root).as_posix()
    except ValueError:
        rel = path.name

    img = validate_and_open(path)
    ph, dh = hashes_for_image(img)
    digest = sha256_file(path)
    size = path.stat().st_size

    with connect_db(db_path) as conn:
        existing = conn.execute("SELECT id FROM assets WHERE relative_path=?", (rel,)).fetchone()
        asset_id = existing["id"] if existing else str(uuid.uuid4())
        conn.execute("""
            INSERT INTO assets(id, relative_path, filename, sha256, phash, dhash, width, height, file_size)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(relative_path) DO UPDATE SET
              filename=excluded.filename, sha256=excluded.sha256,
              phash=excluded.phash, dhash=excluded.dhash,
              width=excluded.width, height=excluded.height,
              file_size=excluded.file_size, indexed_at=CURRENT_TIMESTAMP
        """, (asset_id, rel, path.name, digest, ph, dh, img.width, img.height, size))

    return {
        "id": asset_id,
        "filename": path.name,
        "relative_path": rel,
        "sha256": digest,
        "phash": ph,
        "dhash": dh,
        "width": img.width,
        "height": img.height,
        "file_size": size,
    }


def hamming_hex(a: str, b: str) -> int:
    """Calculates exact Hamming distance between two hex hash strings of equal length."""
    if not a or not b or len(a) != len(b):
        raise ValueError("Invalid or incompatible perceptual hash.")
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except ValueError as exc:
        raise ValueError("Perceptual hash is not valid hexadecimal.") from exc


def search_image(
    query_path: Path,
    db_path: Optional[Path] = None,
    phash_max: int = PHASH_MAX_DISTANCE,
    dhash_max: int = DHASH_MAX_DISTANCE,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Searches indexed collection for exact duplicates and near duplicates.
    Returns: (results_list, candidates_examined_count, query_sha256)
    """
    query_img = validate_and_open(query_path)
    qsha = sha256_file(query_path)
    qph, qdh = hashes_for_image(query_img)

    with connect_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM assets").fetchall()

    results = []
    for row in rows:
        exact = row["sha256"] == qsha
        pd = hamming_hex(qph, row["phash"])
        dd = hamming_hex(qdh, row["dhash"])

        if exact or (pd <= phash_max and dd <= dhash_max):
            if exact:
                kind = "Exact duplicate"
                rank = 0
            else:
                kind = "Near duplicate"
                rank = 1

            results.append({
                "id": row["id"],
                "asset_id": row["id"],
                "filename": row["filename"],
                "preview_url": f"/asset/{row['id']}",
                "exact_match": exact,
                "match_type": kind,
                "phash_distance": pd,
                "dhash_distance": dd,
                "sha256": row["sha256"],
                "width": row["width"],
                "height": row["height"],
                "file_size": row["file_size"],
                "file_size_bytes": row["file_size"],
                "indexed_at": row["indexed_at"],
                "display_score": f"Exact Byte Match (SHA-256)" if exact else f"Near Duplicate (pHash: {pd}, dHash: {dd})",
                "source_name": row["filename"],
                "source_type": "local_collection",
                "_rank": (rank, pd + dd, row["filename"].lower()),
            })

    results.sort(key=lambda r: r["_rank"])
    for r in results:
        r.pop("_rank", None)

    return results, len(rows), qsha


def asset_path_by_id(asset_id: str, db_path: Optional[Path] = None, root_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Locates the actual file on disk for a given asset ID.
    Enforces path containment checks to prevent directory traversal.
    """
    base_root = (root_dir or ROOT).resolve()
    with connect_db(db_path) as conn:
        row = conn.execute("SELECT relative_path FROM assets WHERE id=?", (str(asset_id),)).fetchone()
    if not row:
        return None

    rel = row["relative_path"]
    candidate = (base_root / rel).resolve()

    # Check containment
    if base_root not in candidate.parents and candidate != base_root:
        # Fallback to searching within collection dir
        direct_in_col = (COLLECTION_DIR / Path(rel).name).resolve()
        if direct_in_col.is_file():
            return direct_in_col
        return None

    if candidate.is_file():
        return candidate

    # Also check if file exists directly under COLLECTION_DIR by filename
    fallback = (COLLECTION_DIR / Path(rel).name).resolve()
    return fallback if fallback.is_file() else None


def index_collection(
    collection_dir: Optional[Path] = None,
    root_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Indexes all valid image files in the target collection folder."""
    target_dir = collection_dir or COLLECTION_DIR
    indexed, skipped = [], []

    for path in sorted(target_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            indexed.append(index_file(path, root_dir=root_dir, db_path=db_path))
        except Exception as exc:
            skipped.append({"filename": path.name, "reason": str(exc)})

    return {
        "indexed_or_updated": len(indexed),
        "skipped": skipped,
        "assets": indexed,
    }


def get_status(db_path: Optional[Path] = None) -> dict[str, Any]:
    """Returns total assets indexed in the SQLite database."""
    with connect_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    return {
        "indexed_assets": count,
        "total_assets": count,
        "database": "SQLite",
        "phash_max_distance": PHASH_MAX_DISTANCE,
        "dhash_max_distance": DHASH_MAX_DISTANCE,
        "collection_dir": str(COLLECTION_DIR),
        "database_path": str(DB_PATH),
    }


# Initialize DB on module import
init_db()

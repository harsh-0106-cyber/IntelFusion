"""
test_zlens_indexing.py — Comprehensive Unit & Integration Tests for ZLens SQLite Indexing

Covers:
1. Database schema initialization.
2. Persistence after closing and reopening the connection.
3. Successful indexing of a valid image.
4. Duplicate SHA-256 handling & asset-sources linkage.
5. Repeated batch imports (idempotency).
6. Unsupported image files.
7. Corrupted image files.
8. File-size and pixel-count limits.
9. SQLite transaction rollback on failure.
10. Pagination and accurate asset counts.
11. Database uniqueness constraints.
12. Protection against arbitrary filesystem paths.
13. Missing/minimal source metadata.
14. Batch imports containing both valid and invalid files.
"""

import io
import os
import sqlite3
import pytest
from PIL import Image

from zlens.database import DatabaseManager
from zlens.preprocessor import ImagePreprocessor
from zlens.indexer import (
    ZLensIndexer,
    IndexResult,
    BatchIndexReport,
    validate_permitted_path,
    PathSecurityError,
)


def make_image_bytes(format="JPEG", size=(100, 100), color=(120, 80, 200)) -> bytes:
    """Creates in-memory image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.fixture
def temp_db(tmp_path):
    """Provides an isolated SQLite database manager in a temporary directory."""
    db_file = str(tmp_path / "test_zlens.db")
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def indexer(temp_db):
    """Provides a ZLensIndexer instance using a temporary database."""
    preprocessor = ImagePreprocessor(max_file_size=2 * 1024 * 1024, max_pixels=500_000)
    return ZLensIndexer(db=temp_db, preprocessor=preprocessor)


class TestZLensIndexing:

    # 1. Database schema initialization
    def test_schema_initialization(self, temp_db):
        with temp_db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in cursor.fetchall()}
            assert "assets" in tables
            assert "asset_sources" in tables

            # Verify indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = {row["name"] for row in cursor.fetchall()}
            assert "idx_assets_sha256" in indexes
            assert "idx_assets_phash" in indexes
            assert "idx_assets_dhash" in indexes
            assert "idx_asset_sources_asset_id" in indexes

    # 2. Persistence after closing and reopening connection
    def test_persistence_across_connections(self, tmp_path):
        db_path = str(tmp_path / "persistent.db")
        db1 = DatabaseManager(db_path=db_path)
        indexer1 = ZLensIndexer(db=db1)

        raw = make_image_bytes("JPEG", color=(50, 100, 150))
        res1 = indexer1.index_image(raw, source_name="batch_one")
        assert res1.status == "indexed"
        asset_id = res1.asset_id

        # Reopen via new DatabaseManager pointing to same file
        db2 = DatabaseManager(db_path=db_path)
        indexer2 = ZLensIndexer(db=db2)
        stats = indexer2.get_stats()
        assert stats["total_assets"] == 1
        assert stats["total_sources"] == 1

        assets = indexer2.get_assets(limit=10)
        assert len(assets) == 1
        assert assets[0]["id"] == asset_id
        assert assets[0]["sources"][0]["source_name"] == "batch_one"

    # 3. Successful indexing of a valid image
    def test_successful_indexing_valid_image(self, indexer):
        raw = make_image_bytes("PNG", size=(80, 80), color=(10, 200, 100))
        res = indexer.index_image(
            raw,
            source_type="permitted_dataset",
            source_name="wikimedia_commons",
            source_page_url="https://commons.wikimedia.org/wiki/File:Test.png",
        )
        assert res.status == "indexed"
        assert res.is_duplicate is False
        assert res.asset_id is not None
        assert len(res.image_sha256) == 64

        stats = indexer.get_stats()
        assert stats["total_assets"] == 1
        assert stats["formats_breakdown"].get("PNG") == 1

    # 4. Duplicate SHA-256 handling & asset-sources linkage
    def test_duplicate_sha256_preserves_provenance(self, indexer):
        raw = make_image_bytes("JPEG", color=(200, 50, 50))
        res1 = indexer.index_image(
            raw,
            source_type="local_upload",
            source_name="upload_one",
            source_page_url="page_a.html",
        )
        assert res1.status == "indexed"

        # Index same bytes with a second source page URL
        res2 = indexer.index_image(
            raw,
            source_type="permitted_dataset",
            source_name="dataset_mirror",
            source_page_url="page_b.html",
        )
        assert res2.status == "duplicate"
        assert res2.is_duplicate is True
        assert res2.asset_id == res1.asset_id
        assert res2.image_sha256 == res1.image_sha256

        # Check that assets count remains 1, but asset_sources has 2 entries
        stats = indexer.get_stats()
        assert stats["total_assets"] == 1
        assert stats["total_sources"] == 2

        assets = indexer.get_assets(limit=10)
        sources = assets[0]["sources"]
        assert len(sources) == 2
        page_urls = {s["source_page_url"] for s in sources}
        assert "page_a.html" in page_urls
        assert "page_b.html" in page_urls

    # 5. Repeated batch imports (idempotency)
    def test_repeated_batch_import_idempotency(self, indexer, tmp_path):
        import_dir = tmp_path / "dataset"
        import_dir.mkdir()

        # Create 3 valid images
        for i in range(3):
            file_path = import_dir / f"img_{i}.jpg"
            file_path.write_bytes(make_image_bytes("JPEG", color=(i * 40, 50, 60)))

        # First import
        report1 = indexer.index_directory(str(import_dir), source_name="initial_batch")
        assert report1.total_files_discovered == 3
        assert report1.indexed_count == 3
        assert report1.duplicate_count == 0
        assert report1.error_count == 0

        # Rerun identical import
        report2 = indexer.index_directory(str(import_dir), source_name="initial_batch")
        assert report2.total_files_discovered == 3
        assert report2.indexed_count == 0
        assert report2.duplicate_count == 3
        assert report2.error_count == 0

        # Total assets in database must still be strictly 3
        stats = indexer.get_stats()
        assert stats["total_assets"] == 3

    # 6. Unsupported image files
    def test_unsupported_image_files_skipped(self, indexer, tmp_path):
        test_dir = tmp_path / "mixed_files"
        test_dir.mkdir()

        (test_dir / "notes.txt").write_text("Hello world", encoding="utf-8")
        (test_dir / "page.html").write_text("<html></html>", encoding="utf-8")
        (test_dir / "data.csv").write_text("a,b,c", encoding="utf-8")
        (test_dir / "valid.jpg").write_bytes(make_image_bytes("JPEG"))

        report = indexer.index_directory(str(test_dir))
        assert report.total_files_discovered == 1
        assert report.skipped_count == 3
        assert report.indexed_count == 1
        assert report.error_count == 0

    # 7. Corrupted image files
    def test_corrupted_image_reported(self, indexer, tmp_path):
        test_dir = tmp_path / "corrupted_dir"
        test_dir.mkdir()

        # Starts with JPEG magic bytes but contains garbage bytes
        corrupt_file = test_dir / "broken.jpg"
        corrupt_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 250)

        report = indexer.index_directory(str(test_dir))
        assert report.total_files_discovered == 1
        assert report.indexed_count == 0
        assert report.error_count == 1
        assert len(report.error_details) == 1
        assert "broken.jpg" in report.error_details[0]["file"]

    # 8. File-size and pixel-count limits
    def test_limits_enforced_during_indexing(self, temp_db):
        strict_preprocessor = ImagePreprocessor(
            max_file_size=1000,        # 1000 bytes
            max_pixels=2000,          # 2000 pixels
        )
        indexer = ZLensIndexer(db=temp_db, preprocessor=strict_preprocessor)

        oversized = make_image_bytes("JPEG", size=(100, 100))  # 10,000 pixels
        res = indexer.index_image(oversized)
        assert res.status == "error"
        assert res.asset_id is None
        assert "exceeds" in (res.error_message or "").lower()

    # 9. SQLite transaction rollback on failure
    def test_transaction_rollback_on_failure(self, indexer, monkeypatch):
        raw = make_image_bytes("PNG")

        def failing_insert_source(*args, **kwargs):
            raise sqlite3.OperationalError("Simulated disk error during source insertion")

        monkeypatch.setattr(indexer, "_insert_source", failing_insert_source)

        with pytest.raises(sqlite3.OperationalError):
            indexer.index_image(raw)

        # Confirm rollback: asset must not exist in `assets` table
        stats = indexer.get_stats()
        assert stats["total_assets"] == 0
        assert stats["total_sources"] == 0

    # 10. Pagination and accurate asset counts
    def test_pagination_and_asset_counts(self, indexer):
        for i in range(7):
            indexer.index_image(
                make_image_bytes("JPEG", color=(i * 30, i * 20, 100)),
                source_page_url=f"doc_{i}.html",
            )

        stats = indexer.get_stats()
        assert stats["total_assets"] == 7

        # Page 1 (limit 3, offset 0)
        page1 = indexer.get_assets(limit=3, offset=0)
        assert len(page1) == 3

        # Page 2 (limit 3, offset 3)
        page2 = indexer.get_assets(limit=3, offset=3)
        assert len(page2) == 3
        # Confirm IDs don't overlap
        p1_ids = {a["id"] for a in page1}
        p2_ids = {a["id"] for a in page2}
        assert p1_ids.isdisjoint(p2_ids)

        # Page 3 (remaining 1)
        page3 = indexer.get_assets(limit=3, offset=6)
        assert len(page3) == 1

    # 11. Database uniqueness constraints
    def test_database_uniqueness_constraint_direct(self, temp_db):
        with temp_db.connection() as conn:
            conn.execute(
                """
                INSERT INTO assets (
                    image_sha256, dhash, ahash, phash,
                    width, height, aspect_ratio, format,
                    file_size_bytes, created_at, indexed_at
                ) VALUES ('sha_abc123', 'dh', 'ah', 'ph', 100, 100, 1.0, 'JPEG', 500, 't1', 't1')
                """
            )
            # Duplicate SHA-256 insert must violate UNIQUE constraint
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO assets (
                        image_sha256, dhash, ahash, phash,
                        width, height, aspect_ratio, format,
                        file_size_bytes, created_at, indexed_at
                    ) VALUES ('sha_abc123', 'dh', 'ah', 'ph', 100, 100, 1.0, 'JPEG', 500, 't2', 't2')
                    """
                )

    # 12. Protection against arbitrary filesystem paths
    def test_path_security_validation(self, tmp_path):
        allowed_dir = tmp_path / "allowed_collection"
        allowed_dir.mkdir()
        outside_dir = tmp_path / "system_secrets"
        outside_dir.mkdir()

        # Valid subfolder inside allowed directory
        sub_dir = allowed_dir / "category_a"
        sub_dir.mkdir()
        validated = validate_permitted_path(str(sub_dir), str(allowed_dir))
        assert os.path.exists(validated)

        # Attempt path traversal to outside directory
        with pytest.raises(PathSecurityError):
            validate_permitted_path(str(outside_dir), str(allowed_dir))

        with pytest.raises(PathSecurityError):
            validate_permitted_path(str(allowed_dir / ".." / "system_secrets"), str(allowed_dir))

        # Attempt non-existent directory
        with pytest.raises(PathSecurityError):
            validate_permitted_path(str(allowed_dir / "ghost_folder"), str(allowed_dir))

    # 13. Missing source metadata handled safely
    def test_missing_source_metadata(self, indexer):
        raw = make_image_bytes("WEBP")
        res = indexer.index_image(
            raw,
            source_type="local_upload",
            source_name=None,
            source_page_url=None,
            source_image_url=None,
        )
        assert res.status == "indexed"
        assets = indexer.get_assets(limit=1)
        assert len(assets) == 1
        src = assets[0]["sources"][0]
        assert src["source_type"] == "local_upload"
        assert src["source_name"] is None
        assert src["source_page_url"] is None

    # 14. Batch imports containing both valid and invalid files
    def test_batch_import_mixed_valid_and_invalid(self, indexer, tmp_path):
        batch_dir = tmp_path / "mixed_batch"
        batch_dir.mkdir()

        # 2 valid images
        (batch_dir / "good1.jpg").write_bytes(make_image_bytes("JPEG", color=(10, 10, 10)))
        (batch_dir / "good2.png").write_bytes(make_image_bytes("PNG", color=(20, 20, 20)))

        # 1 corrupt image
        (batch_dir / "bad.jpg").write_bytes(b"\xff\xd8\xff\xe0CORRUPT_BYTES")

        # 1 non-image file
        (batch_dir / "ignore.pdf").write_bytes(b"%PDF-1.4...")

        report = indexer.index_directory(str(batch_dir))
        assert report.total_files_discovered == 3  # good1, good2, bad.jpg
        assert report.skipped_count == 1           # ignore.pdf
        assert report.indexed_count == 2           # good1, good2
        assert report.error_count == 1             # bad.jpg
        assert report.duplicate_count == 0

        # Confirm valid files were committed despite the error on bad.jpg
        stats = indexer.get_stats()
        assert stats["total_assets"] == 2

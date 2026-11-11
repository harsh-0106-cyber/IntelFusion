"""
test_milestone4_verification.py — Formal Verification Suite for Milestone 4 (ZLens Retrieval)

Performs controlled automated retrieval tests on temporary test assets and an isolated database:
- Test A: Exact match (SHA-256 equality, identical asset returned).
- Test B: Persistent exact match (closed/reopened database, process restart simulation).
- Test C: Near duplicate (transformed/resized/recompressed, measures pHash/dHash Hamming distance).
- Test D: Unrelated image (distinct image not falsely reported as exact match or near duplicate).
- Test E: Empty index, invalid image, corrupt hash, and database error produce distinct outcomes.
"""

import io
import os
import pytest
from PIL import Image, ImageDraw

from zlens.database import DatabaseManager
from zlens.preprocessor import ImagePreprocessor, ImageValidationError
from zlens.indexer import ZLensIndexer
from zlens.retriever import (
    ZLensRetriever,
    LocalSearchResult,
    calculate_hamming_distance,
    HashFormatError,
)


def create_synthetic_image(pattern: str = "rectangles", size=(200, 200), color_seed: int = 1) -> bytes:
    """Generates synthetic, deterministic, self-contained test images."""
    img = Image.new("RGB", size, (240, 240, 240))
    draw = ImageDraw.Draw(img)

    if pattern == "rectangles":
        draw.rectangle([20, 20, 80, 80], fill=(200, 40, 40), outline=(0, 0, 0))
        draw.rectangle([90, 90, 180, 180], fill=(40, 120, 200), outline=(0, 0, 0))
        draw.ellipse([110, 20, 170, 80], fill=(40, 180, 80), outline=(0, 0, 0))
    elif pattern == "circles":
        for r in range(10, 90, 15):
            draw.ellipse([100 - r, 100 - r, 100 + r, 100 + r], outline=(color_seed * 40 % 255, 60, 180), width=3)
    elif pattern == "lines":
        for i in range(0, 200, 20):
            draw.line([(0, i), (200, 200 - i)], fill=(30, 30, 30), width=2)
    elif pattern == "blank_white":
        draw.rectangle([0, 0, 200, 200], fill=(255, 255, 255))
    elif pattern == "blank_black":
        draw.rectangle([0, 0, 200, 200], fill=(10, 10, 10))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def temp_env(tmp_path):
    """Provides isolated DatabaseManager, Preprocessor, and Indexer."""
    db_file = str(tmp_path / "milestone4_verify.db")
    db = DatabaseManager(db_path=db_file)
    preprocessor = ImagePreprocessor()
    indexer = ZLensIndexer(db=db, preprocessor=preprocessor)
    retriever = ZLensRetriever(db=db, preprocessor=preprocessor)
    return {
        "db": db,
        "db_file": db_file,
        "preprocessor": preprocessor,
        "indexer": indexer,
        "retriever": retriever,
        "tmp_path": tmp_path,
    }


class TestMilestone4Verification:
    """Controlled automated test suite fulfilling Milestone 4 verification."""

    # Test A: Exact match
    def test_a_exact_match(self, temp_env):
        """
        1. Index a test image.
        2. Search using the exact same file bytes.
        3. Verify that its SHA-256 matches and the indexed asset is returned as an exact match.
        """
        img_bytes = create_synthetic_image("rectangles")
        indexer = temp_env["indexer"]
        retriever = temp_env["retriever"]
        prep = temp_env["preprocessor"]

        idx_res = indexer.index_image(
            img_bytes,
            source_type="test_suite",
            source_name="synthetic_fixture_a",
            source_page_url="rectangles.png",
        )
        assert idx_res.status == "indexed"
        assert idx_res.asset_id is not None
        assert idx_res.image_sha256 is not None

        query_prep = prep.preprocess(img_bytes)
        assert query_prep.sha256 == idx_res.image_sha256

        search_res = retriever.search_local_index(query_prep)
        assert search_res.status == "matches_found"
        assert search_res.exact_matches_count == 1
        assert len(search_res.matches) == 1

        top_match = search_res.matches[0]
        assert top_match["exact_match"] is True
        assert top_match["match_type"] == "exact_duplicate"
        assert top_match["asset_id"] == idx_res.asset_id
        assert top_match["retrieval_method"] == "exact_sha256"
        assert top_match["phash_distance"] == 0
        assert top_match["dhash_distance"] == 0

    # Test B: Persistent exact match
    def test_b_persistent_exact_match(self, temp_env):
        """
        1. Index an image.
        2. Close and reopen the database or restart the application.
        3. Search with the same image.
        4. Verify that the exact match is still returned.
        """
        img_bytes = create_synthetic_image("circles")
        db_file = temp_env["db_file"]
        indexer1 = temp_env["indexer"]
        prep = temp_env["preprocessor"]

        idx_res = indexer1.index_image(img_bytes, source_name="persistent_test")
        assert idx_res.status == "indexed"
        target_asset_id = idx_res.asset_id

        # Simulate full restart: instantiate brand new DatabaseManager & Retriever from disk
        reopened_db = DatabaseManager(db_path=db_file)
        retriever_restarted = ZLensRetriever(db=reopened_db, preprocessor=prep)

        query_prep = prep.preprocess(img_bytes)
        search_res = retriever_restarted.search_local_index(query_prep)

        assert search_res.status == "matches_found"
        assert search_res.exact_matches_count == 1
        assert search_res.matches[0]["asset_id"] == target_asset_id
        assert search_res.matches[0]["exact_match"] is True

    # Test C: Near duplicate
    def test_c_near_duplicate(self, temp_env):
        """
        1. Create a test image and a resized or recompressed version of it.
        2. Index the original and search using the transformed version.
        3. Record the actual pHash and dHash distances.
        4. Verify near-duplicate retrieval against a documented, configurable threshold.
        """
        indexer = temp_env["indexer"]
        retriever = temp_env["retriever"]
        prep = temp_env["preprocessor"]

        # Original image
        orig_bytes = create_synthetic_image("rectangles", size=(256, 256))
        idx_res = indexer.index_image(orig_bytes, source_name="orig_rectangles")
        assert idx_res.status == "indexed"

        # Transformed near-duplicate: resized from 256x256 to 220x220 and recompressed as JPEG quality 75
        orig_pil = Image.open(io.BytesIO(orig_bytes))
        transformed_pil = orig_pil.resize((220, 220), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        transformed_pil.save(buf, format="JPEG", quality=75)
        transformed_bytes = buf.getvalue()

        # Query with transformed image
        query_prep = prep.preprocess(transformed_bytes)
        assert query_prep.sha256 != idx_res.image_sha256  # SHA-256 must differ

        p_dist = calculate_hamming_distance(query_prep.phash, prep.preprocess(orig_bytes).phash)
        d_dist = calculate_hamming_distance(query_prep.dhash, prep.preprocess(orig_bytes).dhash)

        # Record distances
        print(f"\n[Test C Measurements] pHash distance: {p_dist}, dHash distance: {d_dist}")

        search_res = retriever.search_local_index(query_prep)

        # Configured thresholds: strong (p<=6, d<=4), weak (p<=8, d<=8)
        assert p_dist <= retriever.weak_phash_threshold
        assert d_dist <= retriever.weak_dhash_threshold
        assert search_res.status == "matches_found"
        assert search_res.exact_matches_count == 0
        assert search_res.near_duplicates_count >= 1

        match = search_res.matches[0]
        assert match["asset_id"] == idx_res.asset_id
        assert match["exact_match"] is False
        assert match["phash_distance"] == p_dist
        assert match["dhash_distance"] == d_dist

    # Test D: Unrelated image
    def test_d_unrelated_image(self, temp_env):
        """
        1. Index one test image.
        2. Search with a clearly different test image.
        3. Verify that it is not incorrectly reported as an exact match.
        4. Report any near-duplicate false positive honestly.
        """
        indexer = temp_env["indexer"]
        retriever = temp_env["retriever"]
        prep = temp_env["preprocessor"]

        # Index geometric circles
        img_a = create_synthetic_image("circles", size=(200, 200))
        idx_res = indexer.index_image(img_a, source_name="circles")
        assert idx_res.status == "indexed"

        # Query with high-contrast dense diagonal lines
        img_b = create_synthetic_image("lines", size=(200, 200))
        query_prep = prep.preprocess(img_b)

        p_dist = calculate_hamming_distance(query_prep.phash, prep.preprocess(img_a).phash)
        d_dist = calculate_hamming_distance(query_prep.dhash, prep.preprocess(img_a).dhash)

        print(f"\n[Test D Measurements] Unrelated images: pHash distance: {p_dist}, dHash distance: {d_dist}")

        search_res = retriever.search_local_index(query_prep)

        # Must NOT be an exact match
        assert search_res.exact_matches_count == 0
        # Given distinctly different frequency structures, must be rejected as no matches
        assert p_dist > retriever.strong_phash_threshold
        assert search_res.status == "no_matches"
        assert len(search_res.matches) == 0

    # Test E: Empty index and invalid input
    def test_e_empty_index_and_invalid_input(self, temp_env, tmp_path):
        """
        Verify that an empty collection, invalid image, corrupt hash, and database error
        produce distinct, truthful outcomes.
        """
        db = temp_env["db"]
        prep = temp_env["preprocessor"]
        retriever = temp_env["retriever"]

        # 1. Empty index outcome
        query_prep = prep.preprocess(create_synthetic_image("circles"))
        empty_res = retriever.search_local_index(query_prep)
        assert empty_res.status == "index_empty"
        assert empty_res.total_indexed_assets == 0
        assert "empty" in empty_res.message.lower()

        # 2. Invalid image outcome (magic bytes / corrupt bytes)
        with pytest.raises(ImageValidationError) as exc_info:
            prep.preprocess(b"NOT_A_VALID_IMAGE_HEADER_123456789")
        assert exc_info.value.code in ("UNSUPPORTED_FORMAT", "CORRUPT_IMAGE")

        # 3. Corrupt hash format outcome
        with pytest.raises(HashFormatError):
            calculate_hamming_distance("not_a_hex", "0000000000000000")
        with pytest.raises(HashFormatError):
            calculate_hamming_distance("00", "0000000000000000")

        # 4. Database error outcome
        broken_db = DatabaseManager(db_path=str(tmp_path / "corrupt.db"))
        broken_retriever = ZLensRetriever(db=broken_db, preprocessor=prep)
        with broken_db.connection() as conn:
            conn.execute("DROP TABLE IF EXISTS assets")
            conn.execute("DROP TABLE IF EXISTS asset_sources")

        db_err_res = broken_retriever.search_local_index(query_prep)
        assert db_err_res.status == "database_error"
        assert "database error" in db_err_res.message.lower()

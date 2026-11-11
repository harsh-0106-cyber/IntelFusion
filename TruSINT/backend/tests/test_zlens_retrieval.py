"""
test_zlens_retrieval.py — Comprehensive Unit & Integration Tests for ZLens Exact and Near-Duplicate Retrieval

Covers:
1. Exact SHA-256 retrieval.
2. Exact match after application restart / persistence.
3. pHash distance calculations.
4. dHash distance calculations.
5. Identical hashes producing zero distance.
6. Invalid and mismatched hash formats.
7. Configurable distance thresholds.
8. Near-duplicate retrieval (resized, recompressed, cropped).
9. Unrelated images not being classified as exact matches or false positives.
10. Duplicate result elimination.
11. Missing source URLs handled safely.
12. Empty index behavior.
13. Empty search results (indexed collection populated, but no matches).
14. Database failure handling.
15. API response structure compliance.
16. Safe asset preview endpoint.
17. Regression test verifying absence of fabricated scores.
"""

import io
import os
import sqlite3
import pytest
from PIL import Image

from zlens.database import DatabaseManager
from zlens.preprocessor import ImagePreprocessor
from zlens.indexer import ZLensIndexer
from zlens.retriever import (
    ZLensRetriever,
    LocalSearchResult,
    calculate_hamming_distance,
    validate_hex_hash,
    HashFormatError,
)
from tests.ground_truth_builder import build_ground_truth_dataset


@pytest.fixture
def temp_db(tmp_path):
    """Provides an isolated database for retrieval tests."""
    db_file = str(tmp_path / "test_retrieval.db")
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def preprocessor():
    return ImagePreprocessor()


@pytest.fixture
def retriever(temp_db, preprocessor):
    return ZLensRetriever(db=temp_db, preprocessor=preprocessor)


@pytest.fixture
def ground_truth_suite(tmp_path):
    """Builds and returns the deterministic ground-truth image suite."""
    gt_dir = str(tmp_path / "gt_images")
    return build_ground_truth_dataset(gt_dir)


class TestZLensRetrieval:

    # 1. Exact SHA-256 retrieval
    def test_exact_sha256_retrieval(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            base_bytes = f.read()

        idx_res = indexer.index_image(
            base_bytes,
            source_type="permitted_dataset",
            source_name="base_fixture",
            source_page_url="base_image.jpg",
        )
        assert idx_res.status == "indexed"

        # Query using exact copy
        with open(ground_truth_suite["exact"], "rb") as f:
            exact_bytes = f.read()

        query_prep = preprocessor.preprocess(exact_bytes)
        search_res = retriever.search_local_index(query_prep)

        assert search_res.status == "matches_found"
        assert search_res.exact_matches_count == 1
        assert len(search_res.matches) == 1
        match = search_res.matches[0]
        assert match["match_type"] == "exact_duplicate"
        assert match["exact_match"] is True
        assert match["raw_similarity_score"] == 1.0
        assert match["retrieval_method"] == "exact_sha256"
        assert match["asset_id"] == idx_res.asset_id

    # 2. Exact match after application restart / persistence
    def test_exact_match_after_restart(self, tmp_path, preprocessor, ground_truth_suite):
        db_path = str(tmp_path / "persistent_retrieval.db")
        db1 = DatabaseManager(db_path=db_path)
        indexer1 = ZLensIndexer(db=db1, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            base_bytes = f.read()
        res1 = indexer1.index_image(base_bytes, source_name="base_run1")
        assert res1.status == "indexed"

        # Simulate full process restart with fresh DatabaseManager and Retriever
        db2 = DatabaseManager(db_path=db_path)
        retriever2 = ZLensRetriever(db=db2, preprocessor=preprocessor)

        query_prep = preprocessor.preprocess(base_bytes)
        search_res = retriever2.search_local_index(query_prep)

        assert search_res.status == "matches_found"
        assert search_res.exact_matches_count == 1
        assert search_res.matches[0]["asset_id"] == res1.asset_id

    # 3. pHash distance calculations
    def test_phash_distance_calculation(self):
        # 64-bit hex strings (16 hex chars)
        hash1 = "0000000000000000"
        hash2 = "000000000000000f"  # 'f' has 4 set bits: 0000 1111
        assert calculate_hamming_distance(hash1, hash2) == 4

        hash3 = "ffffffffffffffff"  # all 64 bits set
        assert calculate_hamming_distance(hash1, hash3) == 64

    # 4. dHash distance calculations
    def test_dhash_distance_calculation(self):
        hash1 = "a1b2c3d4e5f60718"
        hash2 = "a1b2c3d4e5f60719"  # differs by 1 bit (8 is 1000, 9 is 1001)
        assert calculate_hamming_distance(hash1, hash2) == 1

    # 5. Identical hashes produce zero distance
    def test_identical_hashes_zero_distance(self):
        sample = "c6e4391e39c6c639"
        assert calculate_hamming_distance(sample, sample) == 0

    # 6. Invalid and mismatched hash formats
    def test_invalid_and_mismatched_hash_formats(self):
        with pytest.raises(HashFormatError):
            calculate_hamming_distance("invalid_hex_string!", "0000000000000000")

        # Wrong length (12 instead of 16)
        with pytest.raises(HashFormatError):
            calculate_hamming_distance("000000000000", "0000000000000000")

        # Non-string argument
        with pytest.raises(HashFormatError):
            calculate_hamming_distance(12345, "0000000000000000")

    # 7. Configurable distance thresholds
    def test_configurable_distance_thresholds(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read())

        with open(ground_truth_suite["cropped"], "rb") as f:
            query_prep = preprocessor.preprocess(f.read())

        # With standard threshold (strong=8, weak=12), cropped image should match
        retriever_normal = ZLensRetriever(
            db=temp_db,
            preprocessor=preprocessor,
            strong_phash_threshold=8,
            weak_phash_threshold=12,
        )
        res_normal = retriever_normal.search_local_index(query_prep)
        assert res_normal.status == "matches_found"

        # With overly strict threshold (strong=0, weak=0), near-duplicate must be excluded
        retriever_strict = ZLensRetriever(
            db=temp_db,
            preprocessor=preprocessor,
            strong_phash_threshold=0,
            strong_dhash_threshold=0,
            weak_phash_threshold=0,
            weak_dhash_threshold=0,
        )
        res_strict = retriever_strict.search_local_index(query_prep)
        assert res_strict.status == "no_matches"
        assert len(res_strict.matches) == 0

    # 8. Near-duplicate retrieval (resized, recompressed, cropped)
    def test_near_duplicate_candidate_retrieval(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read(), source_name="base_indexed")

        # A. Resized copy query
        with open(ground_truth_suite["resized"], "rb") as f:
            res_resized = retriever.search_local_index(preprocessor.preprocess(f.read()))
        assert res_resized.status == "matches_found"
        assert res_resized.near_duplicates_count >= 1
        m_resized = res_resized.matches[0]
        assert m_resized["exact_match"] is False
        assert m_resized["phash_distance"] <= 6

        # B. Recompressed copy query
        with open(ground_truth_suite["recompressed"], "rb") as f:
            res_recomp = retriever.search_local_index(preprocessor.preprocess(f.read()))
        assert res_recomp.status == "matches_found"
        assert res_recomp.matches[0]["exact_match"] is False
        assert res_recomp.matches[0]["phash_distance"] <= 6

        # C. Cropped copy query
        with open(ground_truth_suite["cropped"], "rb") as f:
            res_crop = retriever.search_local_index(preprocessor.preprocess(f.read()))
        assert res_crop.status == "matches_found"
        assert res_crop.matches[0]["phash_distance"] <= 10

    # 9. Unrelated images not classified as exact or false positive
    def test_unrelated_image_not_matched(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read())

        with open(ground_truth_suite["unrelated"], "rb") as f:
            res_unrelated = retriever.search_local_index(preprocessor.preprocess(f.read()))

        assert res_unrelated.status == "no_matches"
        assert len(res_unrelated.matches) == 0
        assert res_unrelated.exact_matches_count == 0
        assert res_unrelated.near_duplicates_count == 0

    # 10. Duplicate result elimination
    def test_duplicate_result_elimination(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            raw = f.read()

        # Index once with source 1
        indexer.index_image(raw, source_page_url="source_1.html")
        # Index same bytes with source 2 (linked in asset_sources)
        indexer.index_image(raw, source_page_url="source_2.html")

        # Query with exact image
        res = retriever.search_local_index(preprocessor.preprocess(raw))
        # Must return exactly 1 candidate record (with multiple sources attached), NOT 2 duplicate records
        assert len(res.matches) == 1
        assert res.matches[0]["exact_match"] is True
        assert len(res.matches[0]["sources"]) == 2

    # 11. Missing source URLs handled cleanly
    def test_missing_source_urls_handled(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read(), source_page_url=None)

        with open(ground_truth_suite["exact"], "rb") as f:
            res = retriever.search_local_index(preprocessor.preprocess(f.read()))

        assert res.status == "matches_found"
        assert res.matches[0]["source_page_url"] is None

    # 12. Empty index behavior
    def test_empty_index_behavior(self, temp_db, preprocessor, ground_truth_suite):
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            res = retriever.search_local_index(preprocessor.preprocess(f.read()))

        assert res.status == "index_empty"
        assert res.total_indexed_assets == 0
        assert res.candidates_examined == 0
        assert len(res.matches) == 0
        assert "empty" in res.message.lower()

    # 13. Empty search results (populated index, zero qualifying matches)
    def test_empty_search_results_when_unmatched(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read())

        with open(ground_truth_suite["unindexed"], "rb") as f:
            res = retriever.search_local_index(preprocessor.preprocess(f.read()))

        assert res.status == "no_matches"
        assert res.total_indexed_assets == 1
        assert res.candidates_examined == 1
        assert len(res.matches) == 0
        assert "no exact or near-duplicate matches found" in res.message.lower()

    # 14. Database failure handling
    def test_database_failure_handling(self, preprocessor, ground_truth_suite, tmp_path):
        # Database pointing to invalid read-only or corrupted path
        db = DatabaseManager(db_path=str(tmp_path / "broken.db"))
        retriever = ZLensRetriever(db=db, preprocessor=preprocessor)

        # Drop assets table to simulate missing or corrupted database
        with db.connection() as conn:
            conn.execute("DROP TABLE IF EXISTS asset_sources")
            conn.execute("DROP TABLE IF EXISTS assets")

        with open(ground_truth_suite["base"], "rb") as f:
            res = retriever.search_local_index(preprocessor.preprocess(f.read()))

        assert res.status == "database_error"
        assert "database error" in res.message.lower()

    # 15. API response structure
    def test_api_response_structure(self, temp_db, preprocessor, ground_truth_suite):
        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=temp_db, preprocessor=preprocessor)

        with open(ground_truth_suite["base"], "rb") as f:
            indexer.index_image(f.read(), source_name="fixture_base", source_page_url="base.jpg")

        with open(ground_truth_suite["exact"], "rb") as f:
            res = retriever.search_local_index(preprocessor.preprocess(f.read()))

        d = res.to_dict()
        required_keys = [
            "status", "message", "total_indexed_assets", "candidates_examined",
            "exact_matches_count", "near_duplicates_count", "duration_seconds", "matches"
        ]
        for k in required_keys:
            assert k in d

        m = d["matches"][0]
        match_keys = [
            "asset_id", "match_type", "exact_match", "score_type", "phash_distance",
            "dhash_distance", "retrieval_method", "verification_status", "preview_url"
        ]
        for mk in match_keys:
            assert mk in m

    # 16. Safe asset preview info
    def test_safe_preview_path_resolution(self, temp_db, preprocessor, tmp_path):
        permitted_dir = tmp_path / "permitted_collection"
        permitted_dir.mkdir()
        img_file = permitted_dir / "sample.jpg"

        test_img = Image.new("RGB", (100, 100), (40, 80, 120))
        test_img.save(str(img_file), format="JPEG")

        indexer = ZLensIndexer(db=temp_db, preprocessor=preprocessor)
        retriever = ZLensRetriever(
            db=temp_db,
            preprocessor=preprocessor,
            permitted_dataset_dir=str(permitted_dir),
        )

        with open(str(img_file), "rb") as f:
            idx_res = indexer.index_image(f.read(), source_page_url="sample.jpg")

        preview_info = retriever.get_asset_preview_info(idx_res.asset_id)
        assert preview_info is not None
        dir_path, filename, mime_type = preview_info
        assert filename == "sample.jpg"
        assert mime_type == "image/jpeg"

    # 17. Regression test: fabricated scores absent
    def test_regression_no_fabricated_scores(self, retriever):
        # Verify that _fallback_similarity does not exist on retriever or indexer
        assert not hasattr(retriever, "_fallback_similarity")
        assert not hasattr(retriever, "fallback_similarity")

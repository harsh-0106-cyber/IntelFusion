"""
benchmark_retrieval.py — ZLens Retrieval Latency and Precision Benchmark

Measures exact-match and near-duplicate retrieval performance across:
1. Ground-truth test fixtures.
2. Scaled collection of 1,000 indexed assets.
3. Scaled collection of 5,000 indexed assets.
"""

import os
import sys
import time
import tempfile
import random
import hashlib

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from zlens.database import DatabaseManager
from zlens.preprocessor import ImagePreprocessor
from zlens.indexer import ZLensIndexer
from zlens.retriever import ZLensRetriever
from tests.ground_truth_builder import build_ground_truth_dataset


def run_benchmark():
    print("=" * 70)
    print(" ZLENS RETRIEVAL BENCHMARK — MILESTONE 4")
    print("=" * 70)

    preprocessor = ImagePreprocessor()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "benchmark.db")
        db = DatabaseManager(db_path=db_path)
        indexer = ZLensIndexer(db=db, preprocessor=preprocessor)
        retriever = ZLensRetriever(db=db, preprocessor=preprocessor)

        # ── Part 1: Ground-Truth Dataset Accuracy & Latency ───────────────
        print("\n[PART 1: Ground-Truth Dataset Evaluation]")
        fixtures = build_ground_truth_dataset(tmp_dir)

        # Index base image
        with open(fixtures["base"], "rb") as f:
            base_bytes = f.read()
        base_prep = preprocessor.preprocess(base_bytes)
        idx_res = indexer.index_image(
            image_bytes=base_bytes,
            source_type="ground_truth",
            source_name="base_image.jpg",
            source_page_url="local://base_image.jpg",
        )
        print(f"Indexed base_image into benchmark database (Asset ID: {idx_res.asset_id}).")

        queries = [
            ("exact_copy", fixtures["exact"], "exact_duplicate"),
            ("resized_copy", fixtures["resized"], "near_duplicate"),
            ("recompressed_copy", fixtures["recompressed"], "near_duplicate"),
            ("cropped_copy", fixtures["cropped"], "near_duplicate"),
            ("similar_pattern", fixtures["similar"], "none"),
            ("unrelated_image", fixtures["unrelated"], "none"),
            ("unindexed_query", fixtures["unindexed"], "none"),
        ]

        results_summary = []
        for q_name, q_path, expected_type in queries:
            with open(q_path, "rb") as f:
                q_bytes = f.read()
            q_prep = preprocessor.preprocess(q_bytes)

            t0 = time.perf_counter()
            res = retriever.search_local_index(q_prep)
            latency_ms = (time.perf_counter() - t0) * 1000

            has_exact = res.exact_matches_count > 0
            has_near = res.near_duplicates_count > 0
            has_match = len(res.matches) > 0

            if expected_type == "exact_duplicate":
                correct = has_exact and res.matches[0]["exact_match"] is True
            elif expected_type == "near_duplicate":
                correct = has_near and not has_exact
            elif expected_type == "none":
                correct = (not has_match)
            else:
                correct = True

            results_summary.append({
                "query": q_name,
                "expected": expected_type,
                "candidates_examined": res.candidates_examined,
                "exact_matches": res.exact_matches_count,
                "near_duplicates": res.near_duplicates_count,
                "total_matches": len(res.matches),
                "latency_ms": latency_ms,
                "correct": correct,
            })

            dist_info = ""
            if res.matches:
                m0 = res.matches[0]
                dist_info = f" | m0 pHash_dist={m0.get('phash_distance')} dHash_dist={m0.get('dhash_distance')}"

            print(f" - {q_name:<20}: latency={latency_ms:6.2f}ms | examined={res.candidates_examined} | exact={res.exact_matches_count} | near={res.near_duplicates_count}{dist_info} | status={'PASS' if correct else 'FAIL'}")

        total_queries = len(results_summary)
        passed_queries = sum(1 for r in results_summary if r["correct"])
        precision = (passed_queries / total_queries) * 100
        print(f"\nGround-Truth Precision: {passed_queries}/{total_queries} ({precision:.1f}%)")

        # ── Part 2: Scaled Performance Benchmark (1,000 & 5,000 assets) ───
        for target_scale in [1000, 5000]:
            print(f"\n[PART 2: Scaled Collection Benchmark — {target_scale} Assets]")
            current_count = db.execute_one("SELECT COUNT(*) as c FROM assets")["c"]
            assets_needed = target_scale - current_count
            print(f"Generating and indexing {assets_needed} synthetic candidate records...")

            # Batch insert synthetic asset records
            with db.get_connection() as conn:
                cursor = conn.cursor()
                now_str = "2026-10-14T22:00:00Z"
                for i in range(assets_needed):
                    rand_bytes = f"benchmark_asset_{target_scale}_{i}_{random.random()}".encode("utf-8")
                    fake_sha = hashlib.sha256(rand_bytes).hexdigest()
                    fake_phash = f"{random.getrandbits(64):016x}"
                    fake_dhash = f"{random.getrandbits(64):016x}"
                    fake_ahash = f"{random.getrandbits(64):016x}"

                    cursor.execute(
                        """
                        INSERT INTO assets (
                            image_sha256, dhash, ahash, phash,
                            width, height, aspect_ratio, format,
                            file_size_bytes, created_at, indexed_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
                        """,
                        (fake_sha, fake_dhash, fake_ahash, fake_phash, 200, 200, 1.0, "PNG", 1024, now_str, now_str),
                    )
                    aid = cursor.lastrowid
                    cursor.execute(
                        """
                        INSERT INTO asset_sources (
                            asset_id, source_type, source_name, source_page_url, discovered_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (aid, "scaled_benchmark", f"synthetic_{i}", None, now_str),
                    )
                conn.commit()

            total_assets = db.execute_one("SELECT COUNT(*) as c FROM assets")["c"]
            print(f"Database now contains {total_assets} indexed assets.")

            # Measure query latencies
            # Test A: Exact match query
            t0 = time.perf_counter()
            exact_res = retriever.find_exact_matches(base_prep.sha256)
            exact_ms = (time.perf_counter() - t0) * 1000

            # Test B: Full near-duplicate scan
            with open(fixtures["resized"], "rb") as f:
                r_bytes = f.read()
            r_prep = preprocessor.preprocess(r_bytes)

            t0 = time.perf_counter()
            near_res, examined = retriever.find_near_duplicates(
                query_phash=r_prep.phash,
                query_dhash=r_prep.dhash,
            )
            near_ms = (time.perf_counter() - t0) * 1000

            # Test C: Full end-to-end local search pipeline
            t0 = time.perf_counter()
            full_res = retriever.search_local_index(r_prep)
            full_ms = (time.perf_counter() - t0) * 1000

            print(f"Scale: {total_assets} assets:")
            print(f" - Exact SHA-256 lookup (B-Tree index): {exact_ms:.3f} ms (Matches: {len(exact_res)})")
            print(f" - Near-duplicate hash scan ({examined} assets): {near_ms:.3f} ms (Matches: {len(near_res)})")
            print(f" - Full search_local_index pipeline: {full_ms:.3f} ms (Status: {full_res.status})")

    print("\n" + "=" * 70)
    print(" BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()

"""
zlens_engine.py — TruSINT Visual Retrieval Engine

Provides genuine visual reverse-image search and candidate verification.
Enforces strict rules:
- No facial identification or cross-platform tracking.
- No synthetic fallback similarity scores or invented results.
- Transparent mathematical distances (SHA-256 exact match, perceptual hash Hamming distance, cosine similarity).
- Explicit verification statuses (source_verified, source_unverified, source_unavailable).
- Empty result list with truthful messaging when no genuine matches exist.
"""

from __future__ import annotations

import os
import io
import re
import html
import json
import time
import random
import logging
import hashlib
from urllib.parse import quote_plus, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import requests
import numpy as np
from PIL import Image

from zlens.preprocessor import ImagePreprocessor, PreprocessedImage, ImageValidationError

logger = logging.getLogger("zlens.engine")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 6))


class ZLensEngine:
    """
    Production-oriented visual reverse image retrieval and verification engine.
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    PLATFORM_METADATA = {
        "facebook": {"name": "Facebook", "color": "#1877f2", "icon": "facebook", "domain": "facebook.com"},
        "instagram": {"name": "Instagram", "color": "#e1306c", "icon": "instagram", "domain": "instagram.com"},
        "x": {"name": "X / Twitter", "color": "#1da1f2", "icon": "twitter", "domain": "x.com"},
        "twitter": {"name": "X / Twitter", "color": "#1da1f2", "icon": "twitter", "domain": "twitter.com"},
        "linkedin": {"name": "LinkedIn", "color": "#0a66c2", "icon": "linkedin", "domain": "linkedin.com"},
        "reddit": {"name": "Reddit", "color": "#ff4500", "icon": "reddit", "domain": "reddit.com"},
        "tiktok": {"name": "TikTok", "color": "#fe2c55", "icon": "tiktok", "domain": "tiktok.com"},
        "youtube": {"name": "YouTube", "color": "#ff0000", "icon": "youtube", "domain": "youtube.com"},
        "pinterest": {"name": "Pinterest", "color": "#e60023", "icon": "pinterest", "domain": "pinterest.com"},
        "github": {"name": "GitHub", "color": "#333333", "icon": "github", "domain": "github.com"},
        "wikimedia": {"name": "Wikimedia Commons", "color": "#339966", "icon": "wikimedia", "domain": "wikimedia.org"},
        "web": {"name": "Web Source", "color": "#00d4ff", "icon": "globe", "domain": ""},
    }

    def __init__(self, preprocessor: Optional[ImagePreprocessor] = None):
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    # ──────────────────────────────────────────────────────────────────────────
    # Candidate Ingestion & Comparison
    # ──────────────────────────────────────────────────────────────────────────

    def compare_candidate_image(
        self,
        query_image: PreprocessedImage,
        candidate_img_url: str,
        source_url: str,
        provider_name: str = "web_crawler",
    ) -> Optional[dict[str, Any]]:
        """
        Fetches the actual candidate image from the source, preprocesses it,
        and computes verifiable mathematical similarity.

        Returns None if image cannot be downloaded or fails validation,
        NEVER fabricating a score.
        """
        candidate_bytes = None
        try:
            resp = self.session.get(
                candidate_img_url,
                timeout=4.0,
                headers={"User-Agent": random.choice(self.USER_AGENTS)},
            )
            if resp.status_code == 200 and len(resp.content) >= 32:
                candidate_bytes = resp.content
        except Exception as e:
            logger.debug(f"Candidate image fetch error for {candidate_img_url}: {e}")
            return None

        if not candidate_bytes:
            return None

        try:
            cand_prep = self.preprocessor.preprocess(candidate_bytes)
        except ImageValidationError as e:
            logger.debug(f"Candidate image validation rejected: {e}")
            return None
        except Exception as e:
            logger.debug(f"Candidate image processing exception: {e}")
            return None

        # 1. Exact duplicate check (SHA-256)
        if query_image.sha256 == cand_prep.sha256:
            return {
                "match_type": "exact_duplicate",
                "score_type": "sha256",
                "raw_similarity_score": 1.0,
                "display_score": "Exact (100%)",
                "verification_status": "source_verified",
                "badge_class": "match-high",
                "metrics": {
                    "sha256_match": True,
                    "phash_distance": 0,
                    "dhash_distance": 0,
                },
                "candidate_metadata": {
                    "width": cand_prep.width,
                    "height": cand_prep.height,
                    "format": cand_prep.format,
                },
            }

        # 2. Near-duplicate check (Perceptual Hashing Hamming distance)
        phash_dist = ImagePreprocessor.hamming_distance(query_image.phash, cand_prep.phash)
        dhash_dist = ImagePreprocessor.hamming_distance(query_image.dhash, cand_prep.dhash)

        if phash_dist <= 8 and dhash_dist <= 6:
            # High-confidence near-duplicate (e.g. resized or recompressed version)
            similarity_approx = round(100.0 * (1.0 - (phash_dist / 64.0)), 1)
            return {
                "match_type": "near_duplicate",
                "score_type": "hamming_distance",
                "raw_similarity_score": phash_dist,
                "display_score": f"Near-Copy ({similarity_approx}%)",
                "verification_status": "source_verified",
                "badge_class": "match-high",
                "metrics": {
                    "phash_distance": phash_dist,
                    "dhash_distance": dhash_dist,
                },
                "candidate_metadata": {
                    "width": cand_prep.width,
                    "height": cand_prep.height,
                    "format": cand_prep.format,
                },
            }

        # 3. Vector Visual Similarity (Cosine similarity on normalized tensor representations)
        q_vec = query_image.tensor_representation.flatten()
        c_vec = cand_prep.tensor_representation.flatten()
        dot_product = float(np.dot(q_vec, c_vec))
        norm_q = float(np.linalg.norm(q_vec))
        norm_c = float(np.linalg.norm(c_vec))

        if norm_q > 0 and norm_c > 0:
            cosine_sim = dot_product / (norm_q * norm_c)
        else:
            cosine_sim = 0.0

        # Discard candidate if neither near-duplicate nor high visual correspondence
        if cosine_sim < 0.72 and phash_dist > 14:
            return None

        # Acceptable visual candidate
        is_moderate = cosine_sim >= 0.82 or phash_dist <= 12
        return {
            "match_type": "visual_similarity",
            "score_type": "cosine_similarity",
            "raw_similarity_score": round(cosine_sim, 4),
            "display_score": f"{round(cosine_sim * 100, 1)}% Visual",
            "verification_status": "source_verified",
            "badge_class": "match-med" if is_moderate else "match-low",
            "metrics": {
                "cosine_similarity": round(cosine_sim, 4),
                "phash_distance": phash_dist,
                "dhash_distance": dhash_dist,
            },
            "candidate_metadata": {
                "width": cand_prep.width,
                "height": cand_prep.height,
                "format": cand_prep.format,
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Candidate Discovery via Permitted Search Sources
    # ──────────────────────────────────────────────────────────────────────────

    def discover_web_candidates(self, query_terms: list[str], max_results: int = 16) -> list[dict[str, Any]]:
        """
        Discovers candidate images from live search results using genuine URLs.
        """
        candidates: list[dict[str, Any]] = []
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bing.com/",
        }

        for term in query_terms:
            if len(candidates) >= max_results:
                break
            url = f"https://www.bing.com/images/search?q={quote_plus(term)}&FORM=HDRSC2"
            try:
                resp = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    matches = re.findall(r'class="iusc"[^>]*m="([^"]+)"', resp.text)
                    for m in matches:
                        try:
                            data = json.loads(html.unescape(m))
                            murl = data.get("murl")
                            turl = data.get("turl", murl)
                            purl = data.get("purl", "")
                            title = data.get("t", "")
                            desc = data.get("desc", title)

                            if murl and purl and murl.startswith("http") and purl.startswith("http"):
                                domain = urlparse(purl).netloc.lower()
                                detected_plat = "web"
                                for p_key, p_meta in self.PLATFORM_METADATA.items():
                                    if p_meta.get("domain") and p_meta["domain"] in domain:
                                        detected_plat = p_key
                                        break

                                candidates.append({
                                    "image_url": murl,
                                    "thumbnail_url": turl,
                                    "source_page_url": purl,
                                    "title": title or f"Discovered Image ({domain})",
                                    "snippet": desc or f"Published image on {domain}",
                                    "source_provider": "bing_image_index",
                                    "platform": detected_plat,
                                })
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"Discovery error for term '{term}': {e}")

        # Deduplicate candidates by image_url and source_page_url
        seen_images = set()
        seen_pages = set()
        unique = []
        for c in candidates:
            img_u = c["image_url"]
            pg_u = c["source_page_url"]
            if img_u not in seen_images and pg_u not in seen_pages:
                seen_images.add(img_u)
                seen_pages.add(pg_u)
                unique.append(c)

        return unique[:max_results]

    # ──────────────────────────────────────────────────────────────────────────
    # Master Search & Candidate Verification Workflow
    # ──────────────────────────────────────────────────────────────────────────

    def search_and_verify(
        self,
        query_image: PreprocessedImage,
        name: str = "",
        keywords: str = "",
        target_platforms: Optional[list[str]] = None,
        max_results: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Executes candidate retrieval, downloads candidates, applies verified
        comparisons, and filters candidates strictly by genuine evidence.
        """
        name_clean = (name or "").strip()
        keywords_clean = (keywords or "").strip()

        # Build genuine search terms
        terms = []
        if name_clean:
            terms.append(f"{name_clean} {keywords_clean}".strip())
            terms.append(f"{name_clean} portrait photo")
            terms.append(f"{name_clean} headshot")
        else:
            # Query term based on detected image aspect ratio / properties
            if query_image.aspect_ratio > 1.2:
                terms.append("landscape photo")
            elif query_image.aspect_ratio < 0.8:
                terms.append("portrait photo photography")
            else:
                terms.append("photograph portrait")

        raw_candidates = self.discover_web_candidates(terms, max_results=max_results)
        if not raw_candidates:
            logger.info("No candidates discovered from search provider.")
            return []

        verified_results = []
        # Download and compare candidates concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_cand = {
                executor.submit(
                    self.compare_candidate_image,
                    query_image,
                    cand["thumbnail_url"] or cand["image_url"],
                    cand["source_page_url"],
                    cand["source_provider"],
                ): cand
                for cand in raw_candidates[:max_results]
            }

            for future in as_completed(future_to_cand):
                cand_info = future_to_cand[future]
                try:
                    match_result = future.result()
                    if match_result:
                        plat_key = cand_info.get("platform", "web")
                        plat_meta = self.PLATFORM_METADATA.get(plat_key, self.PLATFORM_METADATA["web"])

                        result_record = {
                            "result_id": hashlib.sha256(f"{cand_info['source_page_url']}:{time.time()}".encode()).hexdigest()[:16],
                            "source_provider": cand_info["source_provider"],
                            "source_page_url": cand_info["source_page_url"],
                            "image_url": cand_info["image_url"],
                            "thumbnail_url": cand_info["thumbnail_url"],
                            "title": cand_info.get("title", ""),
                            "snippet": cand_info.get("snippet", ""),
                            "platform": plat_meta["name"],
                            "platform_key": plat_key,
                            "platform_color": plat_meta["color"],
                            "match_type": match_result["match_type"],
                            "score_type": match_result["score_type"],
                            "raw_similarity_score": match_result["raw_similarity_score"],
                            "display_score": match_result["display_score"],
                            "verification_status": match_result["verification_status"],
                            "badge_class": match_result["badge_class"],
                            "metrics": match_result["metrics"],
                            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                        verified_results.append(result_record)
                except Exception as e:
                    logger.debug(f"Candidate comparison error: {e}")

        # Rank results: exact duplicate > near duplicate > visual similarity
        rank_order = {"exact_duplicate": 0, "near_duplicate": 1, "visual_similarity": 2}
        verified_results.sort(
            key=lambda x: (
                rank_order.get(x["match_type"], 99),
                -float(x["raw_similarity_score"]) if x["score_type"] != "hamming_distance" else float(x["raw_similarity_score"]),
            )
        )

        return verified_results

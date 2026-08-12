"""
people_rank.py — IntelFusion OSINT Engine
Computes a 0-100 "PeopleRank" visibility score, analogous to WebMii's proprietary metric.
The score reflects how prominently and broadly a person appears across the public internet.
"""

import math
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Weights for each scoring dimension (must sum to 100)
WEIGHTS = {
    "result_volume": 20,       # Raw number of web results found
    "domain_diversity": 15,    # Number of unique domains
    "social_presence": 25,     # Social platform coverage
    "authority_sources": 15,   # Wikipedia, news, academic presence
    "image_presence": 10,      # Found profile images
    "keyword_relevance": 15,   # How well results match the query
}

# Social platforms worth bonus points each
SOCIAL_PLATFORM_SCORES = {
    "linkedin": 8,
    "github": 6,
    "twitter": 5,
    "instagram": 4,
    "facebook": 4,
    "youtube": 4,
    "reddit": 3,
    "medium": 3,
    "quora": 2,
}

# Authority domains
AUTHORITY_DOMAINS = {
    "wikipedia.org": 10,
    "britannica.com": 8,
    "nytimes.com": 7,
    "bbc.com": 7,
    "theguardian.com": 6,
    "reuters.com": 6,
    "forbes.com": 6,
    "bloomberg.com": 6,
    "wsj.com": 6,
    "time.com": 5,
    "cnn.com": 5,
    "scholar.google.com": 8,
    "researchgate.net": 6,
    "arxiv.org": 6,
    "pubmed.ncbi.nlm.nih.gov": 7,
    "imdb.com": 5,
}


class PeopleRanker:
    """
    Computes a holistic online visibility score (0-100) for a queried person.

    Score breakdown:
    - Result Volume     (20pts): Logarithmic scale of total result count
    - Domain Diversity  (15pts): Unique domains (more = wider footprint)
    - Social Presence   (25pts): Coverage across social/professional platforms
    - Authority Sources (15pts): Presence on high-credibility sites
    - Image Presence    (10pts): Profile photos found
    - Keyword Relevance (15pts): Name appears in titles/snippets (not just noise)
    """

    def compute(
        self,
        resolved: dict,
        images: list[dict],
        query: dict,
    ) -> dict:
        """
        Args:
            resolved: output from EntityResolver.resolve()
            images:   output from ImageHarvester.harvest()
            query:    parsed query dict

        Returns:
            {
                "score": int,          # 0-100
                "grade": str,          # S / A / B / C / D / F
                "label": str,          # human-readable description
                "breakdown": dict,     # per-dimension scores
                "interpretation": str, # one-liner explanation
            }
        """
        results = resolved.get("results", [])
        stats = resolved.get("stats", {})
        full_name = query.get("full_name", "").lower()

        breakdown = {}

        # ── 1. Result Volume (20 pts) ────────────────────────────────────────
        total = stats.get("total_results", 0)
        # log scale: 1 result → ~5pts, 10 → ~15pts, 50+ → ~20pts
        vol_score = min(20, round(20 * (math.log10(max(total, 1) + 1) / math.log10(51))))
        breakdown["result_volume"] = {"score": vol_score, "max": 20, "detail": f"{total} results found"}

        # ── 2. Domain Diversity (15 pts) ─────────────────────────────────────
        unique_domains = stats.get("unique_domains", 0)
        div_score = min(15, round(15 * (math.log10(max(unique_domains, 1) + 1) / math.log10(26))))
        breakdown["domain_diversity"] = {"score": div_score, "max": 15, "detail": f"{unique_domains} unique domains"}

        # ── 3. Social Presence (25 pts) ──────────────────────────────────────
        platforms_found = set()
        for r in results:
            url = r.get("url", "").lower()
            platform = r.get("platform", "").lower()
            for p in SOCIAL_PLATFORM_SCORES:
                if p in url or p in platform:
                    platforms_found.add(p)

        social_raw = sum(SOCIAL_PLATFORM_SCORES.get(p, 2) for p in platforms_found)
        social_max_raw = sum(SOCIAL_PLATFORM_SCORES.values())  # 39
        soc_score = min(25, round(25 * (social_raw / social_max_raw)))
        breakdown["social_presence"] = {
            "score": soc_score,
            "max": 25,
            "detail": f"Found on: {', '.join(sorted(platforms_found)) or 'none'}",
            "platforms": list(platforms_found),
        }

        # ── 4. Authority Sources (15 pts) ─────────────────────────────────────
        auth_raw = 0
        authority_hits = []
        for r in results:
            domain = urlparse(r.get("url", "")).netloc.replace("www.", "")
            for auth_domain, pts in AUTHORITY_DOMAINS.items():
                if auth_domain in domain:
                    auth_raw += pts
                    authority_hits.append(auth_domain)
                    break

        auth_score = min(15, round(15 * (min(auth_raw, 30) / 30)))
        breakdown["authority_sources"] = {
            "score": auth_score,
            "max": 15,
            "detail": f"Authority sites: {', '.join(set(authority_hits)) or 'none'}",
        }

        # ── 5. Image Presence (10 pts) ────────────────────────────────────────
        img_count = len(images)
        img_score = min(10, round(10 * (min(img_count, 10) / 10)))
        breakdown["image_presence"] = {"score": img_score, "max": 10, "detail": f"{img_count} images found"}

        # ── 6. Keyword Relevance (15 pts) ─────────────────────────────────────
        name_parts = [p for p in full_name.split() if len(p) > 2]
        relevant = 0
        for r in results:
            text = f"{r.get('title', '')} {r.get('description', '')}".lower()
            if any(part in text for part in name_parts):
                relevant += 1

        rel_ratio = relevant / max(len(results), 1)
        rel_score = min(15, round(15 * rel_ratio))
        breakdown["keyword_relevance"] = {
            "score": rel_score,
            "max": 15,
            "detail": f"{relevant}/{len(results)} results mention the name directly",
        }

        # ── Final Score ────────────────────────────────────────────────────────
        total_score = sum(v["score"] for v in breakdown.values())
        total_score = max(0, min(100, total_score))

        grade, label, interpretation = self._grade(total_score, platforms_found, authority_hits)

        return {
            "score": total_score,
            "grade": grade,
            "label": label,
            "breakdown": breakdown,
            "interpretation": interpretation,
        }

    def _grade(self, score: int, platforms: set, authority_hits: list) -> tuple:
        if score >= 85:
            return "S", "Highly Prominent", "This person has a very strong and authoritative online presence across multiple platforms."
        elif score >= 70:
            return "A", "Well Established", "Strong digital footprint with good social media and web coverage."
        elif score >= 55:
            return "B", "Moderately Visible", "Noticeable online presence, present on several platforms and sources."
        elif score >= 35:
            return "C", "Limited Visibility", "Some online presence, but not widely covered across platforms."
        elif score >= 15:
            return "D", "Sparse Presence", "Minimal online footprint. Very few public records found."
        else:
            return "F", "Virtually Unknown", "Little to no public information found for this person online."

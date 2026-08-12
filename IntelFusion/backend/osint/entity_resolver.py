"""
entity_resolver.py — IntelFusion OSINT Engine
Deduplicates results, categorises them by source type, generates a TF-IDF tag cloud,
and flags potential homonyms (multiple distinct individuals sharing the same name).
"""

import re
import math
import logging
from collections import Counter
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Common English stop-words to exclude from tag cloud
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "it", "its", "this", "that",
    "these", "those", "i", "we", "you", "he", "she", "they", "his", "her",
    "their", "our", "your", "my", "me", "him", "us", "them", "who", "which",
    "what", "how", "when", "where", "why", "all", "as", "if", "so", "up",
    "out", "no", "not", "com", "www", "http", "https", "page", "profile",
    "about", "more", "also", "than", "other", "into", "through", "during",
    "about", "against", "between", "after", "before", "above", "below",
    "new", "old", "get", "see", "one", "two", "use", "used", "using",
    "home", "click", "here", "search", "find", "view", "read",
}

# Domain-to-category mapping
DOMAIN_CATEGORIES = {
    "github.com": "professional",
    "linkedin.com": "professional",
    "stackoverflow.com": "professional",
    "medium.com": "blog",
    "dev.to": "blog",
    "substack.com": "blog",
    "twitter.com": "social",
    "x.com": "social",
    "facebook.com": "social",
    "instagram.com": "social",
    "reddit.com": "social",
    "quora.com": "social",
    "youtube.com": "social",
    "tiktok.com": "social",
    "wikipedia.org": "reference",
    "britannica.com": "reference",
    "imdb.com": "reference",
    "scholar.google.com": "academic",
    "researchgate.net": "academic",
    "academia.edu": "academic",
    "arxiv.org": "academic",
    "pubmed.ncbi.nlm.nih.gov": "academic",
}


class EntityResolver:
    """
    Post-processes raw OSINT results:
    - Deduplicates by URL
    - Assigns source categories
    - Generates a weighted tag cloud
    - Detects potential homonyms
    """

    def resolve(self, search_results: list[dict], social_results: list[dict], query: dict) -> dict:
        """
        Merges, deduplicates, and enriches all results.

        Returns:
        {
            "results": list[dict],           # all deduplicated results
            "by_category": dict,             # results keyed by category
            "tag_cloud": list[dict],         # [{word, weight, size}]
            "homonym_groups": list[list],    # potentially different people
            "stats": dict,                   # summary statistics
        }
        """
        full_name = query.get("full_name", "").lower()

        # ── 1. Normalise search results to a common schema ──────────────────
        normalised = []
        for r in search_results:
            domain = r.get("domain") or urlparse(r.get("url", "")).netloc.replace("www.", "")
            cat = self._categorise(domain)
            normalised.append({
                "platform": r.get("source", "Web"),
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("snippet", ""),
                "avatar": "",
                "category": cat,
                "icon": self._icon_for_domain(domain),
                "color": "#4caf50",
                "verified": False,
                "extra": {"domain": domain},
                "_is_social": False,
            })

        # Mark social results
        for r in social_results:
            r["_is_social"] = True
            normalised.append(r)

        # ── 2. Deduplicate by URL ────────────────────────────────────────────
        seen_urls = set()
        unique = []
        for r in normalised:
            url = r.get("url", "").rstrip("/").lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        # ── 3. Assign categories to anything still uncategorised ─────────────
        for r in unique:
            if not r.get("category"):
                domain = urlparse(r.get("url", "")).netloc.replace("www.", "")
                r["category"] = self._categorise(domain)

        # ── 4. Group by category ─────────────────────────────────────────────
        by_category = {}
        for r in unique:
            cat = r.get("category", "web")
            by_category.setdefault(cat, []).append(r)

        # ── 5. Build tag cloud from all text ─────────────────────────────────
        tag_cloud = self._build_tag_cloud(unique, full_name)

        # ── 6. Detect homonym groups ──────────────────────────────────────────
        homonym_groups = self._detect_homonyms(unique, full_name)

        # ── 7. Compute stats ─────────────────────────────────────────────────
        stats = {
            "total_results": len(unique),
            "unique_domains": len({urlparse(r.get("url", "")).netloc for r in unique}),
            "categories_found": list(by_category.keys()),
            "social_hits": len([r for r in unique if r.get("_is_social")]),
            "has_wikipedia": any("wikipedia" in r.get("url", "") for r in unique),
            "has_images": False,  # filled by caller after image harvest
        }

        return {
            "results": unique,
            "by_category": by_category,
            "tag_cloud": tag_cloud,
            "homonym_groups": homonym_groups,
            "stats": stats,
        }

    def _categorise(self, domain: str) -> str:
        for key, cat in DOMAIN_CATEGORIES.items():
            if key in domain:
                return cat
        return "news"

    def _icon_for_domain(self, domain: str) -> str:
        domain_icons = {
            "github.com": "github",
            "linkedin.com": "linkedin",
            "twitter.com": "twitter",
            "x.com": "twitter",
            "facebook.com": "facebook",
            "instagram.com": "instagram",
            "youtube.com": "youtube",
            "reddit.com": "reddit",
            "medium.com": "medium",
            "wikipedia.org": "wikipedia",
            "stackoverflow.com": "stackoverflow",
            "quora.com": "quora",
            "arxiv.org": "academic",
            "researchgate.net": "academic",
        }
        for key, icon in domain_icons.items():
            if key in domain:
                return icon
        return "web"

    def _build_tag_cloud(self, results: list[dict], full_name: str) -> list[dict]:
        """
        Generate a weighted tag cloud from titles + snippets using TF-IDF-lite.
        """
        # Collect all text
        documents = []
        for r in results:
            text = f"{r.get('title', '')} {r.get('description', '')}"
            documents.append(text.lower())

        if not documents:
            return []

        # Term frequency across all documents
        all_words = []
        for doc in documents:
            words = re.findall(r"\b[a-z]{3,}\b", doc)
            all_words.extend(words)

        tf = Counter(all_words)

        # Document frequency (in how many docs does this word appear)
        df = Counter()
        for doc in documents:
            words = set(re.findall(r"\b[a-z]{3,}\b", doc))
            for w in words:
                df[w] += 1

        N = len(documents)
        scores = {}
        for word, count in tf.items():
            if word in STOP_WORDS:
                continue
            # Skip parts of the person's name (not meaningful as tags)
            if any(part in word for part in full_name.split() if len(part) > 2):
                continue
            idf = math.log((N + 1) / (df.get(word, 1) + 1)) + 1
            scores[word] = count * idf

        # Top 30 tags, normalised to 1-10 weight range
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:30]
        if not top:
            return []

        max_score = top[0][1]
        min_score = top[-1][1] if len(top) > 1 else 1

        tag_cloud = []
        for word, score in top:
            normalised = (score - min_score) / max(max_score - min_score, 1)
            weight = round(1 + normalised * 9, 1)
            size_px = int(12 + normalised * 26)
            tag_cloud.append({"word": word, "weight": weight, "size": size_px})

        return tag_cloud

    def _detect_homonyms(self, results: list[dict], full_name: str) -> list[list]:
        """
        Simple heuristic: group results by recurring co-occurring keywords.
        Clusters that share < 2 keywords may represent different people.
        """
        # Extract top keywords per result
        name_parts = set(full_name.split())
        groups: list[set] = []
        group_results: list[list] = []

        for r in results:
            text = f"{r.get('title', '')} {r.get('description', '')}".lower()
            words = {w for w in re.findall(r"\b[a-z]{4,}\b", text) if w not in STOP_WORDS and w not in name_parts}
            words = set(list(words)[:10])

            # Try to assign to existing group
            assigned = False
            for i, g in enumerate(groups):
                overlap = len(g & words)
                if overlap >= 2:
                    groups[i].update(words)
                    group_results[i].append(r)
                    assigned = True
                    break

            if not assigned:
                groups.append(words)
                group_results.append([r])

        # Only flag if there are 2+ meaningful groups
        meaningful = [g for g in group_results if len(g) >= 2]
        return meaningful if len(meaningful) > 1 else []

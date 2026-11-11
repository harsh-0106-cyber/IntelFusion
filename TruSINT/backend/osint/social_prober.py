"""
social_prober.py — TruSINT OSINT Engine
Probes public endpoints across major social platforms for a given person.
Uses official public APIs where available; falls back to site-targeted DDG queries.
"""

import os
import time
import random
import requests
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 12))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Platform icons mapped to category
PLATFORM_META = {
    "github": {"icon": "github", "category": "professional", "color": "#6e40c9"},
    "linkedin": {"icon": "linkedin", "category": "professional", "color": "#0077b5"},
    "twitter": {"icon": "twitter", "category": "social", "color": "#1da1f2"},
    "reddit": {"icon": "reddit", "category": "social", "color": "#ff4500"},
    "wikipedia": {"icon": "wikipedia", "category": "reference", "color": "#636466"},
    "youtube": {"icon": "youtube", "category": "social", "color": "#ff0000"},
    "instagram": {"icon": "instagram", "category": "social", "color": "#e1306c"},
    "facebook": {"icon": "facebook", "category": "social", "color": "#1877f2"},
    "medium": {"icon": "medium", "category": "blog", "color": "#00ab6c"},
    "quora": {"icon": "quora", "category": "social", "color": "#b92b27"},
    "pinterest": {"icon": "pinterest", "category": "social", "color": "#e60023"},
    "tiktok": {"icon": "tiktok", "category": "social", "color": "#010101"},
    "snapchat": {"icon": "web", "category": "social", "color": "#fffc00"},
    "mastodon": {"icon": "web", "category": "social", "color": "#6364ff"},
    "gravatar": {"icon": "gravatar", "category": "identity", "color": "#1e8cbe"},
    "web": {"icon": "web", "category": "news", "color": "#4caf50"},
}


class SocialProber:
    """Probes multiple public platforms for a person's digital footprint."""

    def __init__(self):
        self._ddg_searcher = None  # lazy import

    def _ddg(self):
        if not self._ddg_searcher:
            from osint.search_engine import DuckDuckGoSearcher
            self._ddg_searcher = DuckDuckGoSearcher()
        return self._ddg_searcher

    def probe_all(self, query: dict) -> list[dict]:
        """
        Run all platform probes for a parsed query.
        Returns a list of profile/result dicts:
        [{platform, title, url, description, category, icon, color, verified}]
        """
        full_name = query["full_name"]
        keywords = query.get("keywords", [])
        results = []

        probes = [
            self._probe_github,
            self._probe_reddit,
            self._probe_wikipedia,
            self._probe_linkedin,
            self._probe_twitter,
            self._probe_instagram,
            self._probe_facebook,
            self._probe_youtube,
            self._probe_medium,
            self._probe_quora,
            self._probe_pinterest,
            self._probe_tiktok,
            self._probe_snapchat,
            self._probe_mastodon,
        ]

        for probe_fn in probes:
            try:
                found = probe_fn(full_name, keywords)
                results.extend(found)
                time.sleep(random.uniform(0.3, 0.7))
            except Exception as e:
                logger.warning(f"Probe {probe_fn.__name__} failed: {e}")

        return results

    # ─── GitHub (official public API) ─────────────────────────────────────
    def _probe_github(self, name: str, keywords: list) -> list[dict]:
        results = []
        try:
            url = f"https://api.github.com/search/users?q={quote_plus(name)}&per_page=5"
            resp = requests.get(url, headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for user in data.get("items", [])[:5]:
                    # Fetch additional details
                    detail = {}
                    try:
                        dr = requests.get(user["url"], headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=8)
                        if dr.status_code == 200:
                            detail = dr.json()
                    except Exception:
                        pass

                    bio = detail.get("bio") or ""
                    company = detail.get("company") or ""
                    location = detail.get("location") or ""
                    repos = detail.get("public_repos", 0)
                    followers = detail.get("followers", 0)

                    desc_parts = []
                    if bio:
                        desc_parts.append(bio)
                    if company:
                        desc_parts.append(f"Company: {company}")
                    if location:
                        desc_parts.append(f"Location: {location}")
                    if repos:
                        desc_parts.append(f"{repos} public repos · {followers} followers")

                    meta = PLATFORM_META["github"]
                    results.append({
                        "platform": "GitHub",
                        "title": f"@{user['login']} — GitHub",
                        "url": user["html_url"],
                        "description": " | ".join(desc_parts) or "GitHub profile",
                        "avatar": user.get("avatar_url", ""),
                        "category": meta["category"],
                        "icon": meta["icon"],
                        "color": meta["color"],
                        "verified": True,
                        "extra": {
                            "repos": repos,
                            "followers": followers,
                            "location": location,
                        },
                    })
        except Exception as e:
            logger.warning(f"GitHub probe error: {e}")
        return results

    # ─── Reddit (public JSON API) ─────────────────────────────────────────
    def _probe_reddit(self, name: str, keywords: list) -> list[dict]:
        results = []
        try:
            url = f"https://www.reddit.com/search.json?q={quote_plus(name)}&type=user&limit=5"
            resp = requests.get(url, headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                children = data.get("data", {}).get("children", [])
                meta = PLATFORM_META["reddit"]
                for item in children[:3]:
                    d = item.get("data", {})
                    uname = d.get("name", "")
                    if not uname:
                        continue
                    results.append({
                        "platform": "Reddit",
                        "title": f"u/{uname} — Reddit",
                        "url": f"https://www.reddit.com/user/{uname}",
                        "description": f"Reddit user: {uname}",
                        "avatar": d.get("icon_img", ""),
                        "category": meta["category"],
                        "icon": meta["icon"],
                        "color": meta["color"],
                        "verified": False,
                        "extra": {
                            "karma": d.get("total_karma", 0),
                        },
                    })

            # Also search posts/comments mentioning the name
            url2 = f"https://www.reddit.com/search.json?q={quote_plus(name)}&limit=5&sort=relevance"
            resp2 = requests.get(url2, headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp2.status_code == 200:
                data2 = resp2.json()
                for item in data2.get("data", {}).get("children", [])[:3]:
                    d = item.get("data", {})
                    title = d.get("title", "")
                    permalink = d.get("permalink", "")
                    subreddit = d.get("subreddit", "")
                    if title and permalink:
                        meta = PLATFORM_META["reddit"]
                        results.append({
                            "platform": "Reddit",
                            "title": title,
                            "url": f"https://www.reddit.com{permalink}",
                            "description": f"r/{subreddit} · {d.get('score', 0)} points",
                            "avatar": "",
                            "category": "social",
                            "icon": meta["icon"],
                            "color": meta["color"],
                            "verified": False,
                            "extra": {},
                        })
        except Exception as e:
            logger.warning(f"Reddit probe error: {e}")
        return results

    # ─── Wikipedia (MediaWiki API) ─────────────────────────────────────────
    def _probe_wikipedia(self, name: str, keywords: list) -> list[dict]:
        results = []
        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": name,
                "srnamespace": 0,
                "srlimit": 3,
                "format": "json",
                "origin": "*",
            }
            resp = requests.get("https://en.wikipedia.org/w/api.php", params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                meta = PLATFORM_META["wikipedia"]
                for item in data.get("query", {}).get("search", [])[:3]:
                    page_title = item.get("title", "")
                    snippet = item.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
                    results.append({
                        "platform": "Wikipedia",
                        "title": f"{page_title} — Wikipedia",
                        "url": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
                        "description": snippet or "Wikipedia article",
                        "avatar": "",
                        "category": meta["category"],
                        "icon": meta["icon"],
                        "color": meta["color"],
                        "verified": True,
                        "extra": {"word_count": item.get("wordcount", 0)},
                    })
        except Exception as e:
            logger.warning(f"Wikipedia probe error: {e}")
        return results

    # ─── Site-targeted DDG queries for remaining platforms ─────────────────

    def _site_search(self, name: str, site: str, platform: str, keywords: list = None) -> list[dict]:
        """Generic site:X search via DuckDuckGo."""
        kw = f" {keywords[0]}" if keywords else ""
        query = f'"{name}"{kw} site:{site}'
        raw = self._ddg().search(query, max_results=3)
        meta = PLATFORM_META.get(platform.lower(), PLATFORM_META["web"])
        results = []
        for r in raw:
            results.append({
                "platform": platform,
                "title": r["title"],
                "url": r["url"],
                "description": r["snippet"],
                "avatar": "",
                "category": meta["category"],
                "icon": meta["icon"],
                "color": meta["color"],
                "verified": False,
                "extra": {},
            })
        return results

    def _probe_pinterest(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "pinterest.com", "Pinterest", keywords)
        meta = {"category": "social", "icon": "pinterest", "color": "#e60023"}
        for r in results:
            r["icon"] = meta["icon"]
            r["color"] = meta["color"]
        return results

    def _probe_linkedin(self, name: str, keywords: list) -> list[dict]:
        return self._site_search(name, "linkedin.com/in", "LinkedIn", keywords)

    def _probe_twitter(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "x.com", "Twitter/X", keywords)
        # Assign twitter meta properly
        meta = PLATFORM_META["twitter"]
        for r in results:
            r["icon"] = meta["icon"]
            r["color"] = meta["color"]
        return results

    def _probe_instagram(self, name: str, keywords: list) -> list[dict]:
        return self._site_search(name, "instagram.com", "Instagram", keywords)

    def _probe_facebook(self, name: str, keywords: list) -> list[dict]:
        return self._site_search(name, "facebook.com", "Facebook", keywords)

    def _probe_youtube(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "youtube.com", "YouTube", keywords)
        meta = PLATFORM_META["youtube"]
        for r in results:
            r["icon"] = meta["icon"]
            r["color"] = meta["color"]
        return results

    def _probe_medium(self, name: str, keywords: list) -> list[dict]:
        return self._site_search(name, "medium.com", "Medium", keywords)

    def _probe_quora(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "quora.com", "Quora", keywords)
        meta = PLATFORM_META["quora"]
        for r in results:
            r["icon"] = meta["icon"]
            r["color"] = meta["color"]
        return results

    def _probe_tiktok(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "tiktok.com", "TikTok", keywords)
        meta = PLATFORM_META["tiktok"]
        for r in results:
            r["icon"] = meta["icon"]
            r["color"] = meta["color"]
            r["category"] = meta["category"]
        return results

    def _probe_snapchat(self, name: str, keywords: list) -> list[dict]:
        results = self._site_search(name, "snapchat.com", "Snapchat", keywords)
        meta = PLATFORM_META["snapchat"]
        for r in results:
            r["color"] = meta["color"]
            r["category"] = meta["category"]
        return results

    def _probe_mastodon(self, name: str, keywords: list) -> list[dict]:
        """Search Mastodon via mastodon.social's search."""
        results = self._site_search(name, "mastodon.social", "Mastodon", keywords)
        meta = PLATFORM_META["mastodon"]
        for r in results:
            r["color"] = meta["color"]
            r["category"] = meta["category"]
        return results

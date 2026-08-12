"""
comments_finder.py — IntelFusion OSINT Engine
Finds publicly visible comments, posts, and discussions made by or about
a person across major public platforms.

Sources:
  - Reddit: Public search API (comments + posts)
  - Hacker News: Algolia API (free, no key)
  - YouTube: DDG site-targeted search for comments/discussions
  - Disqus: Public DDG search
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
    "User-Agent": "IntelFusion-OSINT/1.0 (educational use)",
    "Accept": "application/json",
}


class CommentsFinder:
    """
    Discovers public comments, discussions, and forum posts associated with a person.
    """

    def find_all(self, query: dict) -> dict:
        """
        Returns:
        {
            "reddit_comments":   list,
            "hn_comments":       list,
            "forum_posts":       list,
            "total_comments":    int,
        }
        """
        full_name = query.get("full_name", "")
        keywords  = query.get("keywords", [])
        work      = query.get("place_of_work", "")

        reddit_comments = self._reddit_comments(full_name)
        reddit_posts    = self._reddit_posts(full_name, keywords)
        hn_comments     = self._hackernews(full_name)
        forum_posts     = self._forum_search(full_name, work)

        all_comments = reddit_comments + reddit_posts + hn_comments + forum_posts

        return {
            "reddit_comments": reddit_comments,
            "reddit_posts":    reddit_posts,
            "hn_comments":     hn_comments,
            "forum_posts":     forum_posts,
            "all_comments":    all_comments[:30],
            "total_comments":  len(all_comments),
        }

    # ── Reddit Comments ─────────────────────────────────────────────────────
    def _reddit_comments(self, name: str) -> list[dict]:
        """Search Reddit for public comments mentioning this person."""
        results = []
        try:
            url = f"https://www.reddit.com/search.json?q={quote_plus(name)}&type=comment&limit=8&sort=relevance"
            resp = requests.get(url, headers={**HEADERS, "User-Agent": "IntelFusion-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", {}).get("children", []):
                    d = item.get("data", {})
                    body = d.get("body", "")
                    if not body or len(body) < 20:
                        continue
                    results.append({
                        "type": "reddit_comment",
                        "platform": "Reddit",
                        "icon": "reddit",
                        "color": "#ff4500",
                        "author": d.get("author", "[deleted]"),
                        "content": body[:500],
                        "url": f"https://www.reddit.com{d.get('permalink', '')}",
                        "subreddit": d.get("subreddit", ""),
                        "score": d.get("score", 0),
                        "created_utc": d.get("created_utc"),
                        "context": f"r/{d.get('subreddit', '')} · {d.get('score', 0)} points",
                    })
        except Exception as e:
            logger.warning(f"Reddit comments error: {e}")
        return results

    # ── Reddit Posts ─────────────────────────────────────────────────────────
    def _reddit_posts(self, name: str, keywords: list = None) -> list[dict]:
        """Search Reddit posts/threads about or by this person."""
        results = []
        try:
            kw = keywords[0] if keywords else ""
            query = f'"{name}" {kw}'.strip()
            url = f"https://www.reddit.com/search.json?q={quote_plus(query)}&type=link&limit=6&sort=relevance"
            resp = requests.get(url, headers={**HEADERS, "User-Agent": "IntelFusion-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", {}).get("children", []):
                    d = item.get("data", {})
                    title = d.get("title", "")
                    if not title:
                        continue
                    selftext = d.get("selftext", "")[:300]
                    results.append({
                        "type": "reddit_post",
                        "platform": "Reddit",
                        "icon": "reddit",
                        "color": "#ff4500",
                        "author": d.get("author", ""),
                        "content": title + (f"\n{selftext}" if selftext else ""),
                        "url": f"https://www.reddit.com{d.get('permalink', '')}",
                        "subreddit": d.get("subreddit", ""),
                        "score": d.get("score", 0),
                        "created_utc": d.get("created_utc"),
                        "num_comments": d.get("num_comments", 0),
                        "context": f"r/{d.get('subreddit', '')} · {d.get('score', 0)} upvotes · {d.get('num_comments', 0)} comments",
                    })
        except Exception as e:
            logger.warning(f"Reddit posts error: {e}")
        return results

    # ── Hacker News (Algolia API) ─────────────────────────────────────────────
    def _hackernews(self, name: str) -> list[dict]:
        """Search Hacker News for mentions using the free Algolia API."""
        results = []
        try:
            # Comments mentioning the person
            url = "https://hn.algolia.com/api/v1/search"
            params = {
                "query": name,
                "tags": "comment",
                "hitsPerPage": 6,
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for hit in hits[:6]:
                    text = hit.get("comment_text", "") or ""
                    if len(text) < 15:
                        continue
                    hn_id = hit.get("objectID", "")
                    results.append({
                        "type": "hn_comment",
                        "platform": "Hacker News",
                        "icon": "web",
                        "color": "#ff6600",
                        "author": hit.get("author", ""),
                        "content": text[:400],
                        "url": f"https://news.ycombinator.com/item?id={hn_id}",
                        "score": hit.get("points", 0),
                        "created_utc": None,
                        "context": f"Hacker News · {hit.get('points', 0) or 0} points",
                    })

            # Also search for stories about this person
            time.sleep(0.3)
            params2 = {"query": name, "tags": "story", "hitsPerPage": 4}
            resp2 = requests.get(url, params=params2, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp2.status_code == 200:
                for hit in resp2.json().get("hits", [])[:4]:
                    hn_id = hit.get("objectID", "")
                    results.append({
                        "type": "hn_story",
                        "platform": "Hacker News",
                        "icon": "web",
                        "color": "#ff6600",
                        "author": hit.get("author", ""),
                        "content": hit.get("title", ""),
                        "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hn_id}",
                        "score": hit.get("points", 0),
                        "created_utc": None,
                        "context": f"HN Story · {hit.get('points', 0) or 0} pts · {hit.get('num_comments', 0) or 0} comments",
                    })
        except Exception as e:
            logger.warning(f"Hacker News error: {e}")
        return results

    # ── Forum / Public Posts via DDG ──────────────────────────────────────────
    def _forum_search(self, name: str, work: str = "") -> list[dict]:
        """
        Search for forum posts and discussions mentioning the person
        via site-targeted DuckDuckGo queries.
        Each site is searched individually (DDG does not support grouped site: syntax).
        """
        results = []
        try:
            from osint.search_engine import DuckDuckGoSearcher
            import time, random
            ddg = DuckDuckGoSearcher()

            # Target popular forums and discussion platforms — search each individually
            sites = [
                ("quora.com",              "Quora"),
                ("stackoverflow.com",      "Stack Overflow"),
                ("news.ycombinator.com",   "Hacker News"),
                ("producthunt.com",        "Product Hunt"),
                ("dev.to",                 "Dev.to"),
            ]

            base_query = f'"{name}"'
            if work:
                base_query += f" {work}"

            for site_domain, site_label in sites:
                try:
                    site_query = f"{base_query} site:{site_domain}"
                    raw = ddg.search(site_query, max_results=2)
                    for r in raw:
                        results.append({
                            "type": "forum_post",
                            "platform": site_label,
                            "icon": "web",
                            "color": "#8b5cf6",
                            "author": "",
                            "content": r.get("title", "") + "\n" + r.get("snippet", "")[:200],
                            "url": r.get("url", ""),
                            "score": 0,
                            "created_utc": None,
                            "context": f"Public Discussion · {site_label}",
                        })
                    time.sleep(random.uniform(0.3, 0.6))
                except Exception as site_err:
                    logger.warning(f"Forum search for {site_domain} failed: {site_err}")
        except Exception as e:
            logger.warning(f"Forum search error: {e}")
        return results

"""
search_engine.py — TruSINT OSINT Engine
Performs live web searches using DuckDuckGo (no API key required) with optional
Google Custom Search fallback if credentials are provided.
"""

import os
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse
import logging

logger = logging.getLogger(__name__)

# Rotate user-agents to reduce blocking
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/125.0.0.0 Safari/537.36",
]

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 12))
MAX_RESULTS = int(os.getenv("MAX_RESULTS_PER_SOURCE", 10))


def _random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


class DuckDuckGoSearcher:
    """Scrapes DuckDuckGo HTML results — no API key needed."""

    BASE_URL = "https://html.duckduckgo.com/html/"

    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[dict]:
        """
        Returns a list of result dicts:
        [{title, url, snippet, source, domain}]
        """
        results = []
        try:
            params = {"q": query, "kl": "us-en", "s": 0}
            resp = requests.post(
                self.BASE_URL,
                data=params,
                headers=_random_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for result in soup.select(".result"):
                title_el = result.select_one(".result__title a")
                snippet_el = result.select_one(".result__snippet")
                url_el = result.select_one(".result__url")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                url = title_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                display_url = url_el.get_text(strip=True) if url_el else url

                # Clean up DDG redirect URLs
                if url.startswith("//duckduckgo.com/l/?uddg="):
                    from urllib.parse import unquote, parse_qs
                    try:
                        qs = parse_qs(url.split("?", 1)[1])
                        url = unquote(qs.get("uddg", [url])[0])
                    except Exception:
                        pass

                domain = urlparse(url).netloc.replace("www.", "")

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": "DuckDuckGo",
                    "domain": domain,
                })

                if len(results) >= max_results:
                    break

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for '{query}': {e}")

        return results


class GoogleCSESearcher:
    """Uses Google Custom Search JSON API if credentials are configured."""

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "")
        self.cse_id = os.getenv("GOOGLE_CSE_ID", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.cse_id)

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        if not self.is_configured():
            return []
        results = []
        try:
            params = {
                "key": self.api_key,
                "cx": self.cse_id,
                "q": query,
                "num": min(max_results, 10),
            }
            resp = requests.get(self.API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                domain = urlparse(item.get("link", "")).netloc.replace("www.", "")
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "Google CSE",
                    "domain": domain,
                })
        except Exception as e:
            logger.warning(f"Google CSE search failed: {e}")

        return results


class SearchEngine:
    """
    Unified search interface. Prefers Google CSE if configured,
    falls back to DuckDuckGo.
    """

    def __init__(self):
        self.ddg = DuckDuckGoSearcher()
        self.google = GoogleCSESearcher()

    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[dict]:
        if self.google.is_configured():
            results = self.google.search(query, max_results)
            if results:
                return results

        # Small delay to be a polite scraper
        time.sleep(random.uniform(0.5, 1.2))
        return self.ddg.search(query, max_results)

    def multi_search(self, queries: list[str], max_per_query: int = 5) -> list[dict]:
        """Run multiple queries and return deduplicated results."""
        seen_urls = set()
        all_results = []

        for query in queries[:4]:  # cap at 4 queries to avoid overloading
            results = self.search(query, max_per_query)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)
            time.sleep(random.uniform(0.8, 1.5))

        return all_results

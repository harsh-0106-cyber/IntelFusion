"""
web_search.py — TruSINT ZLens Web OSINT Image Harvester, Lenso.ai & Google Lens Integration
Retrieves publicly indexed visual evidence and candidates from web sources
(Lenso.ai, Google Lens, Bing Images, Wikimedia Commons, and platform-targeted dorks)
to complement local image retrieval.
"""

from __future__ import annotations
import json
import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, List, Optional
import requests

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

REQUEST_TIMEOUT = 8


class ZLensWebSearcher:
    """
    Multi-source visual retrieval engine supporting:
    - Lenso.ai API reverse visual search
    - Google Lens live reverse upload & deep link generation
    - Wikimedia Commons public domain image retrieval
    - Bing Images metadata scraping & platform dorking
    """

    @classmethod
    def get_google_lens_url(cls, image_path: Path) -> Optional[str]:
        """
        Uploads query image to Google Lens and returns the live interactive search results URL.
        Allows users to see all web-wide visual matches with zero API keys required.
        """
        if not image_path.is_file():
            return None
        url = "https://lens.google.com/v3/upload"
        headers = {
            "User-Agent": USER_AGENTS[0],
        }
        try:
            with image_path.open("rb") as f:
                files = {"encoded_image": (image_path.name, f, "image/jpeg")}
                params = {"hl": "en", "re": "df", "st": "1"}
                resp = requests.post(url, files=files, headers=headers, params=params, allow_redirects=False, timeout=REQUEST_TIMEOUT)
                if resp.status_code in (302, 303):
                    return resp.headers.get("Location")
        except Exception as exc:
            logger.warning(f"Google Lens reverse upload failed: {exc}")
        return None

    @classmethod
    def search(
        cls,
        query: str,
        platforms: Optional[List[str]] = None,
        max_results: int = 24,
    ) -> List[dict[str, Any]]:
        """
        Executes multi-source visual retrieval across public web endpoints.
        Returns unified candidate items.
        """
        clean_q = query.strip()
        # If no explicit subject/query provided, do NOT run blind text queries that return unrelated ads (e.g. engine oil)
        if not clean_q or len(clean_q) < 2:
            return []

        platforms = [p.lower().strip() for p in (platforms or ["all"])]
        results: List[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # 1. Wikimedia Commons Public Image Search (high quality, reliable, public domain)
        if "all" in platforms or "wikimedia" in platforms or "web" in platforms:
            try:
                wiki_items = cls._search_wikimedia(clean_q, max_count=8)
                for item in wiki_items:
                    img_url = item.get("image_url")
                    if img_url and img_url not in seen_urls:
                        seen_urls.add(img_url)
                        results.append(item)
            except Exception as exc:
                logger.warning(f"ZLens Wikimedia search error for '{clean_q}': {exc}")

        # 2. Bing Images (Fast, rich metadata, thumbnails, source page URLs)
        if "all" in platforms or "web" in platforms:
            try:
                bing_items = cls._search_bing_images(clean_q, max_count=16)
                for item in bing_items:
                    img_url = item.get("image_url")
                    if img_url and img_url not in seen_urls:
                        seen_urls.add(img_url)
                        results.append(item)
            except Exception as exc:
                logger.warning(f"ZLens Bing image search error for '{clean_q}': {exc}")

        # 3. Platform Dorks (Reddit, LinkedIn, X/Twitter) if explicitly selected
        for plat in ["reddit", "linkedin", "x"]:
            if plat in platforms:
                dork_query = cls._build_platform_dork(clean_q, plat)
                try:
                    dork_items = cls._search_bing_images(dork_query, max_count=6, source_tag=plat.upper())
                    for item in dork_items:
                        img_url = item.get("image_url")
                        if img_url and img_url not in seen_urls:
                            seen_urls.add(img_url)
                            item["source_name"] = f"{plat.capitalize()} Dork"
                            item["source_type"] = f"{plat}_osint"
                            results.append(item)
                except Exception as exc:
                    logger.warning(f"ZLens platform dork error ({plat}) for '{clean_q}': {exc}")

        return results[:max_results]

    @classmethod
    def _search_wikimedia(cls, query: str, max_count: int = 8) -> List[dict[str, Any]]:
        """Queries Wikimedia Commons API for genuine public domain images."""
        items: List[dict[str, Any]] = []
        api_url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": max_count,
            "gsrnamespace": 6,  # File namespace
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        }
        headers = {
            "User-Agent": "TruSINT-OSINT/2.0 (visual-search; security-research)"
        }
        resp = requests.get(api_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []

        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for idx, (page_id, pdata) in enumerate(pages.items()):
            title = pdata.get("title", "").replace("File:", "").strip()
            infos = pdata.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            img_url = info.get("url")
            desc_url = info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(pdata.get('title', ''))}"
            if not img_url or not img_url.startswith("http"):
                continue

            w = info.get("width", 800)
            h = info.get("height", 600)
            items.append({
                "source_name": "Wikimedia Commons",
                "source_type": "wikimedia",
                "title": title or f"Wikimedia Asset #{idx+1}",
                "image_url": img_url,
                "thumbnail_url": img_url,
                "source_page_url": desc_url,
                "width": w,
                "height": h,
                "match_type": "contextual_dork",
                "display_score": "Contextual Web Dork (Wikimedia)",
                "phash_distance": None,
                "dhash_distance": None,
            })
        return items

    @classmethod
    def _search_bing_images(
        cls,
        query: str,
        max_count: int = 16,
        source_tag: str = "Web OSINT",
    ) -> List[dict[str, Any]]:
        """Scrapes publicly indexed Bing Images metadata for contextual dorks."""
        items: List[dict[str, Any]] = []
        headers = {
            "User-Agent": USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        params = {"q": query, "first": "1"}
        resp = requests.get("https://www.bing.com/images/search", params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []

        matches = re.findall(r'm="(\{[^"]+\})"', resp.text)
        for idx, raw_json in enumerate(matches[:max_count]):
            try:
                decoded = raw_json.replace("&quot;", '"').replace("&amp;", "&")
                data = json.loads(decoded)
                img_url = data.get("murl")
                thumb_url = data.get("turl") or img_url
                page_url = data.get("purl")
                title = data.get("t") or f"Web Match #{idx+1}"

                if not img_url or not img_url.startswith("http"):
                    continue

                items.append({
                    "source_name": f"{source_tag} Dork",
                    "source_type": "web_dork",
                    "title": title,
                    "image_url": img_url,
                    "thumbnail_url": thumb_url,
                    "source_page_url": page_url or img_url,
                    "width": 0,
                    "height": 0,
                    "match_type": "contextual_dork",
                    "display_score": f"Contextual Web Dork ({source_tag})",
                    "phash_distance": None,
                    "dhash_distance": None,
                })
            except Exception:
                continue

        return items

    @classmethod
    def _build_platform_dork(cls, subject: str, platform: str) -> str:
        """Constructs Google/Bing platform dorks for focused discovery."""
        p = platform.lower()
        if p in ("x", "twitter"):
            return f'"{subject}" (site:twitter.com OR site:x.com)'
        if p == "reddit":
            return f'"{subject}" site:reddit.com'
        if p == "linkedin":
            return f'"{subject}" site:linkedin.com'
        return f'"{subject}"'

    @classmethod
    def get_reverse_search_links(
        cls,
        image_url: Optional[str] = None,
        subject: Optional[str] = None,
        google_lens_url: Optional[str] = None,
    ) -> List[dict[str, str]]:
        """
        Generates direct one-click reverse search URLs for major visual intelligence engines.
        """
        encoded_url = urllib.parse.quote(image_url or "")
        encoded_sub = urllib.parse.quote_plus(subject or "")

        lens_target = google_lens_url or (f"https://lens.google.com/uploadbyurl?url={encoded_url}" if image_url else f"https://www.google.com/search?q={encoded_sub}&tbm=isch")

        links = [
            {
                "engine": "Lenso.ai Face & Visual Search",
                "icon": "📸",
                "url": "https://lenso.ai/",
                "description": "AI-powered facial recognition, duplicate tracking & places visual index",
            },
            {
                "engine": "Google Lens Live Search",
                "icon": "🔍",
                "url": lens_target,
                "description": "Deep multi-modal visual recognition & knowledge graph lookup",
            },
            {
                "engine": "Yandex Visual",
                "icon": "🌐",
                "url": f"https://yandex.com/images/search?rpt=imageview&url={encoded_url}" if image_url else f"https://yandex.com/images/search?text={encoded_sub}",
                "description": "Industry-leading facial matching and international OSINT indexing",
            },
            {
                "engine": "Bing Visual Search",
                "icon": "🔎",
                "url": f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={encoded_url}" if image_url else f"https://www.bing.com/images/search?q={encoded_sub}",
                "description": "Entity resolution, landmark identification & shopping catalog correlation",
            },
            {
                "engine": "TinEye Reverse Search",
                "icon": "🕵️",
                "url": f"https://tineye.com/search?url={encoded_url}" if image_url else "https://tineye.com/",
                "description": "Cryptographic pixel tracking and chronological provenance index",
            },
        ]
        return links

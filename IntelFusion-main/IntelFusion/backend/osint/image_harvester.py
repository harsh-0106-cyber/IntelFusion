"""
image_harvester.py — IntelFusion OSINT Engine
Harvests publicly available images associated with a person's name
using DuckDuckGo's image search public endpoint.
"""

import os
import time
import random
import requests
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 12))


class ImageHarvester:
    """Fetches publicly indexed images associated with a name."""

    DDG_IMAGE_TOKEN_URL = "https://duckduckgo.com/"
    DDG_IMAGE_API_URL = "https://duckduckgo.com/i.js"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    ]

    def harvest(self, full_name: str, max_images: int = 12) -> list[dict]:
        """
        Returns a list of image dicts:
        [{url, thumbnail, title, source_url, width, height}]
        """
        images = []

        try:
            # Step 1: Get vqd token from DuckDuckGo
            token = self._get_vqd_token(full_name)
            if not token:
                logger.warning("Could not retrieve DDG image search token")
                return []

            # Step 2: Fetch images using the token
            headers = {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Referer": "https://duckduckgo.com/",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }

            params = {
                "l": "us-en",
                "o": "json",
                "q": full_name,
                "vqd": token,
                "f": ",,,,,",
                "p": "1",
            }

            time.sleep(random.uniform(0.5, 1.0))
            resp = requests.get(
                self.DDG_IMAGE_API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", [])[:max_images]:
                    images.append({
                        "url": item.get("image", ""),
                        "thumbnail": item.get("thumbnail", item.get("image", "")),
                        "title": item.get("title", ""),
                        "source_url": item.get("url", ""),
                        "width": item.get("width", 0),
                        "height": item.get("height", 0),
                    })

        except Exception as e:
            logger.warning(f"Image harvest failed for '{full_name}': {e}")

        # Filter out broken/empty URLs
        images = [img for img in images if img.get("url") and img["url"].startswith("http")]

        return images[:max_images]

    def _get_vqd_token(self, query: str) -> str | None:
        """Retrieves the vqd token required by DDG image search."""
        try:
            headers = {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,*/*",
            }
            resp = requests.get(
                self.DDG_IMAGE_TOKEN_URL,
                params={"q": query},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            # vqd token is embedded in page source as: vqd='4-...'
            import re
            match = re.search(r"vqd['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", resp.text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning(f"VQD token fetch failed: {e}")
        return None

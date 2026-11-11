"""
account_linker.py — TruSINT OSINT Engine
Performs cross-platform username enumeration inspired by Sherlock.
Given a person's name, derives probable usernames and probes 30+ platforms
to find linked accounts, building a connected identity graph.
"""

import os
import time
import random
import requests
import logging
import hashlib
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 8))

# Platform URL templates — {username} is substituted
PLATFORM_TEMPLATES = [
    {"name": "GitHub",         "url": "https://github.com/{username}",                          "icon": "github",      "color": "#6e40c9", "category": "professional"},
    {"name": "LinkedIn",       "url": "https://www.linkedin.com/in/{username}",                  "icon": "linkedin",    "color": "#0077b5", "category": "professional"},
    {"name": "Twitter/X",      "url": "https://x.com/{username}",                               "icon": "twitter",     "color": "#1da1f2", "category": "social"},
    {"name": "Instagram",      "url": "https://www.instagram.com/{username}/",                   "icon": "instagram",   "color": "#e1306c", "category": "social"},
    {"name": "Reddit",         "url": "https://www.reddit.com/user/{username}",                 "icon": "reddit",      "color": "#ff4500", "category": "social"},
    {"name": "Medium",         "url": "https://medium.com/@{username}",                         "icon": "medium",      "color": "#00ab6c", "category": "blog"},
    {"name": "Dev.to",         "url": "https://dev.to/{username}",                              "icon": "web",         "color": "#0a0a0a", "category": "blog"},
    {"name": "Hashnode",       "url": "https://hashnode.com/@{username}",                       "icon": "web",         "color": "#2962ff", "category": "blog"},
    {"name": "Pinterest",      "url": "https://www.pinterest.com/{username}/",                  "icon": "pinterest",   "color": "#e60023", "category": "social"},
    {"name": "Twitch",         "url": "https://www.twitch.tv/{username}",                       "icon": "web",         "color": "#9147ff", "category": "social"},
    {"name": "YouTube",        "url": "https://www.youtube.com/@{username}",                    "icon": "youtube",     "color": "#ff0000", "category": "social"},
    {"name": "TikTok",         "url": "https://www.tiktok.com/@{username}",                     "icon": "web",         "color": "#010101", "category": "social"},
    {"name": "Quora",          "url": "https://www.quora.com/profile/{username}",               "icon": "quora",       "color": "#b92b27", "category": "social"},
    {"name": "HackerNews",     "url": "https://news.ycombinator.com/user?id={username}",        "icon": "web",         "color": "#ff6600", "category": "professional"},
    {"name": "Stack Overflow", "url": "https://stackoverflow.com/users/{username}",             "icon": "stackoverflow","color": "#f48024", "category": "professional"},
    {"name": "GitLab",         "url": "https://gitlab.com/{username}",                          "icon": "web",         "color": "#fc6d26", "category": "professional"},
    {"name": "Bitbucket",      "url": "https://bitbucket.org/{username}/",                      "icon": "web",         "color": "#0052cc", "category": "professional"},
    {"name": "Keybase",        "url": "https://keybase.io/{username}",                          "icon": "web",         "color": "#ff6f21", "category": "identity"},
    {"name": "Gravatar",       "url": "https://en.gravatar.com/{username}",                     "icon": "gravatar",    "color": "#1e8cbe", "category": "identity"},
    {"name": "Patreon",        "url": "https://www.patreon.com/{username}",                     "icon": "web",         "color": "#f96854", "category": "social"},
    {"name": "Behance",        "url": "https://www.behance.net/{username}",                     "icon": "web",         "color": "#053eff", "category": "professional"},
    {"name": "Dribbble",       "url": "https://dribbble.com/{username}",                        "icon": "web",         "color": "#ea4c89", "category": "professional"},
    {"name": "Flickr",         "url": "https://www.flickr.com/people/{username}/",              "icon": "web",         "color": "#ff0084", "category": "social"},
    {"name": "Snapchat",       "url": "https://www.snapchat.com/add/{username}",                "icon": "web",         "color": "#fffc00", "category": "social"},
    {"name": "SoundCloud",     "url": "https://soundcloud.com/{username}",                      "icon": "web",         "color": "#ff5500", "category": "social"},
    {"name": "Spotify",        "url": "https://open.spotify.com/user/{username}",               "icon": "web",         "color": "#1db954", "category": "social"},
    {"name": "Kaggle",         "url": "https://www.kaggle.com/{username}",                      "icon": "academic",    "color": "#20beff", "category": "academic"},
    {"name": "ResearchGate",   "url": "https://www.researchgate.net/profile/{username}",        "icon": "academic",    "color": "#00d0af", "category": "academic"},
    {"name": "Academia.edu",   "url": "https://independent.academia.edu/{username}",            "icon": "academic",    "color": "#41873f", "category": "academic"},
    {"name": "ProductHunt",    "url": "https://www.producthunt.com/@{username}",                "icon": "web",         "color": "#da552f", "category": "professional"},
]

# HTTP success indicators per platform
# 200 = definitely exists, 404 = definitely not, others = uncertain
NOT_FOUND_INDICATORS = ["not found", "doesn't exist", "page not found", "user not found", "no user", "404"]


class AccountLinker:
    """
    Derives probable usernames from a person's name and probes platforms
    to discover linked accounts across the internet.
    """

    def derive_usernames(self, first: str, last: str, keywords: list = None) -> list[str]:
        """Generate a list of probable username variants from name parts."""
        first = first.lower().strip().replace(" ", "")
        last  = last.lower().strip().replace(" ", "")

        if not first and not last:
            return []

        candidates = []

        if first and last:
            candidates += [
                f"{first}{last}",           # elon musk → elonmusk
                f"{first}.{last}",          # elon.musk
                f"{first}_{last}",          # elon_musk
                f"{first[0]}{last}",        # emusk
                f"{first[0]}.{last}",       # e.musk
                f"{first[0]}_{last}",       # e_musk
                f"{first}{last[0]}",        # elonm
                f"{last}{first}",           # muskelon
                f"{last}.{first}",          # musk.elon
                f"{last}_{first}",          # musk_elon
                f"{first}",                 # elon
                f"{last}",                  # musk
                f"{first}{last[0:3]}",      # elonmus
                f"{first[0:4]}{last[0:4]}", # elonmusk (trimmed)
            ]
        elif first:
            candidates += [first, f"{first}1", f"{first}_official"]
        elif last:
            candidates += [last, f"{last}1"]

        # Remove duplicates, preserve order
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen and len(c) >= 3:
                seen.add(c)
                unique.append(c)

        return unique[:8]  # Top 8 candidates

    def probe_platforms(self, usernames: list[str]) -> list[dict]:
        """
        For each username variant, probe all platforms concurrently using threads.
        Returns list of found accounts.
        """
        import concurrent.futures

        found_accounts = []
        lock = __import__('threading').Lock()

        def check_account(platform: dict, username: str):
            url = platform["url"].format(username=username)
            try:
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                        "Accept": "text/html,*/*",
                    },
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                # Check if the page actually exists
                if resp.status_code == 200:
                    # Verify content doesn't indicate "not found"
                    body_lower = resp.text[:2000].lower()
                    if not any(ind in body_lower for ind in NOT_FOUND_INDICATORS):
                        with lock:
                            found_accounts.append({
                                "platform": platform["name"],
                                "username": username,
                                "url": url,
                                "icon": platform["icon"],
                                "color": platform["color"],
                                "category": platform["category"],
                                "title": f"{platform['name']} — @{username}",
                                "description": f"Account found: {url}",
                                "verified": False,
                                "confidence": "medium",
                            })
            except Exception:
                pass

        # Limit concurrent checks to avoid overwhelming servers
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for username in usernames[:5]:  # Top 5 username variants
                for platform in PLATFORM_TEMPLATES:
                    futures.append(executor.submit(check_account, platform, username))
                    time.sleep(0.01)  # tiny stagger

            # Wait for all with a timeout
            concurrent.futures.wait(futures, timeout=25)

        # Deduplicate by platform (keep best match)
        by_platform = {}
        for acc in found_accounts:
            p = acc["platform"]
            if p not in by_platform:
                by_platform[p] = acc

        return list(by_platform.values())

    def gravatar_lookup(self, email: str) -> dict | None:
        """Check Gravatar for a known email address."""
        if not email:
            return None
        try:
            email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
            url = f"https://www.gravatar.com/{email_hash}.json"
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                entry = data.get("entry", [{}])[0]
                return {
                    "platform": "Gravatar",
                    "username": entry.get("preferredUsername", ""),
                    "url": f"https://gravatar.com/{email_hash}",
                    "display_name": entry.get("displayName", ""),
                    "about": entry.get("aboutMe", ""),
                    "accounts": entry.get("accounts", []),
                    "icon": "gravatar",
                    "color": "#1e8cbe",
                }
        except Exception as e:
            logger.warning(f"Gravatar lookup error: {e}")
        return None

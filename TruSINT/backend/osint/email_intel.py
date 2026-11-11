"""
email_intel.py - LookMeUp Email Intelligence Engine
Performs comprehensive reverse email lookup using multiple free sources and techniques.

Techniques used:
  - Email pattern analysis (name extraction, domain parsing)
  - DNS / MX record resolution (email provider detection)
  - HaveIBeenPwned public API (breach intelligence)
  - Gravatar profile lookup (identity + avatar)
  - GitHub API (account association by email)
  - DuckDuckGo dorking (web footprint)
  - Social media username correlation
  - Clearbit Logo API (domain branding)
  - EmailRep.io public API (reputation)
  - WHOIS / RDAP (domain registration info)
  - Reddit public API search
"""

import re
import socket
import hashlib
import logging
import time
import json
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

TIMEOUT = 8
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))

class EmailIntel:
    """Orchestrates all email intelligence gathering modules."""

    def analyze_pattern(self, email: str) -> dict:
        local, domain = email.lower().split("@", 1)
        separators = re.split(r"[._\-+]", local)
        parts = [p for p in separators if p and not p.isdigit()]
        first_name = parts[0].capitalize() if len(parts) >= 1 else ""
        last_name  = parts[1].capitalize() if len(parts) >= 2 else ""
        full_name  = f"{first_name} {last_name}".strip()

        generic_keywords = {
            "info", "contact", "admin", "support", "hello", "mail", "team",
            "no-reply", "noreply", "help", "sales", "jobs", "hr", "careers",
            "billing", "office", "newsletter", "donotreply", "webmaster",
        }
        is_generic = local.lower() in generic_keywords or any(
            kw in local.lower() for kw in generic_keywords
        )
        tld_parts = domain.split(".")
        tld = "." + tld_parts[-1] if tld_parts else ""
        domain_name = tld_parts[0] if tld_parts else domain

        return {
            "email": email, "local_part": local, "domain": domain,
            "domain_name": domain_name, "tld": tld,
            "first_name": first_name, "last_name": last_name,
            "full_name": full_name, "is_generic": is_generic,
            "separators": separators, "name_parts": parts,
        }

    def analyze_domain(self, domain: str) -> dict:
        result = {
            "domain": domain, "mx_records": [], "a_records": [],
            "provider": "Unknown", "provider_icon": "email",
            "is_disposable": False, "is_corporate": False,
        }
        PROVIDER_MAP = {
            "google": ("Google / Gmail", "gmail"), "googlemail": ("Google / Gmail", "gmail"),
            "gmail": ("Google / Gmail", "gmail"), "yahoo": ("Yahoo Mail", "yahoo"),
            "hotmail": ("Microsoft Outlook / Hotmail", "microsoft"),
            "outlook": ("Microsoft Outlook", "microsoft"), "microsoft": ("Microsoft 365", "microsoft"),
            "office365": ("Microsoft 365", "microsoft"), "protection.outlook": ("Microsoft 365", "microsoft"),
            "zoho": ("Zoho Mail", "zoho"), "mailgun": ("Mailgun (Transactional)", "mailgun"),
            "sendgrid": ("SendGrid (Transactional)", "sendgrid"),
            "amazon": ("Amazon SES (AWS)", "amazon"), "amazonses": ("Amazon SES (AWS)", "amazon"),
            "protonmail": ("ProtonMail (Encrypted)", "protonmail"),
            "icloud": ("Apple iCloud Mail", "apple"), "apple": ("Apple Mail", "apple"),
            "fastmail": ("Fastmail", "fastmail"), "mimecast": ("Mimecast (Security Gateway)", "mimecast"),
            "barracuda": ("Barracuda (Security Gateway)", "barracuda"),
        }
        DISPOSABLE = {
            "mailinator.com", "guerrillamail.com", "10minutemail.com",
            "throwaway.email", "yopmail.com", "trashmail.com", "sharklasers.com",
            "spam4.me", "tempmail.com", "dispostable.com", "maildrop.cc",
        }
        if domain in DISPOSABLE:
            result["is_disposable"] = True
            result["provider"] = "Disposable / Temporary Email"
            result["provider_icon"] = "disposable"
        try:
            import dns.resolver
            mx_records = dns.resolver.resolve(domain, "MX")
            for mx in mx_records:
                mx_str = str(mx.exchange).rstrip(".")
                result["mx_records"].append({"priority": mx.preference, "host": mx_str})
                mx_lower = mx_str.lower()
                for key, (name, icon) in PROVIDER_MAP.items():
                    if key in mx_lower:
                        result["provider"] = name
                        result["provider_icon"] = icon
                        break
        except Exception:
            domain_lower = domain.lower()
            for key, (name, icon) in PROVIDER_MAP.items():
                if key in domain_lower:
                    result["provider"] = name
                    result["provider_icon"] = icon
                    break
        free_domains = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "icloud.com", "protonmail.com", "mail.com", "aol.com",
            "live.com", "msn.com", "ymail.com", "me.com",
        }
        if domain not in free_domains and not result["is_disposable"]:
            result["is_corporate"] = True
        return result

    def lookup_gravatar(self, email: str) -> dict:
        email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        avatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=404&s=200"
        profile_url = f"https://www.gravatar.com/{email_hash}.json"
        result = {
            "has_gravatar": False, "avatar_url": None,
            "display_name": None, "profile_url": None,
            "bio": None, "accounts": [], "urls": [],
        }
        try:
            resp = SESSION.get(profile_url, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                entry = data.get("entry", [{}])[0]
                result.update({
                    "has_gravatar": True, "avatar_url": avatar_url,
                    "display_name": entry.get("displayName"),
                    "profile_url": entry.get("profileUrl"),
                    "bio": entry.get("aboutMe"),
                    "accounts": [{"shortname": a.get("shortname"), "url": a.get("url")}
                                  for a in entry.get("accounts", [])],
                    "urls": [{"title": u.get("title"), "value": u.get("value")}
                              for u in entry.get("urls", [])],
                    "name_components": entry.get("name", {}),
                })
        except Exception as e:
            logger.debug(f"Gravatar JSON failed: {e}")
        if not result["has_gravatar"]:
            try:
                r = SESSION.head(avatar_url, timeout=5)
                if r.status_code == 200:
                    result["has_gravatar"] = True
                    result["avatar_url"] = avatar_url
            except Exception:
                pass
        return result

    def check_breaches(self, email: str) -> dict:
        result = {
            "breached": False, "breach_count": 0, "breaches": [],
            "pastes": 0, "note": "",
        }
        try:
            url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote_plus(email)}"
            resp = SESSION.get(url, headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=TIMEOUT)
            if resp.status_code == 200:
                breaches = resp.json()
                result["breached"] = True
                result["breach_count"] = len(breaches)
                result["breaches"] = [
                    {
                        "name": b.get("Name"), "title": b.get("Title"),
                        "domain": b.get("Domain"), "date": b.get("BreachDate"),
                        "pwn_count": b.get("PwnCount"), "data_classes": b.get("DataClasses", []),
                    }
                    for b in breaches[:20]
                ]
            elif resp.status_code == 404:
                result["note"] = "No breaches found in HIBP database"
            elif resp.status_code == 401:
                result["note"] = "HIBP API key required for full breach lookup"
            elif resp.status_code == 429:
                result["note"] = "HIBP rate limit reached; try again later"
        except Exception as e:
            logger.debug(f"HIBP check failed: {e}")
            result["note"] = "Breach check service unavailable"
        return result

    def lookup_github(self, email: str, name: str = "") -> dict:
        result = {
            "found": False, "username": None, "profile_url": None,
            "name": None, "bio": None, "avatar_url": None,
            "public_repos": 0, "followers": 0, "location": None,
            "company": None, "blog": None, "created_at": None,
        }
        headers = {"Accept": "application/vnd.github.v3+json"}
        try:
            search_url = f"https://api.github.com/search/users?q={quote_plus(email)}+in:email"
            resp = SESSION.get(search_url, timeout=TIMEOUT, headers=headers)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    user_resp = SESSION.get(items[0]["url"], timeout=TIMEOUT, headers=headers)
                    if user_resp.status_code == 200:
                        u = user_resp.json()
                        result.update({
                            "found": True, "username": u.get("login"),
                            "profile_url": u.get("html_url"), "name": u.get("name"),
                            "bio": u.get("bio"), "avatar_url": u.get("avatar_url"),
                            "public_repos": u.get("public_repos", 0),
                            "followers": u.get("followers", 0),
                            "location": u.get("location"), "company": u.get("company"),
                            "blog": u.get("blog"),
                            "created_at": u.get("created_at", "")[:10] if u.get("created_at") else None,
                        })
                        return result
            if name and not result["found"]:
                search_url2 = f"https://api.github.com/search/users?q={quote_plus(name)}&per_page=3"
                resp2 = SESSION.get(search_url2, timeout=TIMEOUT, headers=headers)
                if resp2.status_code == 200:
                    items2 = resp2.json().get("items", [])
                    if items2:
                        user_resp = SESSION.get(items2[0]["url"], timeout=TIMEOUT, headers=headers)
                        if user_resp.status_code == 200:
                            u = user_resp.json()
                            result.update({
                                "found": True, "username": u.get("login"),
                                "profile_url": u.get("html_url"), "name": u.get("name"),
                                "bio": u.get("bio"), "avatar_url": u.get("avatar_url"),
                                "public_repos": u.get("public_repos", 0),
                                "followers": u.get("followers", 0),
                                "location": u.get("location"), "company": u.get("company"),
                                "blog": u.get("blog"),
                                "created_at": u.get("created_at", "")[:10] if u.get("created_at") else None,
                            })
        except Exception as e:
            logger.debug(f"GitHub lookup failed: {e}")
        return result

    def dork_search(self, email: str, name: str = "") -> list:
        queries = [f'"{email}"']
        if name:
            queries.append(f'"{name}" "{email.split("@")[0]}"')
        queries += [
            f'"{email}" site:linkedin.com',
            f'"{email}" profile',
        ]
        results = []
        seen_urls = set()
        for query in queries[:3]:
            try:
                url = f"https://duckduckgo.com/html/?q={quote_plus(query)}&kl=us-en"
                resp = SESSION.get(url, timeout=TIMEOUT, headers={"Accept": "text/html"})
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                links = soup.select(".result__a")
                snippets = soup.select(".result__snippet")
                for i, link in enumerate(links[:5]):
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)
                    snippet_text = snippets[i].get_text(strip=True) if i < len(snippets) else ""
                    domain = ""
                    try:
                        domain = urlparse(href).netloc.replace("www.", "")
                    except Exception:
                        pass
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": href, "domain": domain,
                        "snippet": snippet_text,
                        "category": self._categorize_url(href),
                        "source": "web_dork", "query": query,
                    })
                time.sleep(0.4)
            except Exception as e:
                logger.debug(f"Dork query failed: {e}")
        return results

    def _categorize_url(self, url: str) -> str:
        u = url.lower()
        if "linkedin" in u: return "professional"
        if "github" in u: return "developer"
        if "twitter" in u or "x.com" in u: return "social"
        if "instagram" in u or "facebook" in u or "reddit" in u: return "social"
        if "medium" in u: return "blog"
        if "youtube" in u: return "video"
        if "researchgate" in u or "scholar" in u or "academia" in u: return "academic"
        if "stackoverflow" in u: return "developer"
        return "web"

    def correlate_social(self, local_part: str, name: str = "") -> list:
        platforms = [
            ("GitHub",      "https://github.com/{u}",           "github"),
            ("Twitter/X",   "https://twitter.com/{u}",          "twitter"),
            ("Instagram",   "https://www.instagram.com/{u}/",   "instagram"),
            ("Reddit",      "https://www.reddit.com/user/{u}/", "reddit"),
            ("Medium",      "https://medium.com/@{u}",          "medium"),
            ("Dev.to",      "https://dev.to/{u}",               "devto"),
            ("HackerNews",  "https://news.ycombinator.com/user?id={u}", "hackernews"),
        ]
        candidates = [local_part]
        cleaned = re.sub(r"[^a-z0-9]", "", local_part.lower())
        if cleaned and cleaned != local_part:
            candidates.append(cleaned)
        found = []
        for platform, url_tpl, icon in platforms:
            for uname in candidates:
                url = url_tpl.format(u=uname)
                try:
                    r = SESSION.get(url, timeout=6, allow_redirects=True)
                    if r.status_code == 200 and len(r.content) > 500:
                        text_lower = r.text.lower()
                        not_found_signals = [
                            "page not found", "user not found", "profile not found",
                            "does not exist", "404", "no user found", "sorry, this page",
                        ]
                        if not any(sig in text_lower[:2000] for sig in not_found_signals):
                            found.append({
                                "platform": platform, "url": url,
                                "username": uname, "icon": icon,
                                "category": "social", "confidence": "medium",
                            })
                            break
                except Exception:
                    pass
        return found

    def check_reputation(self, email: str) -> dict:
        result = {"reputation": "unknown", "suspicious": False, "references": 0, "details": {}}
        try:
            resp = SESSION.get(
                f"https://emailrep.io/{quote_plus(email)}",
                headers={"User-Agent": "TruSINT-OSINT/1.0"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                result["reputation"] = data.get("reputation", "unknown")
                result["suspicious"] = data.get("suspicious", False)
                result["references"] = data.get("references", 0)
                details = data.get("details", {})
                result["details"] = {
                    "blacklisted": details.get("blacklisted", False),
                    "malicious_activity": details.get("malicious_activity", False),
                    "credentials_leaked": details.get("credentials_leaked", False),
                    "data_breach": details.get("data_breach", False),
                    "free_provider": details.get("free_provider", False),
                    "disposable": details.get("disposable", False),
                    "deliverable": details.get("deliverable", False),
                    "days_since_seen": details.get("days_since_seen"),
                    "first_seen": details.get("first_seen"),
                    "last_seen": details.get("last_seen"),
                    "spam": details.get("spam", False),
                    "spoofable": details.get("spoofable", False),
                    "profiles": details.get("profiles", []),
                }
        except Exception as e:
            logger.debug(f"EmailRep check failed: {e}")
        return result

    def search_reddit(self, email: str, name: str = "") -> list:
        results = []
        queries = [f'"{email}"']
        if name:
            queries.append(f'"{name}"')
        for q in queries[:2]:
            try:
                url = f"https://www.reddit.com/search.json?q={quote_plus(q)}&sort=relevance&limit=5"
                resp = SESSION.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})
                if resp.status_code == 200:
                    posts = resp.json().get("data", {}).get("children", [])
                    for post in posts:
                        p = post.get("data", {})
                        results.append({
                            "title": p.get("title", ""),
                            "url": f"https://reddit.com{p.get('permalink', '')}",
                            "subreddit": p.get("subreddit_name_prefixed", ""),
                            "score": p.get("score", 0),
                            "snippet": p.get("selftext", "")[:300],
                            "platform": "Reddit", "icon": "reddit", "category": "social",
                        })
            except Exception as e:
                logger.debug(f"Reddit search failed: {e}")
        return results

    def lookup_domain_whois(self, domain: str) -> dict:
        result = {
            "registrar": None, "created": None, "expires": None,
            "updated": None, "org": None, "country": None, "name_servers": [],
        }
        try:
            rdap_url = f"https://rdap.verisign.com/com/v1/domain/{domain}"
            resp = SESSION.get(rdap_url, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                events = {e["eventAction"]: e["eventDate"] for e in data.get("events", [])}
                result["created"] = events.get("registration", "")[:10] if events.get("registration") else None
                result["expires"] = events.get("expiration", "")[:10] if events.get("expiration") else None
                result["updated"] = events.get("last changed", "")[:10] if events.get("last changed") else None
                for entity in data.get("entities", []):
                    if "registrar" in entity.get("roles", []):
                        vcard = entity.get("vcardArray", [None, []])[1]
                        for field in vcard:
                            if field[0] == "fn":
                                result["registrar"] = field[3]
                                break
                result["name_servers"] = [ns.get("ldhName", "") for ns in data.get("nameservers", [])[:4]]
        except Exception as e:
            logger.debug(f"WHOIS lookup failed: {e}")
        return result

    def generate_usernames(self, first: str, last: str, local: str) -> list:
        candidates = set()
        if local:
            candidates.add(local)
            candidates.add(local.lower())
        if first and last:
            f = first.lower()
            l = last.lower()
            candidates.update([
                f"{f}{l}", f"{f}.{l}", f"{f}_{l}", f"{f}-{l}",
                f"{f}{l[0]}", f"{f[0]}{l}", f"{f[0]}.{l}", f"{f[0]}_{l}",
                f"{l}{f}", f"{l}.{f}", f"{l}_{f}", f"{f}", f"{l}",
            ])
        return sorted(list(candidates))[:12]

    def get_profile_photos(self, email: str, domain: str) -> list:
        photos = []
        email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=404&s=200"
        try:
            r = SESSION.head(gravatar_url, timeout=5)
            if r.status_code == 200:
                photos.append({"source": "Gravatar", "url": gravatar_url})
        except Exception:
            pass
        logo_url = f"https://logo.clearbit.com/{domain}?size=200"
        try:
            r = SESSION.head(logo_url, timeout=5)
            if r.status_code == 200:
                photos.append({"source": f"{domain} Logo", "url": logo_url})
        except Exception:
            pass
        return photos

    def investigate(self, email: str) -> dict:
        """Run all intelligence gathering and return consolidated report."""
        email = email.strip().lower()
        if not is_valid_email(email):
            return {"error": "Invalid email address format"}

        report = {
            "email": email, "timestamp": time.time(),
            "pattern": {}, "domain_intel": {}, "gravatar": {},
            "github": {}, "reputation": {}, "breaches": {},
            "social_accounts": [], "web_results": [], "reddit_mentions": [],
            "whois": {}, "photos": [], "username_candidates": [], "summary": {},
        }

        pattern = self.analyze_pattern(email)
        report["pattern"] = pattern
        name = pattern["full_name"]
        local = pattern["local_part"]
        domain = pattern["domain"]
        first = pattern["first_name"]
        last = pattern["last_name"]

        try:
            report["domain_intel"] = self.analyze_domain(domain)
        except Exception as e:
            logger.error(f"Domain analysis failed: {e}")

        try:
            report["gravatar"] = self.lookup_gravatar(email)
            if report["gravatar"].get("display_name"):
                name = report["gravatar"]["display_name"]
        except Exception as e:
            logger.error(f"Gravatar lookup failed: {e}")

        try:
            report["reputation"] = self.check_reputation(email)
        except Exception as e:
            logger.error(f"Reputation check failed: {e}")

        try:
            report["breaches"] = self.check_breaches(email)
        except Exception as e:
            logger.error(f"Breach check failed: {e}")

        try:
            report["github"] = self.lookup_github(email, name)
        except Exception as e:
            logger.error(f"GitHub lookup failed: {e}")

        try:
            report["social_accounts"] = self.correlate_social(local, name)
        except Exception as e:
            logger.error(f"Social correlation failed: {e}")

        try:
            report["web_results"] = self.dork_search(email, name)
        except Exception as e:
            logger.error(f"Dork search failed: {e}")

        try:
            report["reddit_mentions"] = self.search_reddit(email, name)
        except Exception as e:
            logger.error(f"Reddit search failed: {e}")

        try:
            report["whois"] = self.lookup_domain_whois(domain)
        except Exception as e:
            logger.error(f"WHOIS lookup failed: {e}")

        try:
            report["photos"] = self.get_profile_photos(email, domain)
        except Exception as e:
            logger.error(f"Photo lookup failed: {e}")

        report["username_candidates"] = self.generate_usernames(first, last, local)
        report["summary"] = self._build_summary(report)
        return report

    def _build_summary(self, report: dict) -> dict:
        score = 0
        findings = []

        if report["gravatar"].get("has_gravatar"):
            score += 15
            findings.append("Gravatar profile found")

        if report["github"].get("found"):
            score += 20
            findings.append(f"GitHub: @{report['github']['username']}")

        social_count = len(report["social_accounts"])
        score += min(social_count * 8, 30)
        if social_count:
            findings.append(f"{social_count} social account(s) identified")

        web_count = len(report["web_results"])
        score += min(web_count * 3, 20)
        if web_count:
            findings.append(f"{web_count} web references found")

        if report["breaches"].get("breached"):
            findings.append(f"Data breach exposure: {report['breaches']['breach_count']} breach(es)")

        if report["domain_intel"].get("is_corporate"):
            score += 5
            findings.append("Corporate email domain")

        rep = report["reputation"].get("reputation", "unknown")
        if rep == "high":
            score += 10
        elif report["reputation"].get("suspicious"):
            score -= 10
            findings.append("Suspicious reputation flag")

        score = max(0, min(score, 100))

        if score >= 75: grade, label = "A", "High Visibility"
        elif score >= 50: grade, label = "B", "Moderate Visibility"
        elif score >= 25: grade, label = "C", "Low Visibility"
        else: grade, label = "D", "Minimal Footprint"

        return {
            "score": score, "grade": grade, "label": label,
            "key_findings": findings,
            "total_sources_checked": 10,
            "data_points_found": len(findings),
        }

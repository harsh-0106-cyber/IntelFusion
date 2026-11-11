"""
research_finder.py — TruSINT OSINT Engine
Searches academic databases for research papers authored by the target person.
Uses free public APIs: Semantic Scholar, arXiv, ORCID, CrossRef, and Hacker News (Algolia).
No API keys required.
"""

import os
import time
import requests
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 12))

HEADERS = {
    "User-Agent": "TruSINT-OSINT/1.0 (research; educational use)",
    "Accept": "application/json",
}


class ResearchFinder:
    """
    Finds academic publications, ORCID profiles, and research presence
    for a given person across multiple scholarly databases.
    """

    def find_all(self, query: dict) -> dict:
        """
        Returns:
        {
            "papers":   list of paper dicts,
            "orcid":    list of ORCID profile dicts,
            "profiles": list of researcher profile dicts (Semantic Scholar, etc.)
        }
        """
        full_name = query.get("full_name", "")
        organization = query.get("organization", "")
        institute = query.get("institute", "")
        affiliation_hint = organization or institute

        papers = []
        orcid_profiles = []
        researcher_profiles = []

        # Run searches
        ss_author, ss_papers = self._semantic_scholar(full_name, affiliation_hint)
        researcher_profiles.extend(ss_author)
        papers.extend(ss_papers)

        arxiv_papers = self._arxiv_search(full_name)
        papers.extend(arxiv_papers)

        crossref_papers = self._crossref_search(full_name)
        papers.extend(crossref_papers)

        orcid_results = self._orcid_search(full_name)
        orcid_profiles.extend(orcid_results)

        # Deduplicate papers by title similarity
        papers = self._deduplicate_papers(papers)

        return {
            "papers": papers[:20],
            "orcid": orcid_profiles[:5],
            "profiles": researcher_profiles[:5],
            "total_papers": len(papers),
            "has_research": len(papers) > 0 or len(orcid_profiles) > 0,
        }

    # ── Semantic Scholar ───────────────────────────────────────────────────────
    def _semantic_scholar(self, name: str, affiliation: str = "") -> tuple[list, list]:
        """Search Semantic Scholar for author profiles and their papers."""
        author_profiles = []
        papers = []

        try:
            query = name
            if affiliation:
                query += f" {affiliation}"

            url = "https://api.semanticscholar.org/graph/v1/author/search"
            params = {
                "query": query,
                "fields": "name,affiliations,paperCount,citationCount,papers.title,papers.year,papers.externalIds,papers.abstract,papers.authors,papers.venue",
                "limit": 3,
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for author in data.get("data", [])[:3]:
                    affiliations = [a.get("name", "") for a in author.get("affiliations", [])]
                    author_profiles.append({
                        "platform": "Semantic Scholar",
                        "name": author.get("name", ""),
                        "url": f"https://www.semanticscholar.org/author/{author.get('authorId', '')}",
                        "paper_count": author.get("paperCount", 0),
                        "citation_count": author.get("citationCount", 0),
                        "affiliations": affiliations,
                        "icon": "academic",
                        "color": "#1857b6",
                    })

                    # Extract their papers
                    for paper in author.get("papers", [])[:8]:
                        doi = (paper.get("externalIds") or {}).get("DOI", "")
                        url_paper = f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"
                        papers.append({
                            "title": paper.get("title", "Untitled"),
                            "year": paper.get("year"),
                            "venue": paper.get("venue", ""),
                            "abstract": (paper.get("abstract") or "")[:300],
                            "authors": [a.get("name", "") for a in (paper.get("authors") or [])[:5]],
                            "url": url_paper,
                            "doi": doi,
                            "source": "Semantic Scholar",
                        })
        except Exception as e:
            logger.warning(f"Semantic Scholar error: {e}")

        return author_profiles, papers

    # ── arXiv ──────────────────────────────────────────────────────────────────
    def _arxiv_search(self, name: str) -> list[dict]:
        """Search arXiv for papers with this author name."""
        papers = []
        try:
            # arXiv Atom API — free and no key needed
            url = "http://export.arxiv.org/api/query"
            params = {
                "search_query": f'au:"{name}"',
                "start": 0,
                "max_results": 5,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            resp = requests.get(url, params=params, headers={"User-Agent": "TruSINT-OSINT/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                import xml.etree.ElementTree as ET
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "arxiv": "http://arxiv.org/schemas/atom",
                }
                root = ET.fromstring(resp.text)
                for entry in root.findall("atom:entry", ns)[:5]:
                    title_el = entry.find("atom:title", ns)
                    abstract_el = entry.find("atom:summary", ns)
                    link_el = entry.find("atom:id", ns)
                    year = None
                    published_el = entry.find("atom:published", ns)
                    if published_el is not None and published_el.text:
                        year = published_el.text[:4]
                    authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns) if a.find("atom:name", ns) is not None]
                    if title_el is not None:
                        papers.append({
                            "title": title_el.text.strip().replace("\n", " "),
                            "year": int(year) if year else None,
                            "abstract": (abstract_el.text or "")[:300].strip() if abstract_el is not None else "",
                            "authors": authors[:5],
                            "url": link_el.text.strip() if link_el is not None else "",
                            "venue": "arXiv",
                            "doi": "",
                            "source": "arXiv",
                        })
        except Exception as e:
            logger.warning(f"arXiv error: {e}")
        return papers

    # ── CrossRef ────────────────────────────────────────────────────────────────
    def _crossref_search(self, name: str) -> list[dict]:
        """Search CrossRef for papers with this author."""
        papers = []
        try:
            url = "https://api.crossref.org/works"
            params = {
                "query.author": name,
                "rows": 5,
                "select": "title,author,published,DOI,container-title,abstract,URL",
            }
            headers = {**HEADERS, "User-Agent": "TruSINT-OSINT/1.0 (mailto:research@trusint.io)"}
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                for item in items[:5]:
                    titles = item.get("title", ["Untitled"])
                    title = titles[0] if titles else "Untitled"
                    doi = item.get("DOI", "")
                    paper_url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
                    published = item.get("published", {}).get("date-parts", [[None]])
                    year = published[0][0] if published and published[0] else None
                    venue_list = item.get("container-title", [])
                    venue = venue_list[0] if venue_list else ""
                    authors = [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in item.get("author", [])[:5]
                    ]
                    papers.append({
                        "title": title,
                        "year": year,
                        "abstract": (item.get("abstract") or "")[:300],
                        "authors": authors,
                        "url": paper_url,
                        "venue": venue,
                        "doi": doi,
                        "source": "CrossRef",
                    })
        except Exception as e:
            logger.warning(f"CrossRef error: {e}")
        return papers

    # ── ORCID ──────────────────────────────────────────────────────────────────
    def _orcid_search(self, name: str) -> list[dict]:
        """Search ORCID public registry for the person's researcher profile."""
        profiles = []
        try:
            url = "https://pub.orcid.org/v3.0/search/"
            params = {"q": f'family-name:{name.split()[-1]} AND given-names:{name.split()[0]}', "rows": 3}
            headers = {**HEADERS, "Accept": "application/json"}
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                results = resp.json().get("result", [])
                for r in results[:3]:
                    orcid_id = r.get("orcid-identifier", {}).get("path", "")
                    if orcid_id:
                        profiles.append({
                            "platform": "ORCID",
                            "orcid_id": orcid_id,
                            "url": f"https://orcid.org/{orcid_id}",
                            "title": f"ORCID Profile: {orcid_id}",
                            "description": f"Verified researcher profile on ORCID — ID: {orcid_id}",
                            "icon": "academic",
                            "color": "#a6ce39",
                        })
        except Exception as e:
            logger.warning(f"ORCID error: {e}")
        return profiles

    def _deduplicate_papers(self, papers: list[dict]) -> list[dict]:
        """Remove near-duplicate papers by title."""
        seen_titles = set()
        unique = []
        for p in papers:
            # Normalise title for comparison
            key = "".join(p.get("title", "").lower().split())[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(p)
        return unique

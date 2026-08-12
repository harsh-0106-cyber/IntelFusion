"""
query_parser.py — IntelFusion OSINT Engine
Parses raw user input into a structured query object for use by all OSINT modules.
"""

import re


class QueryParser:
    """Splits raw search input into first name, last name, keywords, and optional location."""

    # Common location prepositions that hint at a location clause
    LOCATION_HINTS = {"from", "in", "at", "near", "based", "living"}

    def parse(self, raw_input: str, place_of_work: str = "", institute: str = "", image_url: str = "") -> dict:
        """
        Parse a raw search string like "Elon Musk CEO Tesla" into structured fields.

        Returns:
            {
                "raw": str,
                "first_name": str,
                "last_name": str,
                "full_name": str,
                "keywords": list[str],
                "location": str | None,
                "place_of_work": str,
                "institute": str,
                "image_url": str,
                "query_variants": list[str],  # alternate phrasings for search engines
            }
        """
        raw = raw_input.strip()
        tokens = raw.split()

        first_name = ""
        last_name = ""
        keywords = []
        location = None

        if not tokens:
            return self._empty()

        # Heuristic: first two tokens that aren't location hints are the name
        name_tokens = []
        remaining_tokens = []
        collecting_name = True

        for i, token in enumerate(tokens):
            # If we hit a location hint keyword, everything after is location
            if token.lower() in self.LOCATION_HINTS and name_tokens:
                location = " ".join(tokens[i + 1:])
                break
            # First 1–2 tokens are always treated as the name (first + last).
            # A 3rd token is added only if it is also capitalised (middle name).
            if collecting_name and len(name_tokens) < 2:
                name_tokens.append(token)
            elif collecting_name and len(name_tokens) == 2 and token[0].isupper():
                name_tokens.append(token)
            else:
                collecting_name = False
                remaining_tokens.append(token)

        # Assign name parts
        if len(name_tokens) == 1:
            first_name = name_tokens[0]
            last_name = ""
        elif len(name_tokens) >= 2:
            first_name = name_tokens[0]
            # Middle name(s) become keywords, last token is last name
            if len(name_tokens) == 3:
                keywords.append(name_tokens[1])  # middle name as keyword
            last_name = name_tokens[-1]

        # Any remaining non-name tokens become keywords
        keywords.extend([t for t in remaining_tokens if t.lower() not in self.LOCATION_HINTS])

        full_name = f"{first_name} {last_name}".strip()

        # Build query variants for better search coverage
        query_variants = self._build_variants(full_name, keywords, location, place_of_work, institute)

        return {
            "raw": raw,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "keywords": keywords,
            "location": location,
            "place_of_work": place_of_work,
            "institute": institute,
            "image_url": image_url,
            "query_variants": query_variants,
        }

    def _build_variants(self, full_name: str, keywords: list, location: str | None, place_of_work: str, institute: str) -> list:
        """Generate multiple search query variants for wider coverage."""
        variants = [full_name]

        if keywords:
            kw_str = " ".join(keywords[:3])
            variants.append(f'"{full_name}" {kw_str}')
            
        if place_of_work:
             variants.append(f'"{full_name}" {place_of_work}')
             
        if institute:
             variants.append(f'"{full_name}" {institute}')

        if location:
            variants.append(f'"{full_name}" {location}')

        if keywords and location:
            variants.append(f'"{full_name}" {keywords[0]} {location}')

        # Social-media focused variant
        variants.append(f'"{full_name}" site:linkedin.com OR site:twitter.com OR site:github.com')

        # Always include a quoted exact-match variant
        if f'"{full_name}"' not in variants:
            variants.insert(1, f'"{full_name}"')

        return variants

    def _empty(self) -> dict:
        return {
            "raw": "",
            "first_name": "",
            "last_name": "",
            "full_name": "",
            "keywords": [],
            "location": None,
            "place_of_work": "",
            "institute": "",
            "image_url": "",
            "query_variants": [],
        }


# Quick self-test
if __name__ == "__main__":
    parser = QueryParser()
    tests = [
        "Elon Musk",
        "Elon Musk CEO Tesla",
        "Mark Zuckerberg from Palo Alto",
        "Ada Lovelace mathematician",
        "Sundar",
    ]
    for t in tests:
        print(parser.parse(t))

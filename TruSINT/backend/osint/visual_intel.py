"""
visual_intel.py — TruSINT OSINT Engine
Generates reverse image search links for a given image URL.
"""

from urllib.parse import quote_plus

class VisualIntel:
    """
    Given an image URL, generates direct links to reverse image search engines.
    """

    def generate_links(self, query: dict) -> list[dict]:
        image_url = query.get("image_url", "").strip()
        if not image_url:
            return []

        encoded_url = quote_plus(image_url)
        
        links = [
            {
                "platform": "Google Lens",
                "url": f"https://lens.google.com/uploadbyurl?url={encoded_url}",
                "icon": "web",
                "color": "#ea4335",
                "description": "Search Google Lens for this image."
            },
            {
                "platform": "Yandex Images",
                "url": f"https://yandex.com/images/search?rpt=imageview&url={encoded_url}",
                "icon": "web",
                "color": "#fc3f1d",
                "description": "Search Yandex (often better for facial recognition)."
            },
            {
                "platform": "TinEye",
                "url": f"https://tineye.com/search?url={encoded_url}",
                "icon": "web",
                "color": "#000000",
                "description": "Search TinEye for exact image matches."
            },
            {
                "platform": "Bing Visual Search",
                "url": f"https://www.bing.com/images/search?view=detailv2&iss=sbi&FORM=RECIPE&q=imgurl:{encoded_url}",
                "icon": "web",
                "color": "#008373",
                "description": "Search Bing Visual Search."
            }
        ]
        
        return links

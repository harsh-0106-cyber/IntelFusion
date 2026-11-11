"""
test_zlens_web_dorking.py — Verifies multi-source Web OSINT image harvesting and dorking in ZLens.
"""

import io
from PIL import Image
from zlens.web_search import ZLensWebSearcher
from app import app, zlens_sessions


def make_test_image():
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_web_searcher_wikimedia():
    results = ZLensWebSearcher._search_wikimedia("London", max_count=3)
    assert isinstance(results, list)
    if results:
        assert "image_url" in results[0]
        assert "source_name" in results[0]
        assert results[0]["source_name"] == "Wikimedia Commons"


def test_reverse_search_links():
    links = ZLensWebSearcher.get_reverse_search_links(
        image_url="https://example.com/photo.jpg",
        subject="Test Person",
    )
    assert len(links) == 5
    engines = [l["engine"] for l in links]
    assert any("Lenso.ai" in e for e in engines)
    assert "Google Lens Live Search" in engines
    assert "Yandex Visual" in engines
    assert "Bing Visual Search" in engines
    assert "TinEye Reverse Search" in engines


def test_zlens_upload_with_filename():
    client = app.test_client()
    buf = make_test_image()
    data = {
        "image": (buf, "satya_nadella.jpg", "image/jpeg"),
    }
    res = client.post("/api/zlens/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["success"] is True
    assert json_data["original_filename"] == "satya_nadella.jpg"
    assert "satya nadella" in json_data["suggested_query"].lower()


def test_lenso_client_without_key(tmp_path):
    from zlens.lenso_client import LensoAIClient
    test_img = tmp_path / "test.jpg"
    test_img.write_bytes(make_test_image().getvalue())
    res = LensoAIClient.search(test_img, api_key="")
    assert res["success"] is False
    assert res["error"] == "NO_API_KEY"

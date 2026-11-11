"""
test_zlens_api.py — Integration tests for ZLens Visual Reverse Search REST API
"""

import io
import pytest
from PIL import Image

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def make_test_image(format="JPEG", size=(150, 150), color=(100, 200, 50)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format=format)
    buf.seek(0)
    return buf


class TestZLensAPI:

    def test_zlens_health(self, client):
        res = client.get("/api/zlens/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "ok"
        assert "max_file_size_mb" in data
        assert "allowed_formats" in data
        assert "JPEG" in data["allowed_formats"]

    def test_zlens_upload_valid_image(self, client):
        img_buf = make_test_image(format="JPEG")
        data = {
            "image": (img_buf, "test_query.jpg", "image/jpeg"),
        }
        res = client.post("/api/zlens/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert "session_id" in body
        assert len(body["sha256"]) == 64
        assert len(body["phash"]) == 16
        assert len(body["dhash"]) == 16
        assert body["width"] == 150
        assert body["height"] == 150
        assert body["format"] == "JPEG"

    def test_zlens_upload_rejects_empty(self, client):
        res = client.post("/api/zlens/upload", data={}, content_type="multipart/form-data")
        assert res.status_code == 400
        body = res.get_json()
        assert "error" in body

    def test_zlens_upload_rejects_fake_image(self, client):
        fake_buf = io.BytesIO(b"NOT_AN_IMAGE_CONTENT_HERE")
        data = {
            "image": (fake_buf, "fake.jpg", "image/jpeg"),
        }
        res = client.post("/api/zlens/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 400
        body = res.get_json()
        assert body["code"] == "UNSUPPORTED_FORMAT"

    def test_zlens_sync_search_valid(self, client):
        img_buf = make_test_image(format="PNG")
        data = {
            "image": (img_buf, "query.png", "image/png"),
            "name": "Wikipedia",
            "keywords": "logo",
        }
        res = client.post("/api/zlens/search", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert "query_sha256" in body
        assert "matches" in body
        assert isinstance(body["matches"], list)

    def test_zlens_delete_session(self, client):
        # First upload
        img_buf = make_test_image()
        res = client.post("/api/zlens/upload", data={"image": (img_buf, "test.jpg", "image/jpeg")}, content_type="multipart/form-data")
        session_id = res.get_json()["session_id"]

        # Delete session
        del_res = client.delete(f"/api/zlens/search/{session_id}")
        assert del_res.status_code == 200
        assert del_res.get_json()["success"] is True

        # Non-existent session
        del_res_again = client.delete(f"/api/zlens/search/{session_id}")
        assert del_res_again.status_code == 404

    def test_index_stats_endpoint(self, client):
        res = client.get("/api/zlens/index/stats")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "total_assets" in data
        assert "total_sources" in data
        assert "status" in data
        assert data["status"] == "operational"

    def test_index_assets_endpoint(self, client):
        res = client.get("/api/zlens/index/assets?limit=10&offset=0")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "assets" in data
        assert isinstance(data["assets"], list)
        assert "total" in data

    def test_index_import_security_blocks_traversal(self, client):
        # Path traversal payload
        res = client.post(
            "/api/zlens/index/import",
            json={"subpath": "../../windows/system32"},
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["code"] == "FORBIDDEN_PATH"

    def test_zlens_sync_search_without_optional_text(self, client):
        """Image retrieval must run even when name and keywords are completely omitted."""
        img_buf = make_test_image(format="JPEG")
        data = {
            "image": (img_buf, "query_only.jpg", "image/jpeg"),
        }
        res = client.post("/api/zlens/search", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert "candidates_examined" in body
        assert "exact_matches_count" in body
        assert "near_duplicates_count" in body
        assert "status" in body
        assert body["status"] in ("matches_found", "no_matches", "index_empty")

    def test_zlens_asset_preview_nonexistent(self, client):
        """Preview for non-existent asset returns 404."""
        res = client.get("/api/zlens/assets/999999/preview")
        assert res.status_code == 404
        body = res.get_json()
        assert body["code"] == "PREVIEW_UNAVAILABLE"

    def test_zlens_asset_preview_existing(self, client):
        """Preview for existing asset inside permitted directory returns image."""
        assets_res = client.get("/api/zlens/index/assets?limit=1")
        assert assets_res.status_code == 200
        assets = assets_res.get_json().get("assets", [])
        if assets:
            asset_id = assets[0]["id"]
            preview_res = client.get(f"/api/zlens/assets/{asset_id}/preview")
            assert preview_res.status_code in (200, 404)  # 200 if file exists on disk
            if preview_res.status_code == 200:
                assert preview_res.mimetype.startswith("image/")


"""
test_zlens_preprocessor.py — Unit tests for ZLens Image Preprocessor Service
"""

import io
import pytest
import numpy as np
from PIL import Image

from zlens.preprocessor import (
    ImagePreprocessor,
    ImageValidationError,
    PreprocessedImage,
)


def create_test_image(format="JPEG", size=(200, 200), color=(120, 60, 200), mode="RGB") -> bytes:
    """Helper to generate in-memory test image bytes."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


class TestImagePreprocessor:

    @pytest.fixture
    def preprocessor(self):
        return ImagePreprocessor(
            max_file_size=2 * 1024 * 1024,  # 2MB
            max_pixels=1_000_000,          # 1 Megapixel
            min_dimension=32,
        )

    # 1. Valid Formats
    def test_valid_jpeg(self, preprocessor):
        raw = create_test_image("JPEG")
        res = preprocessor.preprocess(raw)
        assert isinstance(res, PreprocessedImage)
        assert res.format == "JPEG"
        assert res.width == 200
        assert res.height == 200
        assert len(res.sha256) == 64
        assert len(res.dhash) == 16
        assert len(res.ahash) == 16
        assert len(res.phash) == 16
        assert res.tensor_representation.shape == (3, 224, 224)
        assert 0.0 <= res.tensor_representation.min() <= res.tensor_representation.max() <= 1.0

    def test_valid_png(self, preprocessor):
        raw = create_test_image("PNG")
        res = preprocessor.preprocess(raw)
        assert res.format == "PNG"
        assert res.width == 200
        assert res.height == 200

    def test_valid_webp(self, preprocessor):
        raw = create_test_image("WEBP")
        res = preprocessor.preprocess(raw)
        assert res.format == "WEBP"
        assert res.width == 200
        assert res.height == 200

    def test_rgba_with_transparency_blended_to_rgb(self, preprocessor):
        raw = create_test_image("PNG", mode="RGBA", color=(255, 0, 0, 128))
        res = preprocessor.preprocess(raw)
        assert res.width == 200
        assert res.height == 200
        # Serialized format should be sanitized JPEG bytes
        assert res.sanitized_bytes.startswith(b"\xff\xd8\xff")

    # 2. Rejection & Error Handling
    def test_rejects_empty_bytes(self, preprocessor):
        with pytest.raises(ImageValidationError) as exc:
            preprocessor.preprocess(b"")
        assert exc.value.code == "FILE_TOO_SMALL"

    def test_rejects_non_image_disguised_file(self, preprocessor):
        fake_data = b"<!DOCTYPE html><html><body><h1>Fake Image</h1></body></html>"
        with pytest.raises(ImageValidationError) as exc:
            preprocessor.preprocess(fake_data)
        assert exc.value.code == "UNSUPPORTED_FORMAT"

    def test_rejects_corrupted_image(self, preprocessor):
        # Starts with valid JPEG header but contains junk
        corrupt_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        with pytest.raises(ImageValidationError) as exc:
            preprocessor.preprocess(corrupt_jpeg)
        assert exc.value.code == "CORRUPT_IMAGE"

    def test_rejects_oversized_file(self, preprocessor):
        # Configured limit in fixture is 2MB
        oversized_preprocessor = ImagePreprocessor(max_file_size=500)
        raw = create_test_image("JPEG")
        with pytest.raises(ImageValidationError) as exc:
            oversized_preprocessor.preprocess(raw)
        assert exc.value.code == "FILE_TOO_LARGE"

    def test_rejects_oversized_pixel_count(self):
        tiny_limit_preprocessor = ImagePreprocessor(max_pixels=5000)
        raw = create_test_image("JPEG", size=(100, 100))  # 10,000 pixels > 5,000
        with pytest.raises(ImageValidationError) as exc:
            tiny_limit_preprocessor.preprocess(raw)
        assert exc.value.code == "PIXEL_LIMIT_EXCEEDED"

    def test_rejects_dimension_below_minimum(self, preprocessor):
        raw = create_test_image("JPEG", size=(20, 20))  # below 32x32
        with pytest.raises(ImageValidationError) as exc:
            preprocessor.preprocess(raw)
        assert exc.value.code == "DIMENSION_TOO_SMALL"

    # 3. Repeatability & Near-Duplicate Distance
    def test_sha256_deterministic(self, preprocessor):
        raw = create_test_image("JPEG", size=(120, 120), color=(50, 150, 250))
        res1 = preprocessor.preprocess(raw)
        res2 = preprocessor.preprocess(raw)
        assert res1.sha256 == res2.sha256
        assert res1.dhash == res2.dhash
        assert res1.phash == res2.phash

    def test_near_duplicate_perceptual_hash_distance(self, preprocessor):
        # Create base image
        img = Image.new("RGB", (300, 300), (80, 140, 220))
        # Draw some variation so DCT and gradients are non-trivial
        pixels = img.load()
        for x in range(50, 250):
            for y in range(50, 250):
                pixels[x, y] = (x % 255, y % 255, (x * y) % 255)

        buf1 = io.BytesIO()
        img.save(buf1, format="JPEG", quality=95)
        raw1 = buf1.getvalue()

        # Near-duplicate: resized and re-compressed at lower quality
        resized_img = img.resize((240, 240), Image.Resampling.BILINEAR)
        buf2 = io.BytesIO()
        resized_img.save(buf2, format="JPEG", quality=75)
        raw2 = buf2.getvalue()

        # Unrelated image: completely different pattern
        diff_img = Image.new("RGB", (300, 300), (240, 20, 20))
        diff_buf = io.BytesIO()
        diff_img.save(diff_buf, format="JPEG")
        raw_diff = diff_buf.getvalue()

        res1 = preprocessor.preprocess(raw1)
        res2 = preprocessor.preprocess(raw2)
        res_diff = preprocessor.preprocess(raw_diff)

        # Near duplicate should have very small Hamming distance
        phash_dist_near = ImagePreprocessor.hamming_distance(res1.phash, res2.phash)
        dhash_dist_near = ImagePreprocessor.hamming_distance(res1.dhash, res2.dhash)

        # Unrelated should have much larger distance
        phash_dist_diff = ImagePreprocessor.hamming_distance(res1.phash, res_diff.phash)
        dhash_dist_diff = ImagePreprocessor.hamming_distance(res1.dhash, res_diff.dhash)

        assert phash_dist_near <= 10, f"Expected small pHash distance for near-duplicate, got {phash_dist_near}"
        assert dhash_dist_near <= 6, f"Expected small dHash distance for near-duplicate, got {dhash_dist_near}"
        assert phash_dist_diff > phash_dist_near, "Unrelated image should have greater distance than near-duplicate"
        assert dhash_dist_diff > dhash_dist_near, "Unrelated image should have greater distance than near-duplicate"

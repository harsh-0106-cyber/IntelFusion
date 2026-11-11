"""
preprocessor.py — ZLens Image Ingestion and Preprocessing Service

Enforces strict content validation, sanitization, orientation normalization,
EXIF privacy stripping, cryptographic SHA-256 calculation, and perceptual hashing
(dHash, aHash, pHash via 2D Discrete Cosine Transform).
"""

from __future__ import annotations

import io
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Tuple

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("zlens.preprocessor")

# Default configuration limits
DEFAULT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024   # 15 MB
DEFAULT_MAX_PIXELS = 25_000_000                  # 25 Megapixels (e.g. 5000 x 5000)
DEFAULT_MIN_DIMENSION = 32                       # Minimum 32x32 pixels
DEFAULT_NORMALIZED_TENSOR_SIZE = (224, 224)      # Standard inference input

# Magic byte signatures
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_RIFF = b"RIFF"
MAGIC_WEBP = b"WEBP"


class ImageValidationError(ValueError):
    """Raised when an uploaded image fails validation or security checks."""
    def __init__(self, message: str, code: str = "INVALID_IMAGE"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class PreprocessedImage:
    """Immutable result of the image validation and preprocessing pipeline."""
    sha256: str
    dhash: str
    ahash: str
    phash: str
    width: int
    height: int
    format: str
    sanitized_bytes: bytes = field(repr=False)
    tensor_representation: np.ndarray = field(repr=False)

    @property
    def aspect_ratio(self) -> float:
        return round(self.width / max(1, self.height), 4)

    def to_dict(self) -> dict[str, Any]:
        """Serializable summary of the preprocessed image metadata."""
        return {
            "sha256": self.sha256,
            "dhash": self.dhash,
            "ahash": self.ahash,
            "phash": self.phash,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "aspect_ratio": self.aspect_ratio,
            "bytes_length": len(self.sanitized_bytes),
        }


class ImagePreprocessor:
    """
    Dedicated image ingestion, validation, and normalization service.
    """

    def __init__(
        self,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        max_pixels: int = DEFAULT_MAX_PIXELS,
        min_dimension: int = DEFAULT_MIN_DIMENSION,
        tensor_size: Tuple[int, int] = DEFAULT_NORMALIZED_TENSOR_SIZE,
    ):
        self.max_file_size = max_file_size
        self.max_pixels = max_pixels
        self.min_dimension = min_dimension
        self.tensor_size = tensor_size

    # ──────────────────────────────────────────────────────────────────────────
    # Magic Bytes & Content Validation
    # ──────────────────────────────────────────────────────────────────────────

    def detect_format(self, raw_bytes: bytes) -> str:
        """
        Inspects file magic bytes to verify genuine JPEG, PNG, or WebP content.
        Does not trust user-supplied MIME type or file extension.
        """
        if not raw_bytes or len(raw_bytes) < 12:
            raise ImageValidationError("File is empty or too small to be a valid image.", code="FILE_TOO_SMALL")

        if raw_bytes.startswith(MAGIC_JPEG):
            return "JPEG"
        if raw_bytes.startswith(MAGIC_PNG):
            return "PNG"
        if raw_bytes.startswith(MAGIC_RIFF) and raw_bytes[8:12] == MAGIC_WEBP:
            return "WEBP"

        raise ImageValidationError(
            "Unsupported or invalid image format. Allowed formats are genuine JPEG, PNG, and WebP.",
            code="UNSUPPORTED_FORMAT",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Main Preprocessing Pipeline
    # ──────────────────────────────────────────────────────────────────────────

    def preprocess(self, raw_bytes: bytes) -> PreprocessedImage:
        """
        Executes complete verification, sanitization, hashing, and normalization pipeline.
        """
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise ImageValidationError("Image input must be bytes or bytearray.", code="INVALID_TYPE")

        # 1. Size constraint
        byte_len = len(raw_bytes)
        if byte_len > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            raise ImageValidationError(
                f"File size ({round(byte_len / (1024 * 1024), 2)}MB) exceeds maximum permitted limit ({max_mb}MB).",
                code="FILE_TOO_LARGE",
            )

        # 2. Magic byte validation
        detected_format = self.detect_format(raw_bytes)

        # 3. Decode & integrity verification
        try:
            # First pass: Pillow verify
            verify_buffer = io.BytesIO(raw_bytes)
            with Image.open(verify_buffer) as test_img:
                test_img.verify()

            # Second pass: Full decode
            decode_buffer = io.BytesIO(raw_bytes)
            img = Image.open(decode_buffer)
            img.load()
        except Exception as e:
            logger.warning("Image decode/integrity verification failed: %s", type(e).__name__)
            raise ImageValidationError(
                "Image file is corrupted, incomplete, or damaged and cannot be decoded.",
                code="CORRUPT_IMAGE",
            ) from e

        # 4. Dimension & pixel count constraint
        w, h = img.size
        total_pixels = w * h
        if total_pixels > self.max_pixels:
            raise ImageValidationError(
                f"Image resolution ({w}x{h} = {total_pixels:,} pixels) exceeds the maximum limit of {self.max_pixels:,} pixels.",
                code="PIXEL_LIMIT_EXCEEDED",
            )

        if w < self.min_dimension or h < self.min_dimension:
            raise ImageValidationError(
                f"Image dimensions ({w}x{h}) are too small. Minimum required dimension is {self.min_dimension}x{self.min_dimension}.",
                code="DIMENSION_TOO_SMALL",
            )

        # 5. EXIF orientation normalization
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            # Fallback if transpose encounters anomalous metadata
            pass

        # 6. Normalize color mode to RGB and handle transparency
        norm_img = self._normalize_color_mode(img)
        norm_w, norm_h = norm_img.size

        # 7. Strip EXIF & serialize sanitized byte representation
        sanitized_bytes = self._strip_exif_and_serialize(norm_img)

        # 8. Cryptographic hash (SHA-256 of normalized image bytes)
        sha256_hash = hashlib.sha256(sanitized_bytes).hexdigest()

        # 9. Perceptual hashes (dHash, aHash, pHash)
        dhash_str = self.compute_dhash(norm_img)
        ahash_str = self.compute_ahash(norm_img)
        phash_str = self.compute_phash(norm_img)

        # 10. Normalized tensor/array representation for model inference
        tensor_repr = self._create_inference_tensor(norm_img)

        return PreprocessedImage(
            sha256=sha256_hash,
            dhash=dhash_str,
            ahash=ahash_str,
            phash=phash_str,
            width=norm_w,
            height=norm_h,
            format=detected_format,
            sanitized_bytes=sanitized_bytes,
            tensor_representation=tensor_repr,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Color Mode Normalization & EXIF Sanitization
    # ──────────────────────────────────────────────────────────────────────────

    def _normalize_color_mode(self, img: Image.Image) -> Image.Image:
        """
        Converts any image mode (RGBA, P, LA, CMYK, L) safely to RGB.
        Blends transparent alpha channel against a neutral white background.
        """
        if img.mode == "RGB":
            return img

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba_img = img.convert("RGBA")
            bg = Image.new("RGBA", rgba_img.size, (255, 255, 255, 255))
            blended = Image.alpha_composite(bg, rgba_img)
            return blended.convert("RGB")

        return img.convert("RGB")

    def _strip_exif_and_serialize(self, img: Image.Image) -> bytes:
        """
        Serializes clean RGB image into JPEG bytes with 95 quality without any EXIF/GPS tags.
        """
        out_buf = io.BytesIO()
        # Save as clean JPEG without passing any exif/icc info
        img.save(out_buf, format="JPEG", quality=95, optimize=True)
        return out_buf.getvalue()

    # ──────────────────────────────────────────────────────────────────────────
    # Perceptual Hashes
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
        """
        Difference Hash (dHash): compares adjacent pixel gradients.
        Produces a (hash_size * hash_size) bit hash formatted as hex.
        """
        # Resize to (hash_size + 1, hash_size) in grayscale
        resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        arr = np.asarray(resized, dtype=np.int32)
        # Compute horizontal difference
        diff = arr[:, 1:] > arr[:, :-1]
        bits = diff.flatten()
        return ImagePreprocessor._bits_to_hex(bits, hash_size * hash_size)

    @staticmethod
    def compute_ahash(img: Image.Image, hash_size: int = 8) -> str:
        """
        Average Hash (aHash): compares pixels against average luminance.
        Produces a (hash_size * hash_size) bit hash formatted as hex.
        """
        resized = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        arr = np.asarray(resized, dtype=np.float32)
        avg = np.mean(arr)
        bits = (arr > avg).flatten()
        return ImagePreprocessor._bits_to_hex(bits, hash_size * hash_size)

    @staticmethod
    def compute_phash(img: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> str:
        """
        Perceptual Hash (pHash): computes 2D Discrete Cosine Transform (DCT) on 32x32 luminance,
        extracts the top-left 8x8 low-frequency coefficients (excluding DC term), and compares
        against the median coefficient.
        """
        img_size = hash_size * highfreq_factor  # 32x32
        resized = img.convert("L").resize((img_size, img_size), Image.Resampling.LANCZOS)
        arr = np.asarray(resized, dtype=np.float64)

        # Compute 2D DCT via separable 1D matrix multiplication
        dct_matrix = ImagePreprocessor._dct_2d(arr)

        # Extract top-left 8x8 low frequencies (excluding (0,0) DC term)
        low_freq = dct_matrix[:hash_size, :hash_size]
        # Median of all AC coefficients
        median_val = np.median(low_freq.flatten()[1:])
        bits = (low_freq > median_val).flatten()
        return ImagePreprocessor._bits_to_hex(bits, hash_size * hash_size)

    @staticmethod
    def _dct_1d(matrix: np.ndarray) -> np.ndarray:
        N = matrix.shape[1]
        n = np.arange(N)
        k = np.arange(N).reshape(-1, 1)
        cos_table = np.cos((np.pi * (2 * n + 1) * k) / (2.0 * N))
        return np.dot(matrix, cos_table.T)

    @staticmethod
    def _dct_2d(arr: np.ndarray) -> np.ndarray:
        # 2D DCT is separable: 1D DCT on rows, then 1D DCT on columns
        row_dct = ImagePreprocessor._dct_1d(arr)
        col_dct = ImagePreprocessor._dct_1d(row_dct.T).T
        return col_dct

    @staticmethod
    def _bits_to_hex(bits: np.ndarray, total_bits: int) -> str:
        bit_str = "".join("1" if b else "0" for b in bits)
        hex_len = total_bits // 4
        return f"{int(bit_str, 2):0{hex_len}x}"

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """
        Computes bitwise Hamming distance between two hexadecimal hash strings.
        Returns the number of differing bits.
        """
        if not hash1 or not hash2:
            return 64
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count("1")

    # ──────────────────────────────────────────────────────────────────────────
    # Inference Tensor Representation
    # ──────────────────────────────────────────────────────────────────────────

    def _create_inference_tensor(self, img: Image.Image) -> np.ndarray:
        """
        Prepares a standardized (3, 224, 224) float32 tensor normalized to [0, 1].
        Ready for embedding models (e.g. OpenCLIP / DINOv2 / ResNet).
        """
        resized = img.resize(self.tensor_size, Image.Resampling.BICUBIC)
        arr = np.asarray(resized, dtype=np.float32) / 255.0  # (224, 224, 3)
        # Transpose to channels-first (3, H, W)
        tensor = np.transpose(arr, (2, 0, 1))
        return tensor

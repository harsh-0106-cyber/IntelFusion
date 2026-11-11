"""
ZLens — Production-Oriented Visual Reverse Image Retrieval Module.
"""

from zlens.preprocessor import (
    ImagePreprocessor,
    PreprocessedImage,
    ImageValidationError,
)
from zlens.database import DatabaseManager, DEFAULT_DB_PATH
from zlens.indexer import (
    ZLensIndexer,
    IndexResult,
    BatchIndexReport,
    validate_permitted_path,
    PathSecurityError,
)
from zlens.retriever import (
    ZLensRetriever,
    LocalSearchResult,
    calculate_hamming_distance,
    validate_hex_hash,
    HashFormatError,
)
from zlens.engine import (
    connect_db,
    init_db,
    validate_and_open,
    sha256_file,
    hashes_for_image,
    index_file,
    index_collection,
    search_image,
    asset_path_by_id,
    get_status,
    hamming_hex,
    COLLECTION_DIR,
    UPLOAD_DIR,
    DB_PATH,
    PHASH_MAX_DISTANCE,
    DHASH_MAX_DISTANCE,
)

__all__ = [
    "ImagePreprocessor",
    "PreprocessedImage",
    "ImageValidationError",
    "DatabaseManager",
    "DEFAULT_DB_PATH",
    "ZLensIndexer",
    "IndexResult",
    "BatchIndexReport",
    "validate_permitted_path",
    "PathSecurityError",
    "ZLensRetriever",
    "LocalSearchResult",
    "calculate_hamming_distance",
    "validate_hex_hash",
    "HashFormatError",
    "connect_db",
    "init_db",
    "validate_and_open",
    "sha256_file",
    "hashes_for_image",
    "index_file",
    "index_collection",
    "search_image",
    "asset_path_by_id",
    "get_status",
    "hamming_hex",
    "COLLECTION_DIR",
    "UPLOAD_DIR",
    "DB_PATH",
    "PHASH_MAX_DISTANCE",
    "DHASH_MAX_DISTANCE",
]

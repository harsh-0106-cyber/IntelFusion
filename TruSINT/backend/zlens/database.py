"""
database.py — SQLite Database Layer for ZLens Asset and Metadata Indexing

Manages schema initialization, migrations, connection management,
indexing constraints, and transaction safety.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Iterator, Optional, Any

logger = logging.getLogger("zlens.database")

# Default database location inside backend/data/zlens.db
DEFAULT_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "zlens.db")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Core indexed visual assets table
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_sha256 TEXT NOT NULL UNIQUE,
    dhash TEXT NOT NULL,
    ahash TEXT NOT NULL,
    phash TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    aspect_ratio REAL NOT NULL,
    format TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'indexed'
);

CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(image_sha256);
CREATE INDEX IF NOT EXISTS idx_assets_dhash ON assets(dhash);
CREATE INDEX IF NOT EXISTS idx_assets_phash ON assets(phash);
CREATE INDEX IF NOT EXISTS idx_assets_indexed_at ON assets(indexed_at);

-- Provenance and sources for indexed assets (1 asset can have multiple sources)
CREATE TABLE IF NOT EXISTS asset_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT,
    source_page_url TEXT,
    source_image_url TEXT,
    discovered_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_sources_asset_id ON asset_sources(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_sources_page_url ON asset_sources(source_page_url);
"""


class DatabaseManager:
    """
    Manages SQLite connections, transactions, and schema setup for ZLens indexing.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("ZLENS_DB_PATH", DEFAULT_DB_PATH)
        # Ensure parent directory exists
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates a new SQLite connection with appropriate pragmas.
        Caller is responsible for closing, or use connection() context manager.
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=15.0,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for obtaining a connection and auto-closing it."""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for an atomic database transaction.
        Commits on successful block exit, rolls back on exception.
        """
        conn = self.get_connection()
        try:
            with conn:
                yield conn
        except Exception as e:
            logger.error("Transaction rolled back due to error: %s", e)
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Initializes tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
        logger.info(f"ZLens SQLite database schema initialized at {self.db_path}")

    def execute_query(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Executes a SELECT query and returns all matching rows."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()

    def execute_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Executes a SELECT query and returns the first row or None."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()

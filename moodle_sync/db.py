from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    file_hash TEXT NOT NULL,
    module TEXT NOT NULL,
    lecture TEXT NOT NULL,
    filename TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    needs_ocr INTEGER NOT NULL,
    ocr_reason TEXT,
    UNIQUE(document_id, page_number)
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    module TEXT NOT NULL,
    lecture TEXT NOT NULL,
    filename TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS index_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    documents_seen INTEGER NOT NULL,
    documents_indexed INTEGER NOT NULL,
    pages_indexed INTEGER NOT NULL,
    chunks_indexed INTEGER NOT NULL,
    ocr_pages INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def vector_to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def set_metadata(conn: sqlite3.Connection, **items: str) -> None:
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        list(items.items()),
    )


def get_document_by_path(conn: sqlite3.Connection, path: Path) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE path = ?", (str(path),)).fetchone()


def delete_document(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def insert_index_run(conn: sqlite3.Connection, stats: dict[str, int]) -> None:
    conn.execute(
        """
        INSERT INTO index_runs(documents_seen, documents_indexed, pages_indexed, chunks_indexed, ocr_pages)
        VALUES (:documents_seen, :documents_indexed, :pages_indexed, :chunks_indexed, :ocr_pages)
        """,
        stats,
    )

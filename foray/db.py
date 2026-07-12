"""Embedded SQLite storage with WAL mode for concurrent reads.

WAL allows the Chat UI and the MCP server to read while a background
worker writes. The database also acts as its own durable job state,
caches generated onboarding docs and tracks indexing costs.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    loc         INTEGER NOT NULL,
    language    TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    indexed_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT NOT NULL UNIQUE,
    path        TEXT NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    language    TEXT,
    symbols     TEXT NOT NULL DEFAULT '[]',
    content     TEXT NOT NULL,
    token_est   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    path UNINDEXED,
    symbols_text UNINDEXED,
    tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS edges (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    kind   TEXT NOT NULL DEFAULT 'import'
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS costs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    stage    TEXT NOT NULL,          -- 'indexing' | 'docs'
    detail   TEXT NOT NULL DEFAULT '',
    tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    created  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS docs (
    key      TEXT PRIMARY KEY,       -- 'onboarding'
    content  TEXT NOT NULL,
    model    TEXT NOT NULL DEFAULT '',
    created  REAL NOT NULL
);
"""


def connect(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    """Open a WAL-mode connection. Writers serialize via BEGIN IMMEDIATE."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    else:
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)


def open_index(repo_id: str, create: bool = False) -> sqlite3.Connection:
    """Open the per-repo live index database (read path)."""
    from . import paths

    db_path = paths.sqlite_path(repo_id)
    if create:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    if create:
        init_schema(conn)
    return conn

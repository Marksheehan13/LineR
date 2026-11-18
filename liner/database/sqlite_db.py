"""Layer 5, Database: a local SQLite file (Simplified; the target uses PostgreSQL).

Only plain SQL that PostgreSQL also accepts is used in the data-access layer, apart from the
BEGIN IMMEDIATE in the counter, which becomes a row lock or sequence there."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    status        TEXT NOT NULL,
    number        INTEGER,
    image_ref     TEXT,
    created_at    TEXT NOT NULL,
    confirmed_at  TEXT,
    body          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_user_status ON documents (user_id, status);

CREATE TABLE IF NOT EXISTS counters (
    user_id  TEXT PRIMARY KEY,
    value    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id    TEXT NOT NULL,
    user_id   TEXT NOT NULL,
    field     TEXT NOT NULL,
    original  TEXT,
    final     TEXT,
    kind      TEXT NOT NULL,
    at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_documents (
    doc_id        TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    fields_shown  INTEGER NOT NULL,
    at            TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.init_schema()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """One short-lived connection per unit of work: commits on success, rolls back on error."""
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)

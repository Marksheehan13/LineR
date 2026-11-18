"""Layer 4, Document repository: save / get / list (Simplified: SQLite behind the same interface)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..database.sqlite_db import Database
from ..models import Document, document_from_dict, document_to_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SqliteDocumentRepository:
    def __init__(self, db: Database):
        self._db = db

    def save(self, doc: Document) -> str:
        body = json.dumps(document_to_dict(doc), separators=(",", ":"))
        with self._db.connection() as conn:
            if doc.id is None:
                doc.id = uuid.uuid4().hex
                doc.created_at = doc.created_at or _now()
                conn.execute(
                    "INSERT INTO documents (id, user_id, status, number, image_ref, created_at,"
                    " confirmed_at, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc.id, doc.user_id, doc.status, doc.number, doc.image_ref, doc.created_at,
                     doc.confirmed_at, body))
            else:
                # the WHERE on user_id means one user can never overwrite another's document (R8)
                cur = conn.execute(
                    "UPDATE documents SET status = ?, number = ?, image_ref = ?, confirmed_at = ?,"
                    " body = ? WHERE id = ? AND user_id = ?",
                    (doc.status, doc.number, doc.image_ref, doc.confirmed_at, body, doc.id, doc.user_id))
                if cur.rowcount != 1:
                    raise KeyError(f"document {doc.id} not found for this user")
        return doc.id

    def get(self, doc_id: str, user_id: str) -> Document | None:
        with self._db.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?",
                               (doc_id, user_id)).fetchone()
        return None if row is None else self._build(row)

    def list(self, user_id: str, status: str | None = None) -> list[Document]:
        sql = "SELECT * FROM documents WHERE user_id = ?"
        args: list = [user_id]
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY created_at, id"
        with self._db.connection() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._build(r) for r in rows]

    def next_counter(self, user_id: str) -> int:
        with self._db.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")  # take the write lock so two requests cannot share a number
            try:
                row = conn.execute("SELECT value FROM counters WHERE user_id = ?", (user_id,)).fetchone()
                if row is None:
                    value = 1
                    conn.execute("INSERT INTO counters (user_id, value) VALUES (?, ?)", (user_id, value))
                else:
                    value = row["value"] + 1
                    conn.execute("UPDATE counters SET value = ? WHERE user_id = ?", (value, user_id))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return value

    @staticmethod
    def _build(row) -> Document:
        meta = {k: row[k] for k in ("id", "user_id", "status", "number", "image_ref", "created_at",
                                    "confirmed_at")}
        return document_from_dict(meta, json.loads(row["body"]))

"""Layer 4, Audit log writer: appends each correction to a table (Simplified).

Used to report the correction rate per field (risk R6) and, later, to retrain the classifier."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Sequence

from ..database.sqlite_db import Database
from ..models import Correction


class SqliteAuditLog:
    def __init__(self, db: Database):
        self._db = db

    def record_corrections(self, doc_id: str, user_id: str, corrections: Sequence[Correction],
                           fields_shown: int) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._db.connection() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("INSERT OR REPLACE INTO audit_documents (doc_id, user_id, fields_shown, at)"
                             " VALUES (?, ?, ?, ?)", (doc_id, user_id, fields_shown, now))
                conn.execute("DELETE FROM corrections WHERE doc_id = ?", (doc_id,))
                conn.executemany(
                    "INSERT INTO corrections (doc_id, user_id, field, original, final, kind, at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(doc_id, user_id, c.field, c.original, c.final, c.kind, now) for c in corrections])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def summary(self) -> dict:
        with self._db.connection() as conn:
            docs = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(fields_shown), 0) AS s"
                                " FROM audit_documents").fetchone()
            rows = conn.execute("SELECT field, kind FROM corrections").fetchall()
        by_field = Counter(r["field"] for r in rows if r["kind"] in ("corrected", "suggestion_changed",
                                                                      "added", "removed"))
        accepted = sum(1 for r in rows if r["kind"] == "suggestion_accepted")
        return {"documents": docs["n"], "fields_shown": docs["s"], "corrections": dict(by_field),
                "suggestions_accepted": accepted}

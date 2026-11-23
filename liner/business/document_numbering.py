"""Layer 3, Document numbering (D1 component: Document numbering, Simplified): the next document number for a user. The same number goes on every
row of that document, so the paper document and the sheet can be traced to each other.

Simplified: the counter lives in the repository's ``counters`` table, one counter per user. The
prototype has one user, so there is one counter."""
from __future__ import annotations

from ..interfaces import DocumentRepository
from ..models import User


class SequentialNumbering:
    def __init__(self, repository: DocumentRepository):
        self._repo = repository

    def next_number(self, user: User) -> int:
        return self._repo.next_counter(user.id)

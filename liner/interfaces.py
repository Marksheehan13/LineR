"""The interfaces between components (Deliverable 1, section 1.3).

Each is a ``typing.Protocol``: a component is anything with these methods. Layers depend on these
and never on each other's concrete classes, so replacing one implementation (SQLite for PostgreSQL,
Tesseract for a managed OCR service, the demo user for real accounts) changes one class and one
line in ``liner/app.py``.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Sequence

from .models import (BandRow, Correction, Document, Edits, Extraction, Line, OcrResult, Prediction,
                     ReviewReport, Upload, User)

# ---- layer 6: integration -----------------------------------------------------------------------


class OcrEngine(Protocol):
    def read_text(self, image: bytes) -> OcrResult:
        """Words with positions and confidences. Raises ``OcrError`` when nothing usable is read."""


class DocumentRenderer(Protocol):
    def to_image(self, upload: Upload) -> bytes:
        """The page as PNG/JPEG bytes (a PDF's first page is rasterised)."""


class ExcelExporter(Protocol):
    def export(self, documents: Sequence[Document]) -> bytes:
        """An .xlsx file with one row per tax band of each confirmed document."""


class AccountingPackage(Protocol):  # Deferred: interface only
    def export_rows(self, rows: Sequence[BandRow]) -> None: ...


# ---- layer 4: data access -----------------------------------------------------------------------


class DocumentRepository(Protocol):
    def save(self, doc: Document) -> str:
        """Insert (id is None) or update. Returns the id."""

    def get(self, doc_id: str, user_id: str) -> Document | None:
        """Only returns the document if it belongs to ``user_id`` (risk R8)."""

    def list(self, user_id: str, status: str | None = None) -> list[Document]: ...

    def next_counter(self, user_id: str) -> int:
        """Atomically returns the next document number for this user (1, 2, 3, ...)."""


class ImageStore(Protocol):
    def save(self, user_id: str, data: bytes, ext: str) -> str: ...
    def load(self, ref: str) -> bytes: ...
    def delete(self, ref: str) -> None: ...


class ModelStore(Protocol):
    def save(self, name: str, payload: dict) -> int:
        """Stores a new version, returns its number."""

    def load_latest(self, name: str) -> tuple[int, dict] | None: ...


class AuditLog(Protocol):
    def record_corrections(self, doc_id: str, user_id: str, corrections: Sequence[Correction],
                           fields_shown: int) -> None: ...

    def summary(self) -> dict:
        """{'documents': n, 'fields_shown': n, 'corrections': {field: n}}"""


# ---- layer 3: business logic --------------------------------------------------------------------


class FieldExtractor(Protocol):
    def extract_fields(self, ocr_result: OcrResult) -> Extraction: ...


class Classifier(Protocol):
    def predict(self, supplier: str, detail: str) -> Prediction:
        """Always returns an allowed band and a confidence between 0 and 1."""

    def info(self) -> dict:
        """Model version, training date and size, shown to the user (risk R5)."""


class VatCalculator(Protocol):
    def split_total(self, lines: Sequence[Line], printed_vat: dict[str, Decimal] | None = None
                    ) -> list[BandRow]: ...

    def vat_in_gross(self, gross: Decimal, rate: Decimal) -> Decimal: ...


class ReviewPolicy(Protocol):
    def needs_review(self, document: Document) -> ReviewReport: ...


class Numbering(Protocol):
    def next_number(self, user: User) -> int: ...


class Authenticator(Protocol):
    def authenticate(self, credentials: dict) -> User | None: ...


class DocumentCoder(Protocol):
    """What the controllers call (layer 2 -> layer 3)."""

    def code_document(self, upload: Upload, user: User) -> Document: ...
    def get_review(self, doc_id: str, user: User) -> tuple[Document, ReviewReport] | None: ...
    def check_document(self, doc_id: str, user: User, edits: Edits) -> tuple[Document, ReviewReport]: ...
    def confirm_document(self, doc_id: str, user: User, edits: Edits) -> tuple[Document, ReviewReport]: ...
    def model_info(self) -> dict: ...
    def confirmed_documents(self, user: User) -> list[Document]: ...
    def image_for(self, doc_id: str, user: User) -> bytes | None: ...
    def export_xlsx(self, user: User) -> bytes: ...

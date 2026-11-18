"""Test helpers: build OCR results from rows of text, and a scriptable fake OCR engine."""
from __future__ import annotations

from liner.models import OcrError, OcrResult, Word


def ocr_from_rows(rows: list[str], conf: float = 95.0, width: int = 1000, height: int | None = None) -> OcrResult:
    """Each string is one visual row. Two or more spaces start a new column. conf can be a number or a
    dict {row_index: conf}."""
    words: list[Word] = []
    for i, row in enumerate(rows):
        x = 10.0
        c = conf.get(i, 95.0) if isinstance(conf, dict) else conf
        for col in row.split("  "):
            for tok in col.split(" "):
                if tok:
                    words.append(Word(tok, x, 20 + i * 30, len(tok) * 10, 20, c))
                    x += len(tok) * 10 + 10
            x += 60
    return OcrResult(words, width, height or (60 + len(rows) * 30), engine="fake", engine_version="0")


INVOICE_ROWS = [
    "Corrib Office Supplies", "12 Main Street, Killarney", "INVOICE", "Invoice No: INV-1042",
    "Date: 03/11/2026", "Description  Amount (incl. VAT)  VAT %",
    "A4 copy paper  12.30  23%", "Newspaper  2.50  9%", "Diesel  10.00  0%",
    "VAT 23%  2.30", "VAT 9%  0.21", "VAT 0%  0.00", "Total  24.80", "Thank you",
]

RECEIPT_ROWS = [      # no rate printed on any line
    "Lee Valley Service Station", "Main Road, Cork", "Date: 05/11/2026", "Till 2",
    "Diesel pump 4  10.00", "Newspaper  10.00", "TOTAL  20.00", "Card  20.00", "Thank you",
]


class FakeOcrEngine:
    """Returns a scripted result, or raises, behind the same read_text(image) interface."""

    def __init__(self, result: OcrResult | None = None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, 0

    def read_text(self, image: bytes) -> OcrResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def unreadable() -> FakeOcrEngine:
    return FakeOcrEngine(error=OcrError("Reading the document took too long."))

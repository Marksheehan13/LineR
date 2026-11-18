"""Plain data types shared by every layer. No behaviour beyond (de)serialisation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from .parsing import band_key


class _Unset:
    """Marks 'the user did not touch this field' (None means 'the user cleared it')."""
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET = _Unset()

# ---- OCR output ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float
    conf: float  # 0-100, as reported by the OCR engine


@dataclass
class OcrResult:
    words: list[Word]
    width: int
    height: int
    engine: str = "unknown"
    engine_version: str = ""

    @property
    def mean_conf(self) -> float:
        return sum(w.conf for w in self.words) / len(self.words) if self.words else 0.0


class OcrError(Exception):
    """The OCR step could not produce usable text (bad file, timeout, engine missing)."""


# ---- Extraction / document ----------------------------------------------------------------------


@dataclass(frozen=True)
class BBox:
    """Position on the page image as fractions of its width/height (0-1)."""
    x: float
    y: float
    w: float
    h: float


@dataclass
class Field:
    value: Any = None            # str (supplier), date, or Decimal (total); None = missing
    confidence: float | None = None   # 0-1 from OCR; None when typed by the user
    bbox: BBox | None = None
    source: str = "missing"      # 'ocr' | 'user' | 'missing'


@dataclass
class Prediction:
    band: Decimal
    confidence: float            # 0-1
    reason: str


@dataclass
class Line:
    detail: str = ""
    amount: Decimal | None = None
    printed_rate: Decimal | None = None   # rate printed on the document for this line
    band: Decimal | None = None           # the band to claim
    band_source: str = "none"             # 'printed' | 'suggested' | 'user' | 'none'
    confirmed: bool = False               # a suggested band must be confirmed line by line
    suggestion: Prediction | None = None
    confidence: float | None = None       # OCR confidence 0-1 of the words in this line
    bbox: BBox | None = None
    origin: str = "ocr"                   # 'ocr' | 'manual'
    orig_index: int | None = None         # position in the machine's output (None for added lines)


@dataclass
class Extraction:
    """What the field extractor read from the OCR text."""
    supplier: Field
    date: Field
    total: Field
    lines: list[Line]
    printed_vat: dict[str, Decimal] = field(default_factory=dict)  # band key -> printed VAT amount


@dataclass
class BandRow:
    date: date | None
    supplier: str
    detail: str
    net: Decimal
    rate: Decimal
    vat: Decimal
    gross: Decimal
    number: int | None
    vat_source: str = "calculated"       # 'calculated' | 'printed'


@dataclass
class ReviewFlag:
    field: str          # 'supplier', 'date', 'total', 'line:2', 'document'
    message: str
    severity: str       # 'blocking' | 'warning'
    kind: str = ""      # 'missing' | 'doubtful' | 'suggested' | 'reconcile' | 'rate' | 'vat' | 'low_confidence'


@dataclass
class ReviewReport:
    flags: list[ReviewFlag]
    reconciles: bool
    difference: Decimal            # printed total minus sum of lines (0.00 when they agree)
    suspect_lines: list[int]       # line indexes to look at first when they do not agree
    can_save: bool

    def for_field(self, name: str) -> list[ReviewFlag]:
        return [f for f in self.flags if f.field == name]


@dataclass
class Document:
    user_id: str
    status: str = "draft"          # 'draft' | 'unreadable' | 'confirmed'
    id: str | None = None
    image_ref: str | None = None
    supplier: Field = field(default_factory=Field)
    date: Field = field(default_factory=Field)
    total: Field = field(default_factory=Field)
    lines: list[Line] = field(default_factory=list)
    printed_vat: dict[str, Decimal] = field(default_factory=dict)
    original: dict | None = None   # snapshot of what the machine produced, for the corrections log
    rows: list[BandRow] = field(default_factory=list)
    number: int | None = None
    created_at: str = ""
    confirmed_at: str | None = None
    ocr_info: dict = field(default_factory=dict)
    notice: str | None = None


@dataclass
class Upload:
    filename: str
    kind: str           # 'png' | 'jpg' | 'pdf' (decided from the file's content, not its name)
    data: bytes


@dataclass(frozen=True)
class User:
    id: str
    name: str


@dataclass
class LineEdit:
    index: int
    detail: Any = UNSET
    amount: Any = UNSET
    band: Any = UNSET              # Decimal or None (cleared)
    confirmed: bool = False        # ticked "the suggested band is right"
    remove: bool = False


@dataclass
class Edits:
    supplier: Any = UNSET
    date: Any = UNSET
    total: Any = UNSET
    lines: list[LineEdit] = field(default_factory=list)
    add_line: bool = False


@dataclass
class Correction:
    field: str           # 'supplier', 'date', 'total', 'line.detail', 'line.amount', 'line.band', 'line.added', ...
    original: str
    final: str
    kind: str            # 'corrected' | 'suggestion_accepted' | 'suggestion_changed' | 'added' | 'removed'


# ---- (de)serialisation --------------------------------------------------------------------------


def _enc(v: Any) -> Any:
    if isinstance(v, Decimal):
        return {"$d": str(v)}
    if isinstance(v, date):
        return {"$date": v.isoformat()}
    return v


def _dec(v: Any) -> Any:
    if isinstance(v, dict):
        if "$d" in v:
            return Decimal(v["$d"])
        if "$date" in v:
            return date.fromisoformat(v["$date"])
    return v


def _bbox_to(b: BBox | None):
    return None if b is None else [b.x, b.y, b.w, b.h]


def _bbox_from(v):
    return None if v is None else BBox(*v)


def field_to_dict(f: Field) -> dict:
    return {"value": _enc(f.value), "confidence": f.confidence, "bbox": _bbox_to(f.bbox), "source": f.source}


def field_from_dict(d: dict) -> Field:
    return Field(_dec(d["value"]), d["confidence"], _bbox_from(d["bbox"]), d["source"])


def line_to_dict(ln: Line) -> dict:
    sug = None
    if ln.suggestion:
        sug = {"band": _enc(ln.suggestion.band), "confidence": ln.suggestion.confidence,
               "reason": ln.suggestion.reason}
    return {"detail": ln.detail, "amount": _enc(ln.amount), "printed_rate": _enc(ln.printed_rate),
            "band": _enc(ln.band), "band_source": ln.band_source, "confirmed": ln.confirmed,
            "suggestion": sug, "confidence": ln.confidence, "bbox": _bbox_to(ln.bbox), "origin": ln.origin,
            "orig_index": ln.orig_index}


def line_from_dict(d: dict) -> Line:
    s = d["suggestion"]
    sug = Prediction(_dec(s["band"]), s["confidence"], s["reason"]) if s else None
    return Line(d["detail"], _dec(d["amount"]), _dec(d["printed_rate"]), _dec(d["band"]),
                d["band_source"], d["confirmed"], sug, d["confidence"], _bbox_from(d["bbox"]),
                d.get("origin", "ocr"), d.get("orig_index"))


def row_to_dict(r: BandRow) -> dict:
    return {"date": _enc(r.date), "supplier": r.supplier, "detail": r.detail, "net": _enc(r.net),
            "rate": _enc(r.rate), "vat": _enc(r.vat), "gross": _enc(r.gross), "number": r.number,
            "vat_source": r.vat_source}


def row_from_dict(d: dict) -> BandRow:
    return BandRow(_dec(d["date"]), d["supplier"], d["detail"], _dec(d["net"]), _dec(d["rate"]),
                   _dec(d["vat"]), _dec(d["gross"]), d["number"], d["vat_source"])


def document_to_dict(doc: Document) -> dict:
    return {
        "supplier": field_to_dict(doc.supplier), "date": field_to_dict(doc.date),
        "total": field_to_dict(doc.total), "lines": [line_to_dict(x) for x in doc.lines],
        "printed_vat": {k: _enc(v) for k, v in doc.printed_vat.items()},
        "original": doc.original, "rows": [row_to_dict(r) for r in doc.rows],
        "ocr_info": doc.ocr_info, "notice": doc.notice,
    }


def document_from_dict(meta: dict, body: dict) -> Document:
    """``meta`` holds the indexed columns, ``body`` the JSON document body."""
    return Document(
        user_id=meta["user_id"], status=meta["status"], id=meta["id"], image_ref=meta["image_ref"],
        supplier=field_from_dict(body["supplier"]), date=field_from_dict(body["date"]),
        total=field_from_dict(body["total"]), lines=[line_from_dict(x) for x in body["lines"]],
        printed_vat={k: _dec(v) for k, v in body["printed_vat"].items()},
        original=body["original"], rows=[row_from_dict(r) for r in body["rows"]],
        number=meta["number"], created_at=meta["created_at"], confirmed_at=meta["confirmed_at"],
        ocr_info=body.get("ocr_info", {}), notice=body.get("notice"),
    )


def snapshot(doc: Document) -> dict:
    """What the machine produced, kept so corrections can be measured later (risk R6)."""
    return {
        "supplier": _enc(doc.supplier.value), "date": _enc(doc.date.value), "total": _enc(doc.total.value),
        "lines": [{"detail": ln.detail, "amount": _enc(ln.amount), "band": _enc(ln.band),
                   "band_source": ln.band_source} for ln in doc.lines],
    }


__all__ = [n for n in dir() if not n.startswith("_") or n == "UNSET"] + ["band_key"]

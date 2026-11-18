"""Layer 3, Field extractor: rule-based parsing of the OCR text. Not AI.

Turns words-with-positions into supplier, date, total, lines (detail, amount, printed rate) and the
VAT amounts printed per rate. Anything it cannot find is returned as missing, never guessed.

Known limits (listed in the technical document): one document per page; line amounts are read as
VAT-inclusive; the rightmost amount on a line is taken as the line amount; rates are read only
when printed as a percentage (23%, 13.5%), not as letter codes."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from decimal import Decimal

from ..models import BBox, Extraction, Field, Line, OcrResult, Word
from ..parsing import AMOUNT_RE, RATE_RE, band_key, parse_amount, parse_date, parse_rate

_TOTAL_RE = re.compile(r"\b(?:grand\s+)?total\b|\b(?:amount|balance)\s+due\b|\bto\s+pay\b", re.I)
_NOT_TOTAL_RE = re.compile(r"sub\s*-?\s*total|total\s+(?:vat|tax|excl|ex\b|net|items)|(?:vat|tax|net)\s+total|excl", re.I)
_STOP_RE = re.compile(
    r"^\W*(?:sub\s*-?\s*total|total|grand|vat|tax|balance|amount\s+due|payment|tender|cash|card|visa|"
    r"mastercard|change|thank|rate\b)", re.I)
_HEADER_RE = re.compile(r"\b(?:description|item|items|details?|qty|quantity)\b", re.I)
_META_RE = re.compile(r"invoice|receipt|\btax\b|\bvat\b|\bdate\b|\btel\b|phone|www\.|http|@|order|\bno\b|number|page|"
                      r"\bdue\b|\bref\b", re.I)
_DATE_LABEL_RE = re.compile(r"\b(?:invoice\s+|issue\s+)?date\b", re.I)
_DUE_RE = re.compile(r"\bdue\b", re.I)


@dataclass
class TextLine:
    words: list[Word]
    text: str
    spans: list[tuple[int, int]]       # character span of each word within ``text``
    conf: float                        # mean word confidence, 0-1

    def words_in(self, start: int, end: int) -> list[Word]:
        return [w for w, (a, b) in zip(self.words, self.spans) if a < end and b > start]


def group_lines(ocr: OcrResult) -> list[TextLine]:
    """Words on the same visual row become one line, left to right, top to bottom."""
    words = [w for w in ocr.words if w.text.strip()]
    if not words:
        return []
    med_h = statistics.median(w.h for w in words) or 1.0
    ordered = sorted(words, key=lambda w: w.y + w.h / 2)
    rows: list[list[Word]] = []
    centre = 0.0
    for w in ordered:
        c = w.y + w.h / 2
        if rows and abs(c - centre) <= 0.6 * med_h:
            rows[-1].append(w)
            centre = sum(x.y + x.h / 2 for x in rows[-1]) / len(rows[-1])
        else:
            rows.append([w])
            centre = c
    out: list[TextLine] = []
    for row in rows:
        row.sort(key=lambda w: w.x)
        text, spans, pos = "", [], 0
        for w in row:
            if text:
                text += " "
                pos += 1
            spans.append((pos, pos + len(w.text)))
            text += w.text
            pos += len(w.text)
        out.append(TextLine(row, text, spans, sum(w.conf for w in row) / len(row) / 100.0))
    return out


class RuleBasedFieldExtractor:
    def __init__(self, page_size: tuple[int, int] | None = None):
        self._page = page_size

    def extract_fields(self, ocr_result: OcrResult) -> Extraction:
        lines = group_lines(ocr_result)
        w, h = max(ocr_result.width, 1), max(ocr_result.height, 1)

        def bbox(words: list[Word]) -> BBox | None:
            if not words:
                return None
            x0, y0 = min(x.x for x in words), min(x.y for x in words)
            x1, y1 = max(x.x + x.w for x in words), max(x.y + x.h for x in words)
            return BBox(x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h)

        def field(value, words: list[Word]) -> Field:
            if value is None or not words:
                return Field()
            return Field(value, sum(x.conf for x in words) / len(words) / 100.0, bbox(words), "ocr")

        total_idx, total_val, total_words = self._find_total(lines)
        stop_idx = self._stop_index(lines, total_idx)
        start_idx = self._start_index(lines, stop_idx)

        supplier = self._find_supplier(lines, start_idx, field)
        date_field = self._find_date(lines, stop_idx, field)
        item_lines = self._find_items(lines, start_idx, stop_idx, bbox)
        printed_vat = self._find_printed_vat(lines, stop_idx)

        return Extraction(supplier=supplier, date=date_field, total=field(total_val, total_words),
                          lines=item_lines, printed_vat=printed_vat)

    # -- total -----------------------------------------------------------------------------------
    def _find_total(self, lines: list[TextLine]):
        for i in range(len(lines) - 1, -1, -1):
            t = lines[i].text
            if _TOTAL_RE.search(t) and not _NOT_TOTAL_RE.search(t):
                m = self._last_amount(t)
                if m:
                    val = parse_amount(m.group())
                    if val is not None:
                        return i, val, lines[i].words_in(m.start(), m.end())
        return None, None, []

    # -- layout anchors ----------------------------------------------------------------------
    @staticmethod
    def _stop_index(lines: list[TextLine], total_idx: int | None) -> int:
        """First line after the item rows: the first subtotal / VAT / total / payment line."""
        for i, ln in enumerate(lines):
            if _STOP_RE.match(ln.text) and i > 0:
                return i
        return total_idx if total_idx is not None else len(lines)

    @staticmethod
    def _start_index(lines: list[TextLine], stop_idx: int) -> int:
        for i in range(min(stop_idx, len(lines))):
            t = lines[i].text
            if _HEADER_RE.search(t) and re.search(r"\b(?:amount|price|total|vat|rate|gross|cost)\b", t, re.I):
                return i + 1
        return 0

    # -- supplier ------------------------------------------------------------------------------
    @staticmethod
    def _find_supplier(lines, start_idx, field) -> Field:
        limit = start_idx if start_idx else min(len(lines), 6)
        for ln in lines[:max(limit, 1)]:
            t = ln.text.strip()
            letters = sum(c.isalpha() for c in t)
            if letters >= 3 and letters / max(len(t.replace(" ", "")), 1) >= 0.6 and not _META_RE.search(t) \
                    and not AMOUNT_RE.search(t):
                return field(re.sub(r"\s{2,}", " ", t), ln.words)
        return Field()

    # -- date ----------------------------------------------------------------------------------
    @staticmethod
    def _find_date(lines, stop_idx, field) -> Field:
        candidates = []
        for i, ln in enumerate(lines):
            d = parse_date(ln.text)
            if d is not None:
                labelled = bool(_DATE_LABEL_RE.search(ln.text)) and not _DUE_RE.search(ln.text)
                candidates.append((0 if labelled else 1, i, d, ln))
        if not candidates:
            return Field()
        _, _, d, ln = min(candidates, key=lambda c: (c[0], c[1]))
        # the words that make up the date (all words of the line that contain digits or month text)
        words = [w for w in ln.words if re.search(r"\d", w.text) or re.fullmatch(r"[A-Za-z]{3,9}\.?,?", w.text)]
        date_words = [w for w in words if not re.fullmatch(r"(?i)date|invoice|issue|due", w.text.strip(":"))]
        return field(d, date_words or ln.words)

    # -- lines ---------------------------------------------------------------------------------
    def _find_items(self, lines, start_idx, stop_idx, bbox) -> list[Line]:
        items: list[Line] = []
        for ln in lines[start_idx:stop_idx]:
            text = ln.text
            masked = self._mask_dates(text)
            m = self._last_amount(masked)
            if not m:
                continue
            amount = parse_amount(m.group())
            if amount is None:
                continue
            rate_match = RATE_RE.search(masked)
            printed = parse_rate(rate_match.group(1)) if rate_match else None
            cut = min(x for x in (m.start(), rate_match.start() if rate_match else len(masked)) if x >= 0)
            detail = re.sub(r"[\s€:.\-|]+$", "", masked[:cut]).strip()
            if sum(c.isalpha() for c in detail) < 2:
                continue
            amount_conf = [w.conf / 100.0 for w in ln.words_in(m.start(), m.end())]
            conf = min([ln.conf] + amount_conf)
            printed_dec = printed if printed is not None else None
            items.append(Line(
                detail=detail, amount=amount, printed_rate=printed_dec,
                band=printed_dec, band_source="printed" if printed_dec is not None else "none",
                confidence=conf, bbox=bbox(ln.words), origin="ocr"))
        return items

    # -- printed VAT per rate ---------------------------------------------------------------
    def _find_printed_vat(self, lines, stop_idx) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for ln in lines[stop_idx:]:
            t = ln.text
            if not re.match(r"^\W*vat\b", t, re.I) or re.search(r"total", t, re.I):
                continue
            rm = RATE_RE.search(t)
            am = self._last_amount(t[rm.end():]) if rm else None
            if rm and am:
                rate = parse_rate(rm.group(1))
                val = parse_amount(am.group())
                if rate is not None and val is not None:
                    out[band_key(rate)] = val
        return out

    # -- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def _last_amount(text: str):
        found = None
        for m in AMOUNT_RE.finditer(text):
            found = m
        return found

    @staticmethod
    def _mask_dates(text: str) -> str:
        """Blank out dates so '03.11.2026' is never mistaken for an amount."""
        return re.sub(r"(?<!\d)\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}(?!\d)", lambda m: " " * len(m.group()), text)

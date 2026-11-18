"""Small, pure helpers for reading amounts, dates and rates from text.

Used by the field extractor (text from OCR) and by input validation (text typed by the user).
No I/O and no dependency on any layer."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")

# An amount with exactly two decimals, e.g. 12.30, 1,234.56, 12,30, -5.00, EUR/€ prefix allowed.
AMOUNT_RE = re.compile(
    r"(?<![\d.,])(?:-?€\s?|-)?"
    r"(?:\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}|\d+[.,]\d{2})"
    r"(?!\d|[.,]\d)")
RATE_RE = re.compile(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s?%")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_TEXT_DATE = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})(?!\d)")


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(text: str | None) -> Decimal | None:
    """'€1,234.56' -> Decimal('1234.56'); '12,30' -> Decimal('12.30'); junk -> None.
    Accepts at most two decimals."""
    if text is None:
        return None
    s = text.strip().replace("€", "").replace("EUR", "").replace("−", "-").replace(" ", "")
    if not s:
        return None
    sign = -1 if s.startswith("-") else 1
    if s[:1] in "-+":
        s = s[1:]
    if not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        # the last separator is the decimal point; the other is a thousands separator
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        if len(tail) in (1, 2):          # 12,30 -> decimal comma
            s = f"{head.replace(',', '')}.{tail}"
        elif len(tail) == 3 and head:    # 1,234 -> thousands separator
            s = s.replace(",", "")
        else:
            return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    if d != quantize(d):
        return None
    return quantize(d) * sign


def parse_date(text: str | None) -> date | None:
    """Day-first (Irish) dates: 03/11/2026, 3-11-26, 3.11.2026, 3 Nov 2026, 2026-11-03."""
    if not text:
        return None
    s = text.strip()
    try:
        m = _ISO_DATE.search(s)
        if m:
            return _valid(int(m[1]), int(m[2]), int(m[3]))
        m = _NUM_DATE.search(s)
        if m:
            y = int(m[3])
            y = y + 2000 if y < 100 else y
            return _valid(y, int(m[2]), int(m[1]))
        m = _TEXT_DATE.search(s)
        if m and m[2][:3].lower() in _MONTHS:
            return _valid(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1]))
    except ValueError:
        return None
    return None


def _valid(y: int, mo: int, d: int) -> date | None:
    if not 2000 <= y <= 2100:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_rate(text: str | None) -> Decimal | None:
    """'23', '23%', '13,5 %' -> Decimal; junk -> None. Does not check the allowed set."""
    if text is None:
        return None
    s = text.strip().replace("%", "").replace(",", ".").strip()
    if not re.fullmatch(r"\d{1,2}(\.\d)?", s):
        return None
    return Decimal(s)


def band_key(rate: Decimal) -> str:
    """Stable text key for a rate: Decimal('13.50') -> '13.5', Decimal('23') -> '23', 0 -> '0'."""
    return format(rate.normalize(), "f")

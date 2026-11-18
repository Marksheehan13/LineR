"""Layer 2, Input validation: file type and size checks, and field formats.

Cheap, and tested directly. The file's *content* decides its type (magic bytes), not its name, and
an upload that does not pass is refused before any other component sees it (risk R10)."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from PIL import Image, UnidentifiedImageError

from ..models import Edits, LineEdit, Upload
from ..parsing import parse_amount, parse_date, parse_rate

_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"%PDF-", "pdf"))
_EXT_KIND = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "pdf": "pdf"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_TEXT = 200
MAX_AMOUNT = Decimal("1000000")


class ValidationError(Exception):
    """A message that is safe to show the user."""


@dataclass(frozen=True)
class UploadLimits:
    max_bytes: int = 5 * 1024 * 1024
    max_pixels: int = 25_000_000
    allowed_extensions: tuple[str, ...] = ("png", "jpg", "jpeg", "pdf")
    max_pdf_pages: int = 1


def validate_upload(filename: str | None, data: bytes | None, limits: UploadLimits = UploadLimits()) -> Upload:
    if not filename or not data:
        raise ValidationError("Choose a file to upload.")
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in limits.allowed_extensions:
        raise ValidationError("Upload a PNG, JPEG or PDF file.")
    if len(data) > limits.max_bytes:
        raise ValidationError(f"The file is too large (limit {limits.max_bytes // (1024 * 1024)} MB).")
    kind = next((k for magic, k in _MAGIC if data.startswith(magic)), None)
    if kind is None or kind != _EXT_KIND[ext]:
        raise ValidationError("The file's contents do not match its type. Upload a real PNG, JPEG or PDF.")

    if kind == "pdf":
        try:
            from pdf2image import pdfinfo_from_bytes
            pages = int(pdfinfo_from_bytes(data, timeout=10)["Pages"])
        except Exception:
            raise ValidationError("The PDF could not be opened.") from None
        if pages > limits.max_pdf_pages:
            raise ValidationError(f"One document per upload: this PDF has {pages} pages "
                                  f"(limit {limits.max_pdf_pages}).")
    else:
        try:
            Image.MAX_IMAGE_PIXELS = limits.max_pixels
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                width, height = im.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
            raise ValidationError("The image could not be opened.") from None
        if width * height > limits.max_pixels:
            raise ValidationError("The image is too large.")
    return Upload(filename=name, kind=kind, data=data)


def _clean(text: str) -> str:
    return _CONTROL.sub("", text).strip()


def parse_edits(form: Mapping[str, str], allowed_bands: tuple[Decimal, ...] | None = None
                ) -> tuple[Edits, dict[str, str], dict[str, str]]:
    """Turn submitted form values into typed edits.

    Returns (edits, errors, typed). A value that cannot be read is left out of the edits (the stored
    value is kept), reported in ``errors`` and echoed back in ``typed`` so the user sees what they typed.
    """
    edits = Edits()
    errors: dict[str, str] = {}
    typed: dict[str, str] = {}

    if "supplier" in form:
        s = _clean(form["supplier"])
        if len(s) > MAX_TEXT:
            errors["supplier"], typed["supplier"] = f"Keep the supplier under {MAX_TEXT} characters.", s
        else:
            edits.supplier = s or None
    if "date" in form:
        raw = _clean(form["date"])
        if not raw:
            edits.date = None
        elif (d := parse_date(raw)) is None:
            errors["date"], typed["date"] = "Enter the date as dd/mm/yyyy.", raw
        else:
            edits.date = d
    if "total" in form:
        raw = _clean(form["total"])
        total = parse_amount(raw) if raw else None
        if not raw:
            edits.total = None
        elif total is None or abs(total) > MAX_AMOUNT:
            errors["total"], typed["total"] = "Enter the total as an amount such as 20.00.", raw
        else:
            edits.total = total

    indexes = sorted({int(m.group(1)) for k in form if (m := re.match(r"^line-(\d{1,3})-", k))})
    for i in indexes:
        le = LineEdit(index=i)
        le.remove = form.get(f"line-{i}-remove") is not None
        le.confirmed = form.get(f"line-{i}-confirmed") is not None
        if f"line-{i}-detail" in form:
            detail = _clean(form[f"line-{i}-detail"])
            if len(detail) > MAX_TEXT:
                errors[f"line:{i}:detail"], typed[f"line:{i}:detail"] = \
                    f"Keep the description under {MAX_TEXT} characters.", detail
            else:
                le.detail = detail
        if f"line-{i}-amount" in form:
            raw = _clean(form[f"line-{i}-amount"])
            amount = parse_amount(raw) if raw else None
            if not raw:
                le.amount = None
            elif amount is None or abs(amount) > MAX_AMOUNT:
                errors[f"line:{i}:amount"], typed[f"line:{i}:amount"] = "Enter an amount such as 12.30.", raw
            else:
                le.amount = amount
        if f"line-{i}-band" in form:
            raw = _clean(form[f"line-{i}-band"])
            if not raw:
                le.band = None
            else:
                rate = parse_rate(raw)
                if rate is None or (allowed_bands is not None and rate not in allowed_bands):
                    errors[f"line:{i}:band"], typed[f"line:{i}:band"] = "Choose 23, 13.5, 9 or 0.", raw
                else:
                    le.band = rate
        edits.lines.append(le)
    return edits, errors, typed

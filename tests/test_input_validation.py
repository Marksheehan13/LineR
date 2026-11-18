import io
from decimal import Decimal as D

import pytest
from reportlab.pdfgen import canvas

from liner.config import ALLOWED_BANDS
from liner.models import UNSET
from liner.presentation_logic.input_validation import (UploadLimits, ValidationError, parse_edits,
                                                       validate_upload)
from tests.conftest import png_bytes


def pdf_bytes(pages=1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(100, 700, f"page {i}")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_valid_png_and_jpeg_and_pdf():
    assert validate_upload("a.png", png_bytes()).kind == "png"
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (50, 50)).save(buf, "JPEG")
    assert validate_upload("a.JPG", buf.getvalue()).kind == "jpg"
    assert validate_upload("a.pdf", pdf_bytes()).kind == "pdf"


@pytest.mark.parametrize("name,data", [(None, b"x"), ("a.png", b""), ("a.png", None), ("", png_bytes())])
def test_no_file_is_refused(name, data):
    with pytest.raises(ValidationError):
        validate_upload(name, data)


@pytest.mark.parametrize("name", ["a.exe", "a.txt", "a.svg", "a", "a.png.exe", "a.gif"])
def test_wrong_extension_is_refused(name):
    with pytest.raises(ValidationError, match="PNG, JPEG or PDF"):
        validate_upload(name, png_bytes())


def test_contents_must_match_the_extension():
    with pytest.raises(ValidationError, match="do not match"):
        validate_upload("a.png", b"MZ\x90\x00 not an image")
    with pytest.raises(ValidationError, match="do not match"):
        validate_upload("a.pdf", png_bytes())
    with pytest.raises(ValidationError, match="do not match"):
        validate_upload("a.png", pdf_bytes())


def test_size_limit():
    with pytest.raises(ValidationError, match="too large"):
        validate_upload("a.png", png_bytes(), UploadLimits(max_bytes=100))


def test_corrupt_image_and_corrupt_pdf_are_refused():
    with pytest.raises(ValidationError):
        validate_upload("a.png", b"\x89PNG\r\n\x1a\n" + b"garbage")
    with pytest.raises(ValidationError):
        validate_upload("a.pdf", b"%PDF-1.4 garbage")


def test_pixel_limit():
    with pytest.raises(ValidationError):
        validate_upload("a.png", png_bytes((400, 400)), UploadLimits(max_pixels=1000))


def test_multi_page_pdf_is_refused_one_document_per_upload():
    with pytest.raises(ValidationError, match="One document per upload"):
        validate_upload("a.pdf", pdf_bytes(3))


def test_directory_parts_in_the_filename_are_dropped():
    assert validate_upload("../../etc/passwd.png", png_bytes()).filename == "passwd.png"
    assert validate_upload("C:\\temp\\a.png", png_bytes()).filename == "a.png"


# ---- form fields -----------------------------------------------------------------------------------


def test_parse_edits_reads_typed_values():
    form = {"supplier": " Acme ", "date": "03/11/2026", "total": "22.30", "line-0-detail": "Paper",
            "line-0-amount": "12,30", "line-0-band": "13.5", "line-0-confirmed": "on", "line-1-remove": "on"}
    e, errors, _ = parse_edits(form, ALLOWED_BANDS)
    assert not errors and e.supplier == "Acme" and e.total == D("22.30") and e.date.isoformat() == "2026-11-03"
    assert e.lines[0].amount == D("12.30") and e.lines[0].band == D("13.5") and e.lines[0].confirmed
    assert e.lines[1].remove and e.lines[1].amount is UNSET


def test_blank_means_cleared_and_absent_means_untouched():
    e, errors, _ = parse_edits({"supplier": "", "total": " "}, ALLOWED_BANDS)
    assert e.supplier is None and e.total is None and e.date is UNSET and not errors


def test_bad_values_are_reported_kept_out_of_the_edits_and_echoed():
    form = {"date": "31/02/2026", "total": "abc", "supplier": "x" * 500, "line-0-amount": "12.345",
            "line-0-band": "21", "line-0-detail": "ok"}
    e, errors, typed = parse_edits(form, ALLOWED_BANDS)
    assert set(errors) == {"date", "total", "supplier", "line:0:amount", "line:0:band"}
    assert e.date is UNSET and e.total is UNSET and e.supplier is UNSET
    assert e.lines[0].amount is UNSET and e.lines[0].band is UNSET and e.lines[0].detail == "ok"
    assert typed["total"] == "abc"


def test_control_characters_are_stripped():
    e, _, _ = parse_edits({"supplier": "Ac\x00me\x07"}, ALLOWED_BANDS)
    assert e.supplier == "Acme"


def test_absurd_amounts_are_refused():
    _, errors, _ = parse_edits({"total": "99999999999.00"}, ALLOWED_BANDS)
    assert "total" in errors

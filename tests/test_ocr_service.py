import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from liner.integration.ocr_service import TesseractOcrEngine
from liner.integration.pdf_renderer import PillowPopplerRenderer
from liner.models import OcrError, OcrResult, Upload
from tests.conftest import needs_tesseract, png_bytes
from tools.make_documents import _font
from tests.helpers import FakeOcrEngine, ocr_from_rows
from tests.test_input_validation import pdf_bytes


def text_png(text="Invoice Total 12.30") -> bytes:
    img = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(img).text((40, 60), text, fill="black",
                             font=_font("DejaVuSans.ttf", 48))
    buf = io.BytesIO(); img.save(buf, "PNG")
    return buf.getvalue()


def test_the_fake_engine_has_the_same_shape_as_the_real_one():
    res = FakeOcrEngine(ocr_from_rows(["Total  12.30"])).read_text(b"")
    assert isinstance(res, OcrResult) and res.words[0].text == "Total"
    assert {"text", "x", "y", "w", "h", "conf"} <= set(res.words[0].__dataclass_fields__)


@needs_tesseract
def test_tesseract_returns_words_with_positions_and_confidences():
    res = TesseractOcrEngine().read_text(text_png())
    assert [w.text for w in res.words][:2] == ["Invoice", "Total"] or "Invoice" in [w.text for w in res.words]
    assert all(0 <= w.conf <= 100 and w.w > 0 and w.h > 0 for w in res.words)
    assert res.engine == "tesseract" and res.engine_version and res.width >= 900


@needs_tesseract
@pytest.mark.parametrize("data", [b"", b"not an image at all", b"\x89PNG\r\n\x1a\ntruncated"])
def test_an_unreadable_file_raises_a_clear_error_not_a_crash(data):
    with pytest.raises(OcrError, match="not a readable image"):
        TesseractOcrEngine().read_text(data)


@needs_tesseract
def test_a_blank_page_gives_no_words_rather_than_garbage():
    assert TesseractOcrEngine().read_text(png_bytes()).words == []


def test_a_missing_engine_is_reported_as_an_ocr_error(monkeypatch):
    import pytesseract

    def boom(*a, **k):
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "image_to_data", boom)
    with pytest.raises(OcrError, match="not installed"):
        TesseractOcrEngine().read_text(png_bytes())


def test_a_timeout_is_reported_as_an_ocr_error(monkeypatch):
    import pytesseract

    def slow(*a, **k):
        raise RuntimeError("Tesseract process timeout")
    monkeypatch.setattr(pytesseract, "image_to_data", slow)
    with pytest.raises(OcrError, match="too long"):
        TesseractOcrEngine().read_text(png_bytes())


# ---- renderer -----------------------------------------------------------------------------------------


def test_renderer_reencodes_images_and_caps_their_size():
    big = png_bytes((6000, 4000))
    out = PillowPopplerRenderer().to_image(Upload("a.png", "png", big))
    im = Image.open(io.BytesIO(out))
    assert im.format == "PNG" and max(im.size) <= 3000


def test_renderer_rasterises_the_first_page_of_a_pdf():
    out = PillowPopplerRenderer().to_image(Upload("a.pdf", "pdf", pdf_bytes(1)))
    assert Image.open(io.BytesIO(out)).format == "PNG"


@pytest.mark.parametrize("kind,data", [("png", b"junk"), ("pdf", b"%PDF-1.4 junk")])
def test_renderer_failures_are_ocr_errors(kind, data):
    with pytest.raises(OcrError):
        PillowPopplerRenderer().to_image(Upload("a", kind, data))

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from liner.app import build_services, create_app
from liner.config import Config
from liner.models import Upload, User
from tests.helpers import INVOICE_ROWS, RECEIPT_ROWS, FakeOcrEngine, ocr_from_rows
from tools.synthetic_lines import generate_lines

HAS_TESSERACT = shutil.which("tesseract") is not None
needs_tesseract = pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract is not installed")

USER = User("demo", "Demo bookkeeper")


def small_training_lines():
    return generate_lines(600, seed=13)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path / "var")


def png_bytes(size=(400, 300), colour="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def upload() -> Upload:
    return Upload("doc.png", "png", png_bytes())


@pytest.fixture
def make_service(config):
    """make_service(rows_or_engine) -> a fully wired coding service using a fake OCR engine."""
    def _make(source):
        engine = source if isinstance(source, FakeOcrEngine) else FakeOcrEngine(ocr_from_rows(source))
        return build_services(config, ocr=engine, make_training_lines=small_training_lines), engine
    return _make


@pytest.fixture
def invoice_service(make_service):
    return make_service(INVOICE_ROWS)[0]


@pytest.fixture
def receipt_service(make_service):
    return make_service(RECEIPT_ROWS)[0]


@pytest.fixture
def client(config):
    app = create_app(config, ocr=FakeOcrEngine(ocr_from_rows(INVOICE_ROWS)), make_training_lines=small_training_lines)
    app.config["TESTING"] = True
    return app.test_client()

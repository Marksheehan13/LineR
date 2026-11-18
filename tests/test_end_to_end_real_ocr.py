"""The whole feature with the real Tesseract engine on generated documents (skipped if Tesseract is absent).

Documents are synthetic and rendered by tools.make_documents. These tests show the pieces fit together;
they say nothing about how real receipts would read (see the evaluation in the test report)."""
import io
import random
import re
from decimal import Decimal as D

import pytest
from PIL import Image, ImageFilter
from openpyxl import load_workbook

from liner.app import create_app
from tests.conftest import needs_tesseract, small_training_lines
from tools.make_documents import degrade, make_spec, render

pytestmark = needs_tesseract


@pytest.fixture
def real_client(config):
    app = create_app(config, make_training_lines=small_training_lines)      # real OCR engine
    app.config["TESTING"] = True
    return app.test_client()


def upload(client, data, name):
    r = client.post("/upload", data={"document": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)
    return re.search(r"/documents/([0-9a-f]{32})", r.headers["Location"]).group(1)


def clean_png(layout, seed, n_lines=3):
    spec = make_spec(random.Random(seed), layout=layout, n_lines=n_lines)
    data, _ = degrade(render(spec, random.Random(seed)), "clean", random.Random(seed))
    return spec, data


def test_clean_invoice_end_to_end(real_client):
    spec, data = clean_png("invoice", 11)
    doc_id = upload(real_client, data, "invoice.png")
    html = real_client.get(f"/documents/{doc_id}").get_data(as_text=True)
    assert spec.supplier in html and f"{spec.total:.2f}" in html and "Lines add up to the printed total." in html
    r = real_client.post(f"/documents/{doc_id}", data={"action": "accept"})
    assert r.status_code == 302
    ws = load_workbook(io.BytesIO(real_client.get("/export.xlsx").data)).active
    gross = sum(D(str(ws.cell(i, 7).value)) for i in range(2, ws.max_row + 1))
    assert round(gross, 2) == spec.total
    assert {ws.cell(i, 2).value for i in range(2, ws.max_row + 1)} == {spec.supplier}


def test_clean_receipt_without_rates_needs_each_suggestion_confirmed(real_client):
    spec, data = clean_png("receipt", 4, n_lines=2)
    doc_id = upload(real_client, data, "receipt.png")
    html = real_client.get(f"/documents/{doc_id}").get_data(as_text=True)
    assert "AI suggestion" in html and "Needs review" in html
    r = real_client.post(f"/documents/{doc_id}", data={"action": "accept"})
    assert r.status_code == 200 and "Not saved." in r.get_data(as_text=True)


def test_pdf_upload_is_read_the_same_way(real_client):
    spec, png = clean_png("invoice", 11)
    buf = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(buf, "PDF", resolution=150)
    doc_id = upload(real_client, buf.getvalue(), "invoice.pdf")
    assert spec.supplier in real_client.get(f"/documents/{doc_id}").get_data(as_text=True)


def test_a_blurred_unreadable_image_is_handled_without_crashing(real_client):
    spec, png = clean_png("invoice", 11)
    img = Image.open(io.BytesIO(png)).convert("RGB").filter(ImageFilter.GaussianBlur(25))
    buf = io.BytesIO(); img.save(buf, "PNG")
    doc_id = upload(real_client, buf.getvalue(), "blur.png")
    html = real_client.get(f"/documents/{doc_id}").get_data(as_text=True)
    assert "could not be read automatically" in html and 'name="supplier" value=""' in html
    assert real_client.get("/").status_code == 200


def test_a_blank_page_is_unreadable(real_client):
    buf = io.BytesIO(); Image.new("RGB", (800, 600), "white").save(buf, "PNG")
    doc_id = upload(real_client, buf.getvalue(), "blank.png")
    assert "could not be read automatically" in real_client.get(f"/documents/{doc_id}").get_data(as_text=True)

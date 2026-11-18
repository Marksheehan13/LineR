"""The five-step journey through the Flask screens (fake OCR so the result is exact)."""
import io
import re

import pytest
from openpyxl import load_workbook

from liner.app import create_app
from tests.conftest import png_bytes, small_training_lines
from tests.helpers import FakeOcrEngine, RECEIPT_ROWS, ocr_from_rows, unreadable
from tests.test_input_validation import pdf_bytes


def post_upload(client, name="doc.png", data=None):
    return client.post("/upload", data={"document": (io.BytesIO(data if data is not None else png_bytes()), name)},
                       content_type="multipart/form-data")


def doc_id_from(resp):
    return re.search(r"/documents/([0-9a-f]{32})", resp.headers["Location"]).group(1)


def make_client(config, rows=None, engine=None):
    app = create_app(config, ocr=engine or FakeOcrEngine(ocr_from_rows(rows)), make_training_lines=small_training_lines)
    app.config["TESTING"] = True
    return app.test_client()


def test_upload_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Upload a document" in r.data and b"synthetic documents only" in r.data


def test_full_journey_upload_review_accept_rows_download(client):
    r = post_upload(client)
    assert r.status_code == 302
    doc_id = doc_id_from(r)

    page = client.get(f"/documents/{doc_id}")                       # steps 2-3
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and "Corrib Office Supplies" in html and "AI-read: suggestion only" in html
    assert f"/documents/{doc_id}/image" in html and "24.80" in html and "Lines add up to the printed total." in html
    assert client.get(f"/documents/{doc_id}/image").mimetype == "image/png"

    r = client.post(f"/documents/{doc_id}", data={"action": "accept"})  # step 4
    assert r.status_code == 302 and "/rows" in r.headers["Location"]
    rows = client.get(r.headers["Location"]).get_data(as_text=True)
    assert rows.count('<tr class="hl">') == 3 and "Corrib Office Supplies" in rows

    x = client.get("/export.xlsx")                                      # step 5
    assert x.status_code == 200 and "spreadsheetml" in x.mimetype and "attachment" in x.headers["Content-Disposition"]
    ws = load_workbook(io.BytesIO(x.data)).active
    assert ws.max_row == 4 and {ws.cell(i, 8).value for i in range(2, 5)} == {1}


def test_reviewing_a_confirmed_document_goes_to_the_rows(client):
    doc_id = doc_id_from(post_upload(client))
    client.post(f"/documents/{doc_id}", data={"action": "accept"})
    assert "/rows" in client.get(f"/documents/{doc_id}").headers["Location"]


@pytest.mark.parametrize("name,data,message", [
    ("a.exe", png_bytes(), b"PNG, JPEG or PDF"), ("a.png", b"MZ not an image", b"do not match"),
    ("a.pdf", pdf_bytes(3), b"One document per upload"), ("a.png", b"", b"Choose a file"),
])
def test_bad_uploads_show_a_message_and_nothing_is_stored(client, name, data, message):
    r = post_upload(client, name, data)
    assert r.status_code == 400 and message in r.data
    assert b"Coded rows" in client.get("/rows").data and b"No confirmed documents" in client.get("/rows").data


def test_upload_without_a_file_field(client):
    assert client.post("/upload", data={}).status_code == 400


def test_oversized_request_is_refused(config):
    config.max_upload_bytes = 1000
    c = make_client(config, rows=RECEIPT_ROWS)
    r = c.post("/upload", data={"document": (io.BytesIO(b"x" * 2_000_000), "a.png")}, content_type="multipart/form-data")
    assert r.status_code == 413 and b"too large" in r.data


def test_unreadable_document_shows_the_message_and_a_blank_form(config):
    c = make_client(config, engine=unreadable())
    r = post_upload(c)
    page = c.get(f"/documents/{doc_id_from(r)}")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and "could not be read automatically" in html and "enter the details" in html
    assert 'name="supplier" value=""' in html
    assert c.get("/").status_code == 200                            # the application keeps working


def test_a_blocked_save_explains_why_and_keeps_the_users_edits(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    doc_id = doc_id_from(post_upload(c))
    r = c.post(f"/documents/{doc_id}", data={"action": "accept", "supplier": "My Edit", "line-0-detail": "Diesel pump 4",
                                            "line-0-amount": "10.00", "line-0-band": "0", "line-1-detail": "Newspaper",
                                            "line-1-amount": "10.00", "line-1-band": "9"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Not saved." in html and "no rate is printed" in html and "My Edit" in html
    assert b"No confirmed documents" in c.get("/rows").data


def test_ticking_each_suggested_line_then_accepting_saves(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    doc_id = doc_id_from(post_upload(c))
    form = {"action": "accept", "line-0-detail": "Diesel pump 4", "line-0-amount": "10.00", "line-0-band": "0",
            "line-0-confirmed": "on", "line-1-detail": "Newspaper", "line-1-amount": "10.00", "line-1-band": "9",
            "line-1-confirmed": "on"}
    r = c.post(f"/documents/{doc_id}", data=form)
    assert r.status_code == 302
    assert c.get("/rows").get_data(as_text=True).count("<tr") == 3        # header + two band rows


def test_check_again_applies_edits_and_recalculates_without_saving(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    doc_id = doc_id_from(post_upload(c))
    r = c.post(f"/documents/{doc_id}", data={"action": "check", "total": "25.00"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "difference +5.00" in html and "25.00" in html
    assert b"No confirmed documents" in c.get("/rows").data


def test_bad_typed_values_are_reported_next_to_the_field(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    doc_id = doc_id_from(post_upload(c))
    html = c.post(f"/documents/{doc_id}", data={"action": "accept", "date": "31/02/2026", "total": "abc"}).get_data(as_text=True)
    assert "Enter the date as dd/mm/yyyy." in html and "Enter the total as an amount" in html and 'value="abc"' in html


def test_add_a_line_and_remove_a_line(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    doc_id = doc_id_from(post_upload(c))
    html = c.post(f"/documents/{doc_id}", data={"action": "add_line"}).get_data(as_text=True)
    assert 'name="line-2-detail"' in html
    html = c.post(f"/documents/{doc_id}", data={"action": "check", "line-2-remove": "on"}).get_data(as_text=True)
    assert 'name="line-2-detail"' not in html


def test_suggested_lines_show_the_ai_label_reason_and_a_confirm_box(config):
    c = make_client(config, rows=RECEIPT_ROWS)
    html = c.get(f"/documents/{doc_id_from(post_upload(c))}").get_data(as_text=True)
    assert "AI suggestion" in html and "Suggested band is right" in html and "not tax advice" in html
    assert "Naive Bayes model v1" in html and "rate table as of" in html and "Needs review" in html


def test_unknown_document_is_a_404_page(client):
    for url in ("/documents/" + "0" * 32, "/documents/" + "0" * 32 + "/image"):
        assert client.get(url).status_code == 404
    assert client.post("/documents/" + "0" * 32, data={"action": "accept"}).status_code == 404


def test_the_stylesheet_is_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200 and b"--blue" in r.data
    assert b"/static/style.css" in client.get("/").data


def test_responses_carry_security_headers(client):
    assert client.get("/").headers["X-Content-Type-Options"] == "nosniff"


def test_user_supplied_text_is_escaped_in_the_page(config):
    rows = [r.replace("Corrib Office Supplies", "Acme") for r in ["Acme", "Date: 03/11/2026", "Paint  5.00  23%", "Total  5.00"]]
    c = make_client(config, rows=rows)
    doc_id = doc_id_from(post_upload(c))
    html = c.post(f"/documents/{doc_id}", data={"action": "check", "supplier": "<script>alert(1)</script>"}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html

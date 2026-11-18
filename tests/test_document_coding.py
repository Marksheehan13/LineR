"""Scenario tests for the chosen feature (Deliverable 1, section 1.6), run through the coding service
with a fake OCR engine so they do not depend on image quality."""
from datetime import date
from decimal import Decimal as D

import pytest

from liner.models import Edits, LineEdit, Upload
from tests.conftest import USER
from tests.helpers import FakeOcrEngine, INVOICE_ROWS, ocr_from_rows, unreadable


def accept_all(doc):
    """Edits that tick every suggested band, as the user would line by line."""
    return Edits(lines=[LineEdit(i, confirmed=True) for i in range(len(doc.lines))])


# ---- scenario 1: a clean invoice with printed rates ----------------------------------------------------


def test_clean_invoice_is_filled_in_with_no_typing_and_split_one_row_per_rate(invoice_service, upload):
    doc = invoice_service.code_document(upload, USER)
    assert doc.status == "draft" and doc.supplier.value == "Corrib Office Supplies"
    assert doc.date.value == date(2026, 11, 3) and doc.total.value == D("24.80")
    assert [l.band_source for l in doc.lines] == ["printed"] * 3

    final, report = invoice_service.confirm_document(doc.id, USER, Edits())
    assert report.can_save and final.status == "confirmed" and final.number == 1
    assert sorted(r.rate for r in final.rows) == [D("0"), D("9"), D("23")]
    assert all(r.number == 1 and r.supplier == "Corrib Office Supplies" and r.date == date(2026, 11, 3)
               for r in final.rows)
    assert sum(r.gross for r in final.rows) == D("24.80")
    assert {r.rate: r.vat_source for r in final.rows} == {D("23"): "printed", D("9"): "printed", D("0"): "printed"}


# ---- scenario 2: a EUR 20 receipt, EUR 10 fuel + EUR 10 food --------------------------------------------


def test_twenty_euro_receipt_splits_into_two_rows_sharing_one_number(receipt_service, upload):
    doc = receipt_service.code_document(upload, USER)
    edits = Edits(lines=[LineEdit(0, band=D("0"), confirmed=True), LineEdit(1, band=D("9"), confirmed=True)])   # fuel 0%, food 9%, each ticked
    final, _ = receipt_service.confirm_document(doc.id, USER, edits)
    assert final.status == "confirmed" and len(final.rows) == 2
    assert {r.number for r in final.rows} == {1} and sum(r.gross for r in final.rows) == D("20.00")
    assert {r.rate: r.gross for r in final.rows} == {D("0"): D("10.00"), D("9"): D("10.00")}


# ---- scenario 3: a line with no printed rate --------------------------------------------------------------


def test_line_with_no_rate_gets_a_suggestion_that_cannot_be_bulk_accepted(receipt_service, upload):
    doc = receipt_service.code_document(upload, USER)
    assert all(l.band_source == "suggested" and l.suggestion and 0 <= l.suggestion.confidence <= 1 for l in doc.lines)
    assert doc.lines[0].band == D("0")                                  # "Diesel pump 4"

    doc, report = receipt_service.confirm_document(doc.id, USER, Edits())     # nothing confirmed
    assert doc.status == "draft" and not report.can_save
    assert [f.kind for f in report.flags if f.kind == "suggested"] == ["suggested", "suggested"]

    _, report = receipt_service.confirm_document(doc.id, USER, Edits(lines=[LineEdit(0, confirmed=True)]))
    assert not report.can_save                                           # one line still unconfirmed


def test_changing_a_suggested_band_recalculates_the_row_and_records_the_correction(receipt_service, upload, config):
    doc = receipt_service.code_document(upload, USER)
    edits = Edits(lines=[LineEdit(0, confirmed=True), LineEdit(1, band=D("23"))])   # keep line 0, change line 1
    final, _ = receipt_service.confirm_document(doc.id, USER, edits)
    assert final.status == "confirmed"
    by_rate = {r.rate: r for r in final.rows}
    assert by_rate[D("23")].vat == D("1.87") and by_rate[D("23")].net == D("8.13")

    from liner.data_access.audit_log import SqliteAuditLog
    from liner.database.sqlite_db import Database
    summary = SqliteAuditLog(Database(config.db_path)).summary()
    assert summary["documents"] == 1 and summary["suggestions_accepted"] == 1
    assert summary["corrections"] == {"line.band": 1}


def test_editing_a_description_gives_a_fresh_suggestion(receipt_service, upload):
    doc = receipt_service.code_document(upload, USER)
    before = doc.lines[1].suggestion.reason
    doc, _ = receipt_service.check_document(doc.id, USER, Edits(lines=[LineEdit(1, detail="A4 copy paper")]))
    assert doc.lines[1].band == D("23") and doc.lines[1].suggestion.reason != before
    assert doc.lines[1].confirmed is False


# ---- scenario 4: unreadable image / failures (risk R4) ------------------------------------------------------


@pytest.mark.parametrize("engine", [
    unreadable(),
    FakeOcrEngine(error=RuntimeError("engine blew up")),
    FakeOcrEngine(ocr_from_rows(["a"])),                                  # almost no text
    FakeOcrEngine(ocr_from_rows(["blurry words here ok"], conf=10.0)),     # garbage confidence
])
def test_unreadable_document_prefills_nothing_and_the_app_keeps_working(make_service, upload, engine):
    service, _ = make_service(engine)
    doc = service.code_document(upload, USER)
    assert doc.status == "unreadable" and "enter the details" in doc.notice
    assert doc.supplier.value is None and doc.date.value is None and doc.total.value is None and doc.lines == []
    assert service.get_review(doc.id, USER)[1].can_save is False
    assert service.code_document(upload, USER).status == "unreadable"      # and it still works afterwards


def test_an_unreadable_document_can_be_entered_by_hand_and_saved(make_service, upload):
    service, _ = make_service(unreadable())
    doc = service.code_document(upload, USER)
    doc, _ = service.check_document(doc.id, USER, Edits(supplier="Acme", date=date(2026, 11, 3), total=D("12.30"), add_line=True))
    doc, _ = service.check_document(doc.id, USER, Edits(lines=[LineEdit(0, detail="Paper", amount=D("12.30"), band=D("23"))]))
    final, report = service.confirm_document(doc.id, USER, Edits())
    assert report.can_save and final.status == "confirmed" and final.rows[0].gross == D("12.30")


def test_a_wrong_file_that_cannot_be_rendered_is_unreadable_not_a_crash(make_service):
    service, _ = make_service(INVOICE_ROWS)
    doc = service.code_document(Upload("x.png", "png", b"not an image"), USER)
    assert doc.status == "unreadable" and doc.image_ref is None


def test_a_classifier_failure_leaves_the_band_for_the_user(receipt_service, upload, monkeypatch):
    monkeypatch.setattr(receipt_service._classifier, "predict", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    doc = receipt_service.code_document(upload, USER)
    assert doc.status == "draft" and all(l.band is None for l in doc.lines)
    _, report = receipt_service.confirm_document(doc.id, USER, Edits())
    assert not report.can_save


# ---- scenario 5: lines that do not add up (risk R11) ------------------------------------------------------------


def test_lines_that_do_not_add_up_are_not_saved_and_the_difference_is_shown(make_service, upload):
    rows = [r.replace("Total  24.80", "Total  25.80") for r in INVOICE_ROWS]
    service, _ = make_service(rows)
    doc = service.code_document(upload, USER)
    final, report = service.confirm_document(doc.id, USER, Edits())
    assert final.status == "draft" and not report.can_save and report.difference == D("1.00")
    assert "1.00" in next(f.message for f in report.flags if f.kind == "reconcile")
    assert service.confirmed_documents(USER) == []
    # a number was not used up by the failed attempt
    fixed, _ = service.confirm_document(doc.id, USER, Edits(total=D("24.80")))
    assert fixed.status == "confirmed" and fixed.number == 1


def test_a_forged_total_at_the_bottom_is_caught_by_the_reconcile_check(make_service, upload):   # risk R10
    service, _ = make_service(INVOICE_ROWS + ["Total  0.00"])
    doc = service.code_document(upload, USER)
    assert doc.total.value == D("0.00")
    final, report = service.confirm_document(doc.id, USER, Edits())
    assert final.status == "draft" and not report.reconciles


# ---- numbering, idempotency, isolation -------------------------------------------------------------------------------


def test_numbers_are_sequential_and_repeated_on_every_row(make_service, upload):
    service, _ = make_service(INVOICE_ROWS)
    nums = []
    for _ in range(3):
        doc = service.code_document(upload, USER)
        final, _ = service.confirm_document(doc.id, USER, Edits())
        assert len({r.number for r in final.rows}) == 1
        nums.append(final.number)
    assert nums == [1, 2, 3]


def test_confirming_twice_does_not_number_the_document_twice(invoice_service, upload):
    doc = invoice_service.code_document(upload, USER)
    a, _ = invoice_service.confirm_document(doc.id, USER, Edits())
    b, _ = invoice_service.confirm_document(doc.id, USER, Edits())
    assert a.number == b.number == 1 and len(invoice_service.confirmed_documents(USER)) == 1


def test_a_confirmed_document_cannot_be_edited(invoice_service, upload):
    doc = invoice_service.code_document(upload, USER)
    invoice_service.confirm_document(doc.id, USER, Edits())
    with pytest.raises(ValueError):
        invoice_service.check_document(doc.id, USER, Edits(total=D("1.00")))


def test_another_user_cannot_read_edit_or_confirm_a_document(invoice_service, upload):
    from liner.models import User
    doc = invoice_service.code_document(upload, USER)
    other = User("someone-else", "Other")
    assert invoice_service.get_review(doc.id, other) is None and invoice_service.image_for(doc.id, other) is None
    with pytest.raises(LookupError):
        invoice_service.confirm_document(doc.id, other, Edits())


# ---- corrections log ------------------------------------------------------------------------------------------------------


def test_typed_corrections_are_logged_with_before_and_after(make_service, upload, config):
    rows = [r.replace("Total  24.80", "Total  24.80") for r in INVOICE_ROWS]
    rows[0] = "Corib Office Suplies"               # an OCR misread the user fixes
    service, _ = make_service(rows)
    doc = service.code_document(upload, USER)
    service.confirm_document(doc.id, USER, Edits(supplier="Corrib Office Supplies"))
    import sqlite3
    con = sqlite3.connect(config.db_path)
    got = con.execute("SELECT field, original, final, kind FROM corrections").fetchall()
    assert got == [("supplier", "Corib Office Suplies", "Corrib Office Supplies", "corrected")]


def test_exported_workbook_holds_only_confirmed_rows(invoice_service, upload):
    import io
    from openpyxl import load_workbook
    invoice_service.code_document(upload, USER)                         # left as a draft
    doc = invoice_service.code_document(upload, USER)
    invoice_service.confirm_document(doc.id, USER, Edits())
    ws = load_workbook(io.BytesIO(invoice_service.export_xlsx(USER))).active
    assert ws.max_row == 4 and {ws.cell(i, 8).value for i in range(2, 5)} == {1}


def test_text_that_starts_with_equals_is_exported_as_text(make_service, upload):       # risk R7
    import io
    from openpyxl import load_workbook
    rows = [r.replace("Newspaper", "=HYPERLINK(1)") for r in INVOICE_ROWS]
    service, _ = make_service(rows)
    doc = service.code_document(upload, USER)
    service.confirm_document(doc.id, USER, Edits())
    ws = load_workbook(io.BytesIO(service.export_xlsx(USER))).active
    details = [ws.cell(i, 3).value for i in range(2, ws.max_row + 1)]
    assert "'=HYPERLINK(1)" in details and not any(d.startswith("=") for d in details)

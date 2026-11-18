import io
from datetime import date
from decimal import Decimal as D

import pytest
from openpyxl import load_workbook

from liner.integration.excel_exporter import COLUMNS, OpenpyxlExcelExporter, safe_text
from liner.models import BandRow, Document


def doc(number, status="confirmed", detail="Paper", supplier="Acme"):
    d = Document(user_id="demo", status=status, number=number)
    d.rows = [BandRow(date(2026, 11, 3), supplier, detail, D("10.00"), D("23"), D("2.30"), D("12.30"), number),
              BandRow(date(2026, 11, 3), supplier, "Diesel", D("5.00"), D("0"), D("0.00"), D("5.00"), number)]
    return d


def sheet(documents):
    wb = load_workbook(io.BytesIO(OpenpyxlExcelExporter().export(documents)))
    return wb.active


def test_columns_and_order_match_the_layout_the_user_already_uses():
    ws = sheet([doc(1)])
    assert [c.value for c in ws[1]] == ["Date", "Supplier", "Detail", "Net", "Tax rate", "VAT", "Gross", "Number"]
    assert tuple(c.value for c in ws[1]) == COLUMNS


def test_one_row_per_band_with_the_same_number_and_real_numbers():
    ws = sheet([doc(7)])
    assert ws.max_row == 3
    r2, r3 = [[c.value for c in ws[i]] for i in (2, 3)]
    assert r2[7] == r3[7] == 7
    assert r2[3] == 10.0 and r2[5] == 2.3 and r2[6] == 12.3 and abs(r2[4] - 0.23) < 1e-9
    assert r2[0].date().isoformat() == "2026-11-03" and ws.cell(2, 5).number_format == "0.0%"


def test_only_confirmed_documents_are_exported_in_number_order():
    ws = sheet([doc(2), doc(1), doc(3, status="draft")])
    assert [ws.cell(i, 8).value for i in range(2, ws.max_row + 1)] == [1, 1, 2, 2]


@pytest.mark.parametrize("text", ["=1+1", "+cmd|' /C calc'!A0", "-2+3", "@SUM(A1)", "\t=1", "\r=1"])
def test_formula_leading_text_is_written_as_text_with_a_quote(text):      # risk R7
    ws = sheet([doc(1, detail=text, supplier=text)])
    for col in (2, 3):
        cell = ws.cell(2, col)
        assert cell.data_type == "s" and cell.value.startswith("'") and not cell.value.startswith("=")


def test_ordinary_text_is_unchanged_and_illegal_characters_are_removed():
    assert safe_text("Diesel") == "Diesel" and safe_text("A\x00B\x07") == "AB" and safe_text(None) == ""


def test_empty_export_still_has_the_header_row():
    ws = sheet([])
    assert ws.max_row == 1 and ws["A1"].value == "Date"

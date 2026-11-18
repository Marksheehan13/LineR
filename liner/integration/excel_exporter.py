"""Layer 6, Excel exporter: one row per tax band, in the layout the user already uses.

Text is written as plain strings; text that starts with = + - @ (or a tab/return) gets a leading
quote so Excel cannot run it as a formula when the sheet is opened (risk R7)."""
from __future__ import annotations

import io
import re
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from ..models import Document

COLUMNS = ("Date", "Supplier", "Detail", "Net", "Tax rate", "VAT", "Gross", "Number")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def safe_text(value: str | None) -> str:
    text = _ILLEGAL.sub("", value or "")
    if text.startswith(_FORMULA_START):
        text = "'" + text
    return text


class OpenpyxlExcelExporter:
    def export(self, documents: Sequence[Document]) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Coded rows"
        ws.append(list(COLUMNS))
        for cell in ws[1]:
            cell.font = Font(bold=True)
        confirmed = sorted((d for d in documents if d.status == "confirmed"), key=lambda d: d.number or 0)
        for doc in confirmed:
            for r in doc.rows:
                ws.append([r.date, None, None, float(r.net), float(r.rate) / 100, float(r.vat),
                           float(r.gross), r.number])
                row = ws.max_row
                for col, text in ((2, r.supplier), (3, r.detail)):
                    c = ws.cell(row=row, column=col)
                    c.value = safe_text(text)
                    c.data_type = "s"      # never a formula, whatever the text starts with
                ws.cell(row=row, column=1).number_format = "dd/mm/yyyy"
                for col in (4, 6, 7):
                    ws.cell(row=row, column=col).number_format = "#,##0.00"
                ws.cell(row=row, column=5).number_format = "0.0%"
                ws.cell(row=row, column=3).alignment = Alignment(wrap_text=False)
        for col, width in zip("ABCDEFGH", (12, 28, 48, 12, 10, 12, 12, 9)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

"""Layer 2, Controllers (Flask routes) and view models.

Controllers validate the request, call the business layer through ``DocumentCoder`` and shape the
result for a template. They hold no business rules. View models are small data classes kept in this
module (Simplified in Deliverable 1: the target has a separate package for them)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from flask import (Blueprint, Response, abort, redirect, render_template, request, url_for)

from ..interfaces import Authenticator, DocumentCoder
from ..models import Document, Line, ReviewFlag, ReviewReport
from ..parsing import band_key
from .input_validation import UploadLimits, ValidationError, parse_edits, validate_upload

log = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---- view models ----------------------------------------------------------------------------------


@dataclass
class FieldView:
    name: str
    label: str
    text: str
    flags: list[ReviewFlag]
    error: str = ""
    bbox: str = ""             # "x,y,w,h" as fractions, for the image highlight


@dataclass
class LineView:
    index: int
    detail: str
    amount: str
    band: str                  # '' when none / not in the allowed set
    band_source: str           # printed | suggested | user | none
    confirmed: bool
    flags: list[ReviewFlag]
    errors: dict[str, str]
    suggestion_reason: str = ""
    confidence_text: str = ""
    bbox: str = ""
    printed_rate: str = ""

    @property
    def needs_review(self) -> bool:
        return bool(self.flags) or bool(self.errors)


@dataclass
class ReviewView:
    doc_id: str
    status: str
    notice: str
    has_image: bool
    supplier: FieldView
    date: FieldView
    total: FieldView
    lines: list[LineView]
    document_flags: list[ReviewFlag]
    blocking: list[ReviewFlag]
    can_save: bool
    reconciles: bool
    reconcile_text: str
    bands: list[str]
    model_text: str
    not_saved: bool = False

    @property
    def needs_review(self) -> bool:
        return bool(self.blocking) or any(f.flags or f.error for f in (self.supplier, self.date, self.total)) \
            or any(l.needs_review for l in self.lines)


@dataclass
class RowView:
    date: str
    supplier: str
    detail: str
    net: str
    rate: str
    vat: str
    gross: str
    number: str
    highlight: bool


@dataclass
class RowsView:
    rows: list[RowView]
    documents: int


# ---- helpers ----------------------------------------------------------------------------------------


def _money(v: Decimal | None) -> str:
    return "" if v is None else f"{v:.2f}"


def _bbox(b) -> str:
    return "" if b is None else f"{b.x:.4f},{b.y:.4f},{b.w:.4f},{b.h:.4f}"


def build_review_view(doc: Document, report: ReviewReport, bands: Sequence[Decimal], model_info: dict,
                      errors: dict[str, str] | None = None, typed: dict[str, str] | None = None,
                      not_saved: bool = False) -> ReviewView:
    errors, typed = errors or {}, typed or {}
    band_keys = [band_key(b) for b in bands]

    def fview(name: str, label: str, text: str, bbox) -> FieldView:
        return FieldView(name, label, typed.get(name, text), report.for_field(name), errors.get(name, ""), _bbox(bbox))

    date_text = doc.date.value.strftime("%d/%m/%Y") if doc.date.value else ""
    lines = []
    for i, ln in enumerate(doc.lines):
        key = f"line:{i}"
        band = band_key(ln.band) if ln.band is not None and band_key(ln.band) in band_keys else ""
        lines.append(LineView(
            index=i, detail=typed.get(f"{key}:detail", ln.detail),
            amount=typed.get(f"{key}:amount", _money(ln.amount)), band=typed.get(f"{key}:band", band),
            band_source=ln.band_source, confirmed=ln.confirmed, flags=report.for_field(key),
            errors={k.split(":")[2]: v for k, v in errors.items() if k.startswith(key + ":")},
            suggestion_reason=ln.suggestion.reason if ln.suggestion and ln.band_source == "suggested" else "",
            confidence_text=(f"{ln.suggestion.confidence:.0%}" if ln.suggestion and ln.band_source == "suggested" else ""),
            bbox=_bbox(ln.bbox), printed_rate=band_key(ln.printed_rate) if ln.printed_rate is not None else ""))

    if report.reconciles:
        reconcile_text = "Lines add up to the printed total."
    elif doc.total.value is not None and doc.lines and all(l.amount is not None for l in doc.lines):
        reconcile_text = f"Lines do not add up to the printed total (difference {report.difference:+.2f})."
    else:
        reconcile_text = "Lines and total must be filled in to check they add up."

    model_text = (f"Text read by OCR (Tesseract). Band suggestions by a Naive Bayes model v{model_info.get('version', '?')}, "
                  f"trained {str(model_info.get('trained_at', '?'))[:10]} on {model_info.get('examples', '?')} synthetic lines; "
                  f"rate table as of {model_info.get('rate_table_as_of', '?')}.") if model_info else ""
    return ReviewView(
        doc_id=doc.id or "", status=doc.status, notice=doc.notice or "", has_image=bool(doc.image_ref),
        supplier=fview("supplier", "Supplier", doc.supplier.value or "", doc.supplier.bbox),
        date=fview("date", "Date", date_text, doc.date.bbox),
        total=fview("total", "Total (incl. VAT)", _money(doc.total.value), doc.total.bbox),
        lines=lines, document_flags=[f for f in report.flags if f.field == "document"],
        blocking=[f for f in report.flags if f.severity == "blocking"], can_save=report.can_save,
        reconciles=report.reconciles, reconcile_text=reconcile_text, bands=band_keys,
        model_text=model_text, not_saved=not_saved)


def build_rows_view(docs: Sequence[Document], highlight_id: str | None) -> RowsView:
    rows = []
    for d in sorted(docs, key=lambda d: d.number or 0):
        for r in d.rows:
            rows.append(RowView(r.date.strftime("%d/%m/%Y") if r.date else "", r.supplier, r.detail, _money(r.net),
                                f"{band_key(r.rate)}%", _money(r.vat), _money(r.gross), str(r.number or ""),
                                d.id == highlight_id))
    return RowsView(rows, len(docs))


# ---- the blueprint -------------------------------------------------------------------------------------


def build_blueprint(coder: DocumentCoder, auth: Authenticator, bands: Sequence[Decimal],
                    limits: UploadLimits = UploadLimits()) -> Blueprint:
    bp = Blueprint("liner", __name__, template_folder="../presentation_gui/templates",
                   static_folder="../presentation_gui/static", static_url_path="/static")
    band_tuple = tuple(bands)

    def current_user():
        user = auth.authenticate({})
        if user is None:
            abort(401)
        return user

    def render_review(doc, report, errors=None, typed=None, not_saved=False, status=200):
        view = build_review_view(doc, report, band_tuple, coder.model_info(), errors, typed, not_saved)
        return render_template("review.html", v=view), status

    @bp.after_request
    def headers(resp: Response):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @bp.get("/")
    def upload_form():
        return render_template("upload.html", error=None, max_mb=limits.max_bytes // (1024 * 1024))

    @bp.post("/upload")
    def upload():
        user = current_user()
        f = request.files.get("document")
        try:
            up = validate_upload(f.filename if f else None, f.read() if f else None, limits)
        except ValidationError as exc:
            return render_template("upload.html", error=str(exc), max_mb=limits.max_bytes // (1024 * 1024)), 400
        doc = coder.code_document(up, user)
        return redirect(url_for("liner.review", doc_id=doc.id))

    @bp.get("/documents/<doc_id>")
    def review(doc_id: str):
        user = current_user()
        found = coder.get_review(doc_id, user)
        if found is None:
            abort(404)
        doc, report = found
        if doc.status == "confirmed":
            return redirect(url_for("liner.rows", just=doc.id))
        return render_review(doc, report)

    @bp.post("/documents/<doc_id>")
    def review_submit(doc_id: str):
        user = current_user()
        action = request.form.get("action", "check")
        edits, errors, typed = parse_edits(request.form, band_tuple)
        if action == "add_line":
            edits.add_line = True
        try:
            if action == "accept" and not errors:
                doc, report = coder.confirm_document(doc_id, user, edits)
                if doc.status == "confirmed":
                    return redirect(url_for("liner.rows", just=doc.id))
                return render_review(doc, report, errors, typed, not_saved=True)
            doc, report = coder.check_document(doc_id, user, edits)
        except LookupError:
            abort(404)
        except ValueError:
            return redirect(url_for("liner.rows", just=doc_id))
        return render_review(doc, report, errors, typed, not_saved=(action == "accept"))

    @bp.get("/documents/<doc_id>/image")
    def image(doc_id: str):
        data = coder.image_for(doc_id, current_user())
        if data is None:
            abort(404)
        return Response(data, mimetype="image/png", headers={"Cache-Control": "private, max-age=300"})

    @bp.get("/rows")
    def rows():
        user = current_user()
        docs = coder.confirmed_documents(user)
        return render_template("rows.html", v=build_rows_view(docs, request.args.get("just")))

    @bp.get("/export.xlsx")
    def export():
        data = coder.export_xlsx(current_user())
        return Response(data, mimetype=XLSX_MIME,
                        headers={"Content-Disposition": 'attachment; filename="liner-coded-rows.xlsx"'})

    @bp.errorhandler(404)
    def not_found(_):
        return render_template("error.html", title="Not found", message="That page or document does not exist."), 404

    @bp.errorhandler(413)
    def too_big(_):
        return render_template("upload.html", error="The file is too large.",
                               max_mb=limits.max_bytes // (1024 * 1024)), 413

    return bp

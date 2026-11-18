"""Layer 3, Document coding service: coordinates one document from upload to saved rows.

    code_document   upload -> page image -> OCR -> field extraction -> classifier for lines with no
                    printed rate -> saved draft
    check_document  apply the user's edits and re-run the review (nothing is saved as final)
    confirm_document apply edits, run the review, and only if it passes: split into band rows,
                    number the document, save it, and log the corrections

Every collaborator arrives through its interface (see ``liner.interfaces``), so this module knows
nothing about Tesseract, SQLite or Excel. Any failure in reading a document is caught here and turned
into an 'unreadable' draft with nothing pre-filled, so the application keeps working (risk R4)."""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from decimal import Decimal

from ..interfaces import (AuditLog, Classifier, DocumentRenderer, DocumentRepository, ExcelExporter,
                          FieldExtractor, ImageStore, Numbering, OcrEngine, ReviewPolicy, VatCalculator)
from ..models import (UNSET, Correction, Document, Edits, Field, Line, OcrError, ReviewFlag, ReviewReport,
                      Upload, User, snapshot)
from ..parsing import band_key

log = logging.getLogger(__name__)

UNREADABLE_NOTICE = ("This document could not be read automatically. Nothing has been filled in: "
                     "enter the details from the image by hand.")


class DocumentCodingService:
    def __init__(self, *, renderer: DocumentRenderer, ocr: OcrEngine, extractor: FieldExtractor,
                 classifier: Classifier, calculator: VatCalculator, policy: ReviewPolicy,
                 numbering: Numbering, repository: DocumentRepository, images: ImageStore,
                 exporter: ExcelExporter, audit: AuditLog, ocr_min_words: int = 4,
                 ocr_min_mean_conf: float = 35.0):
        self._renderer, self._ocr, self._extractor = renderer, ocr, extractor
        self._classifier, self._calc, self._policy = classifier, calculator, policy
        self._numbering, self._repo, self._images = numbering, repository, images
        self._exporter, self._audit = exporter, audit
        self._min_words, self._min_conf = ocr_min_words, ocr_min_mean_conf

    # ------------------------------------------------------------------ code_document
    def code_document(self, upload: Upload, user: User) -> Document:
        try:
            image = self._renderer.to_image(upload)
        except OcrError as exc:
            log.warning("could not render upload %r: %s", upload.filename, exc)
            return self._unreadable(user, None, str(exc))
        ref = self._images.save(user.id, image, "png")

        try:
            ocr = self._ocr.read_text(image)
        except OcrError as exc:
            log.warning("OCR failed for %s: %s", ref, exc)
            return self._unreadable(user, ref, str(exc))
        except Exception:  # an engine bug must not take the application down
            log.exception("unexpected OCR failure for %s", ref)
            return self._unreadable(user, ref, "The OCR step failed unexpectedly.")

        if len(ocr.words) < self._min_words or ocr.mean_conf < self._min_conf:
            return self._unreadable(user, ref, "Very little text could be read from this image.",
                                    ocr_info=self._ocr_info(ocr))

        try:
            extraction = self._extractor.extract_fields(ocr)
        except Exception:
            log.exception("field extraction failed for %s", ref)
            return self._unreadable(user, ref, "The text could not be turned into fields.",
                                    ocr_info=self._ocr_info(ocr))

        doc = Document(user_id=user.id, status="draft", image_ref=ref, supplier=extraction.supplier,
                       date=extraction.date, total=extraction.total, lines=extraction.lines,
                       printed_vat=extraction.printed_vat, ocr_info=self._ocr_info(ocr))
        for i, ln in enumerate(doc.lines):
            ln.orig_index = i
            if ln.printed_rate is None:
                self._suggest(doc, ln)
        doc.original = snapshot(doc)
        self._repo.save(doc)
        return doc

    # ------------------------------------------------------------------ review / edit / confirm
    def get_review(self, doc_id: str, user: User):
        doc = self._repo.get(doc_id, user.id)
        return None if doc is None else (doc, self._policy.needs_review(doc))

    def check_document(self, doc_id: str, user: User, edits: Edits) -> tuple[Document, ReviewReport]:
        doc = self._editable(doc_id, user)
        self._apply(doc, edits)
        self._repo.save(doc)
        return doc, self._policy.needs_review(doc)

    def confirm_document(self, doc_id: str, user: User, edits: Edits) -> tuple[Document, ReviewReport]:
        existing = self._repo.get(doc_id, user.id)
        if existing is None:
            raise LookupError("document not found")
        if existing.status == "confirmed":      # a double click must not number the document twice
            return existing, self._policy.needs_review(existing)

        doc = existing
        self._apply(doc, edits)
        report = self._policy.needs_review(doc)
        if not report.can_save:
            self._repo.save(doc)                # keep the user's edits, but not as final
            return doc, report

        try:
            rows = self._calc.split_total(doc.lines, doc.printed_vat)
        except ValueError as exc:               # the review should have caught this; refuse, do not crash
            report.flags.append(ReviewFlag("document", f"The rows could not be worked out: {exc}", "blocking"))
            report.can_save = False
            self._repo.save(doc)
            return doc, report

        number = self._numbering.next_number(user)
        doc.rows = [dataclasses.replace(r, date=doc.date.value, supplier=doc.supplier.value, number=number)
                    for r in rows]
        doc.number = number
        doc.status = "confirmed"
        doc.confirmed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._repo.save(doc)
        self._log_corrections(doc)
        return doc, report

    # ------------------------------------------------------------------ lists / export / misc
    def confirmed_documents(self, user: User) -> list[Document]:
        return self._repo.list(user.id, "confirmed")

    def export_xlsx(self, user: User) -> bytes:
        return self._exporter.export(self.confirmed_documents(user))

    def image_for(self, doc_id: str, user: User) -> bytes | None:
        doc = self._repo.get(doc_id, user.id)
        if doc is None or not doc.image_ref:
            return None
        try:
            return self._images.load(doc.image_ref)
        except (OSError, ValueError):
            return None

    def model_info(self) -> dict:
        return self._classifier.info()

    # ------------------------------------------------------------------ internals
    def _unreadable(self, user: User, ref: str | None, why: str, ocr_info: dict | None = None) -> Document:
        doc = Document(user_id=user.id, status="unreadable", image_ref=ref, notice=f"{UNREADABLE_NOTICE} ({why})",
                       ocr_info=ocr_info or {})
        doc.original = snapshot(doc)
        self._repo.save(doc)
        return doc

    @staticmethod
    def _ocr_info(ocr) -> dict:
        return {"engine": ocr.engine, "engine_version": ocr.engine_version,
                "words": len(ocr.words), "mean_conf": round(ocr.mean_conf, 1)}

    def _editable(self, doc_id: str, user: User) -> Document:
        doc = self._repo.get(doc_id, user.id)
        if doc is None:
            raise LookupError("document not found")
        if doc.status == "confirmed":
            raise ValueError("this document is already confirmed")
        return doc

    def _suggest(self, doc: Document, ln: Line) -> None:
        try:
            pred = self._classifier.predict(doc.supplier.value or "", ln.detail)
        except Exception:
            log.exception("classifier failed; leaving the band for the user to choose")
            return
        ln.suggestion, ln.band, ln.band_source, ln.confirmed = pred, pred.band, "suggested", False

    def _apply(self, doc: Document, edits: Edits) -> None:
        for name in ("supplier", "date", "total"):
            new = getattr(edits, name)
            if new is UNSET:
                continue
            if isinstance(new, str):
                new = new.strip() or None
            current: Field = getattr(doc, name)
            if new is None:
                setattr(doc, name, Field())
            elif new != current.value:
                setattr(doc, name, Field(new, None, current.bbox, "user"))

        removed: set[int] = set()
        for le in edits.lines:
            if not 0 <= le.index < len(doc.lines):
                continue
            ln = doc.lines[le.index]
            if le.remove:
                removed.add(le.index)
                continue
            prev_band, prev_source = ln.band, ln.band_source
            resuggested = False
            if le.detail is not UNSET and le.detail.strip() != ln.detail:
                ln.detail = le.detail.strip()
                if ln.printed_rate is None and ln.band_source in ("none", "suggested"):
                    self._suggest(doc, ln)      # a changed description gets a fresh suggestion
                    resuggested = ln.band_source == "suggested"
            if le.amount is not UNSET and le.amount != ln.amount:
                ln.amount, ln.confidence = le.amount, None
            if le.band is not UNSET:
                same_as_before = (prev_band is not None and le.band is not None
                                  and band_key(le.band) == band_key(prev_band))
                if le.band is None:
                    ln.band, ln.band_source, ln.confirmed = None, "none", False
                elif same_as_before and prev_source == "suggested":
                    if not resuggested:         # a fresh suggestion needs its own tick
                        ln.confirmed = le.confirmed
                elif same_as_before and prev_source in ("printed", "user"):
                    pass                        # the same band that was already there
                else:                           # the user chose a band: theirs overrides any suggestion
                    ln.band, ln.band_source, ln.confirmed = le.band, "user", True
            elif ln.band_source == "suggested" and not resuggested:
                ln.confirmed = le.confirmed
        if removed:
            doc.lines = [ln for i, ln in enumerate(doc.lines) if i not in removed]
        if edits.add_line:
            doc.lines.append(Line(origin="manual"))

    def _log_corrections(self, doc: Document) -> None:
        orig = doc.original or {}
        out: list[Correction] = []

        def text(v) -> str:
            if isinstance(v, dict):
                return str(next(iter(v.values())))
            return "" if v is None else str(v)

        for name in ("supplier", "date", "total"):
            before, after = text(orig.get(name)), text(getattr(doc, name).value)
            if before != after:
                out.append(Correction(name, before, after, "corrected"))

        orig_lines = orig.get("lines", [])
        seen = set()
        for ln in doc.lines:
            if ln.orig_index is None or ln.orig_index >= len(orig_lines):
                out.append(Correction("line", "", f"{ln.detail} {ln.amount}", "added"))
                continue
            seen.add(ln.orig_index)
            o = orig_lines[ln.orig_index]
            if text(o["detail"]) != ln.detail:
                out.append(Correction("line.detail", text(o["detail"]), ln.detail, "corrected"))
            if text(o["amount"]) != text(ln.amount):
                out.append(Correction("line.amount", text(o["amount"]), text(ln.amount), "corrected"))
            ob, nb = text(o["band"]), text(ln.band)
            if o["band_source"] == "suggested":
                kind = "suggestion_accepted" if ob == nb else "suggestion_changed"
                out.append(Correction("line.band", ob, nb, kind))
            elif ob != nb:
                out.append(Correction("line.band", ob, nb, "corrected"))
        for i, o in enumerate(orig_lines):
            if i not in seen:
                out.append(Correction("line", f"{text(o['detail'])} {text(o['amount'])}", "", "removed"))

        self._audit.record_corrections(doc.id, doc.user_id, out, fields_shown=3 + 3 * len(orig_lines))

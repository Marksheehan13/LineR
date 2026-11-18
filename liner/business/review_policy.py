"""Layer 3, Review and reconcile policy: decides what the user must look at before anything is saved.

This carries the mitigations demonstrated in Deliverable 3:
  R1  doubtful fields are flagged; saving is refused until the lines add up to the printed total
  R4  nothing is pre-filled when a document could not be read (handled by the coding service)
  R5  a band outside the allowed set is rejected
  R11 lines must add up to the printed total; the difference and the lines to check are shown

Flags are 'blocking' (the document cannot be saved) or 'warning' (shown, but can be saved)."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from ..config import ALLOWED_BANDS
from ..interfaces import VatCalculator
from ..models import Document, ReviewFlag, ReviewReport
from ..parsing import band_key, quantize


class ConfidenceReviewPolicy:
    def __init__(self, calculator: VatCalculator, bands: Sequence[Decimal] = ALLOWED_BANDS,
                 doubtful_field_conf: float = 0.80, low_suggestion_conf: float = 0.70,
                 printed_vat_tolerance: Decimal = Decimal("0.02")):
        self._calc = calculator
        self._bands = {band_key(b) for b in bands}
        self._doubtful = doubtful_field_conf
        self._low_suggestion = low_suggestion_conf
        self._tolerance = printed_vat_tolerance

    def needs_review(self, document: Document) -> ReviewReport:
        flags: list[ReviewFlag] = []

        # ---- header fields ------------------------------------------------------------------
        for name, label in (("supplier", "supplier"), ("date", "date"), ("total", "total")):
            f = getattr(document, name)
            if f.value is None:
                flags.append(ReviewFlag(name, f"The {label} was not found. Type it in from the image.",
                                        "blocking", "missing"))
            elif f.source == "ocr" and f.confidence is not None and f.confidence < self._doubtful:
                flags.append(ReviewFlag(name, f"The {label} may be misread (OCR confidence "
                                              f"{f.confidence:.0%}). Check it against the image.",
                                        "warning", "doubtful"))

        if not document.lines:
            flags.append(ReviewFlag("document", "No lines were found. Add each line from the image.",
                                    "blocking", "missing"))

        # ---- lines --------------------------------------------------------------------------
        for i, ln in enumerate(document.lines):
            key = f"line:{i}"
            label = f"Line {i + 1}"
            if ln.amount is None:
                flags.append(ReviewFlag(key, f"{label} has no amount.", "blocking", "missing"))
            elif ln.origin == "ocr" and ln.band_source != "user" and ln.confidence is not None \
                    and ln.confidence < self._doubtful:
                flags.append(ReviewFlag(key, f"{label} may be misread (OCR confidence {ln.confidence:.0%}).",
                                        "warning", "doubtful"))
            if not ln.detail.strip():
                flags.append(ReviewFlag(key, f"{label} has no description.", "warning", "missing"))

            if ln.printed_rate is not None and band_key(ln.printed_rate) not in self._bands \
                    and ln.band_source != "user":
                flags.append(ReviewFlag(
                    key, f"{label}: the printed rate {band_key(ln.printed_rate)}% is not an Irish band "
                         f"(23, 13.5, 9, 0). It may be misread; choose the right band.",
                    "blocking", "rate"))
            elif ln.band is None:
                flags.append(ReviewFlag(key, f"{label} has no band. Choose one.", "blocking", "rate"))
            elif band_key(ln.band) not in self._bands:
                flags.append(ReviewFlag(key, f"{label}: {band_key(ln.band)}% is not an allowed band.",
                                        "blocking", "rate"))
            elif ln.band_source == "suggested":
                if not ln.confirmed:
                    flags.append(ReviewFlag(key, f"{label}: no rate is printed. Suggested band "
                                                 f"{band_key(ln.band)}%. Tick it to confirm or choose another band.",
                                            "blocking", "suggested"))
                if ln.suggestion and ln.suggestion.confidence < self._low_suggestion:
                    flags.append(ReviewFlag(key, f"{label}: the suggestion is low confidence "
                                                 f"({ln.suggestion.confidence:.0%}).", "warning", "low_confidence"))
            elif ln.printed_rate is not None and ln.band_source == "user" \
                    and band_key(ln.band) != band_key(ln.printed_rate):
                flags.append(ReviewFlag(key, f"{label}: you coded {band_key(ln.band)}% but the document "
                                             f"prints {band_key(ln.printed_rate)}%.", "warning", "rate"))

        # ---- reconcile: lines must add up to the printed total ---------------------------------
        reconciles, difference, suspects = self._reconcile(document)
        if document.total.value is not None and document.lines and any(l.amount is not None for l in document.lines):
            if not reconciles:
                shown = ", ".join(str(i + 1) for i in suspects)
                flags.append(ReviewFlag(
                    "total", f"The lines add up to {self._sum(document):.2f} but the printed total is "
                             f"{document.total.value:.2f} (difference {difference:+.2f}). "
                             f"Check lines {shown} and the total against the image.",
                    "blocking", "reconcile"))

        # ---- printed VAT versus our own calculation ----------------------------------------------
        flags.extend(self._check_printed_vat(document))

        can_save = not any(f.severity == "blocking" for f in flags)
        return ReviewReport(flags=flags, reconciles=reconciles, difference=difference,
                            suspect_lines=suspects, can_save=can_save)

    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _sum(document: Document) -> Decimal:
        return quantize(sum((l.amount for l in document.lines if l.amount is not None), Decimal(0)))

    def _reconcile(self, document: Document):
        if document.total.value is None or not document.lines \
                or any(l.amount is None for l in document.lines):
            return False, Decimal("0.00"), []
        diff = quantize(document.total.value - self._sum(document))
        if diff == 0:
            return True, Decimal("0.00"), []
        # lines to check first: the least certain reads, then any line equal to the difference
        order = sorted(range(len(document.lines)),
                       key=lambda i: (document.lines[i].confidence if document.lines[i].confidence is not None else 1.0))
        suspects = order[:2] if len(order) > 2 else order
        return False, diff, sorted(suspects)

    def _check_printed_vat(self, document: Document) -> list[ReviewFlag]:
        if not document.printed_vat or not document.lines \
                or any(l.amount is None or l.band is None or band_key(l.band) not in self._bands
                       for l in document.lines):
            return []
        flags = []
        by_band: dict[str, Decimal] = {}
        for ln in document.lines:
            by_band[band_key(ln.band)] = by_band.get(band_key(ln.band), Decimal(0)) + ln.amount
        for key, printed in document.printed_vat.items():
            if key not in by_band:
                flags.append(ReviewFlag("document", f"The document prints VAT at {key}% but no line is coded "
                                                    f"to {key}%.", "warning", "vat"))
                continue
            calc = self._calc.vat_in_gross(quantize(by_band[key]), Decimal(key))
            if abs(printed - calc) > self._tolerance:
                flags.append(ReviewFlag(
                    "document", f"Printed VAT at {key}% is {printed:.2f} but the lines coded to {key}% give "
                                f"{calc:.2f}. The calculated figure is used.", "warning", "vat"))
        return flags

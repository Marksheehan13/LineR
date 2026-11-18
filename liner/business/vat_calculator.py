"""Layer 3, VAT calculator: groups lines by band and works out net, VAT and gross per band.

Plain arithmetic, no AI. Each line amount is taken to include VAT, so for a band:
    gross = sum of its line amounts
    VAT   = gross x rate / (100 + rate), rounded to the cent
    net   = gross - VAT
Because net is gross minus VAT, net + VAT equals gross exactly on every row, and the rows add up to
the sum of the lines (which the review step has already matched to the printed total)."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from ..config import ALLOWED_BANDS
from ..models import BandRow, Line
from ..parsing import band_key, quantize


class IrishVatCalculator:
    def __init__(self, bands: Sequence[Decimal] = ALLOWED_BANDS, printed_vat_tolerance: Decimal = Decimal("0.02")):
        self._bands = {band_key(b): b for b in bands}
        self._tolerance = printed_vat_tolerance

    def vat_in_gross(self, gross: Decimal, rate: Decimal) -> Decimal:
        return quantize(gross * rate / (Decimal(100) + rate))

    def split_total(self, lines: Sequence[Line], printed_vat: dict[str, Decimal] | None = None) -> list[BandRow]:
        printed_vat = printed_vat or {}
        groups: dict[str, list[Line]] = {}
        for ln in lines:
            if ln.amount is None:
                raise ValueError("a line has no amount")
            if ln.band is None or band_key(ln.band) not in self._bands:
                raise ValueError(f"band {ln.band!r} is not allowed")
            groups.setdefault(band_key(ln.band), []).append(ln)

        rows: list[BandRow] = []
        for key, members in groups.items():   # dicts keep first-appearance order
            rate = self._bands[key]
            gross = quantize(sum((m.amount for m in members), Decimal(0)))
            calculated = self.vat_in_gross(gross, rate)
            vat, source = calculated, "calculated"
            printed = printed_vat.get(key)
            if printed is not None and abs(printed - calculated) <= self._tolerance:
                vat, source = printed, "printed"      # the document's own figure, within rounding
            detail = "; ".join(m.detail.strip() for m in members if m.detail.strip())
            rows.append(BandRow(date=None, supplier="", detail=detail, net=gross - vat, rate=rate,
                                vat=vat, gross=gross, number=None, vat_source=source))
        return rows

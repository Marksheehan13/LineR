import random
from decimal import Decimal as D

import pytest

from liner.business.vat_calculator import IrishVatCalculator
from liner.models import Line

calc = IrishVatCalculator()


def line(detail, amount, band):
    return Line(detail=detail, amount=D(str(amount)), band=D(str(band)), band_source="user")


@pytest.mark.parametrize("band,gross,vat", [("23", "123.00", "23.00"), ("13.5", "113.50", "13.50"),
                                            ("9", "109.00", "9.00"), ("0", "50.00", "0.00")])
def test_all_four_bands(band, gross, vat):
    (row,) = calc.split_total([line("x", gross, band)])
    assert row.vat == D(vat) and row.gross == D(gross) and row.net == D(gross) - D(vat) and row.rate == D(band)


def test_grouping_one_row_per_band_in_first_seen_order():
    rows = calc.split_total([line("Diesel", "10.00", 0), line("Paper", "12.30", 23), line("Petrol", "5.00", 0)])
    assert [r.rate for r in rows] == [D("0"), D("23")]
    assert rows[0].gross == D("15.00") and rows[0].detail == "Diesel; Petrol"


def test_receipt_with_fuel_and_food_splits_in_two():
    rows = calc.split_total([line("Diesel", "10.00", 0), line("Newspaper", "10.00", 9)])
    assert len(rows) == 2 and sum(r.gross for r in rows) == D("20.00")
    assert rows[1].vat == D("0.83") and rows[1].net == D("9.17")


def test_cent_rounding_never_loses_a_cent():
    rng = random.Random(5)
    for _ in range(300):
        lines = [line("l", D(rng.randint(1, 99999)) / 100, rng.choice([23, 13.5, 9, 0])) for _ in range(rng.randint(1, 8))]
        rows = calc.split_total(lines)
        assert sum(r.gross for r in rows) == sum(l.amount for l in lines)          # rows sum to the lines
        assert all(r.net + r.vat == r.gross for r in rows)                          # net + VAT = gross
        assert all(r.vat == r.vat.quantize(D("0.01")) for r in rows)


def test_zero_and_negative_amounts():
    (row,) = calc.split_total([line("free sample", "0.00", 23)])
    assert row.gross == row.vat == row.net == D("0.00")
    (credit,) = calc.split_total([line("refund", "-12.30", 23)])
    assert credit.vat == D("-2.30") and credit.net == D("-10.00")


def test_printed_vat_used_when_within_a_cent_or_two_else_calculated():
    lines = [line("a", "12.30", 23)]
    assert calc.split_total(lines, {"23": D("2.31")})[0].vat_source == "printed"
    assert calc.split_total(lines, {"23": D("2.31")})[0].vat == D("2.31")
    far = calc.split_total(lines, {"23": D("5.00")})[0]
    assert far.vat == D("2.30") and far.vat_source == "calculated"


def test_band_outside_the_allowed_set_is_refused():
    with pytest.raises(ValueError):
        calc.split_total([line("x", "10.00", 21)])
    with pytest.raises(ValueError):
        calc.split_total([Line(detail="x", amount=D("1.00"), band=None)])
    with pytest.raises(ValueError):
        calc.split_total([Line(detail="x", amount=None, band=D("23"))])

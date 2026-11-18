from datetime import date
from decimal import Decimal as D

import pytest

from liner.parsing import AMOUNT_RE, band_key, parse_amount, parse_date, parse_rate


@pytest.mark.parametrize("text,expected", [
    ("12.30", D("12.30")), ("€1,234.56", D("1234.56")), ("12,30", D("12.30")), ("-5.00", D("-5.00")),
    ("1.234,56", D("1234.56")), ("20", D("20.00")), (" 7.5 ", D("7.50")), ("- 5.00", D("-5.00")),
])
def test_parse_amount_valid(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["", None, "abc", "12.345", "1.2.3", "--5", "12,3456", "€"])
def test_parse_amount_rejects_junk(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize("text,expected", [
    ("03/11/2026", date(2026, 11, 3)), ("3-11-26", date(2026, 11, 3)), ("03.11.2026", date(2026, 11, 3)),
    ("3 Nov 2026", date(2026, 11, 3)), ("3rd November 2026", date(2026, 11, 3)),
    ("Date: 24 April 2026", date(2026, 4, 24)), ("2026-11-03", date(2026, 11, 3)),
])
def test_parse_date_is_day_first(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["31/02/2026", "13/13/2026", "hello", "", None, "03/11/1850", "1/2"])
def test_parse_date_rejects_impossible(text):
    assert parse_date(text) is None


def test_parse_rate_and_band_key():
    assert parse_rate("13,5 %") == D("13.5") and parse_rate("23") == D("23") and parse_rate("x") is None
    assert band_key(D("13.50")) == "13.5" and band_key(D("23")) == "23" and band_key(D("0.0")) == "0"


def test_amount_regex_does_not_read_dates_or_phone_numbers_as_money():
    assert not AMOUNT_RE.findall("Date 03.11.2026")
    assert [m.group() for m in AMOUNT_RE.finditer("3 x book - 82.44 0%")] == ["82.44"]
    assert [m.group() for m in AMOUNT_RE.finditer("Discount -2.00")] == ["-2.00"]

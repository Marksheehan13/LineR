from datetime import date
from decimal import Decimal as D

import pytest

from liner.business.review_policy import ConfidenceReviewPolicy
from liner.business.vat_calculator import IrishVatCalculator
from liner.models import Document, Field, Line, Prediction

policy = ConfidenceReviewPolicy(IrishVatCalculator())


def ocr_field(value, conf=0.95):
    return Field(value, conf, None, "ocr")


def good_doc(**over) -> Document:
    d = Document(user_id="demo", supplier=ocr_field("Acme"), date=ocr_field(date(2026, 11, 3)),
                 total=ocr_field(D("22.30")),
                 lines=[Line("Paper", D("12.30"), D("23"), D("23"), "printed", False, None, 0.95),
                        Line("Diesel", D("10.00"), D("0"), D("0"), "printed", False, None, 0.95)])
    for k, v in over.items():
        setattr(d, k, v)
    return d


def kinds(report, severity=None):
    return {(f.field, f.kind) for f in report.flags if severity is None or f.severity == severity}


def test_clean_document_can_be_saved():
    r = policy.needs_review(good_doc())
    assert r.can_save and r.reconciles and r.flags == [] and r.difference == D("0.00")


@pytest.mark.parametrize("name", ["supplier", "date", "total"])
def test_a_missing_header_field_blocks_saving(name):
    r = policy.needs_review(good_doc(**{name: Field()}))
    assert not r.can_save and (name, "missing") in kinds(r, "blocking")


def test_doubtful_ocr_reads_are_flagged_but_do_not_block():
    r = policy.needs_review(good_doc(supplier=ocr_field("Acme", 0.5)))
    assert r.can_save and ("supplier", "doubtful") in kinds(r, "warning")


def test_lines_must_add_up_to_the_printed_total():
    d = good_doc(total=ocr_field(D("25.30")))
    r = policy.needs_review(d)
    assert not r.can_save and not r.reconciles and r.difference == D("3.00")
    assert ("total", "reconcile") in kinds(r, "blocking") and r.suspect_lines
    assert "3.00" in next(f.message for f in r.flags if f.kind == "reconcile")


def test_a_forged_total_line_cannot_get_a_wrong_figure_saved():     # risk R10: reconcile decides
    r = policy.needs_review(good_doc(total=ocr_field(D("0.00"))))
    assert not r.can_save


def test_suspect_lines_are_the_least_certain_reads():
    d = good_doc(total=ocr_field(D("99.00")))
    d.lines.append(Line("Pens", D("3.00"), D("23"), D("23"), "printed", False, None, 0.30))
    d.lines.append(Line("Ink", D("4.00"), D("23"), D("23"), "printed", False, None, 0.99))
    assert 2 in policy.needs_review(d).suspect_lines


def test_suggested_band_must_be_confirmed_line_by_line():
    sug = Prediction(D("0"), 0.95, "Words like diesel")
    ln = Line("Diesel", D("10.00"), None, D("0"), "suggested", False, sug, 0.95)
    d = good_doc(lines=[ln], total=ocr_field(D("10.00")))
    r = policy.needs_review(d)
    assert not r.can_save and ("line:0", "suggested") in kinds(r, "blocking")
    ln.confirmed = True
    assert policy.needs_review(d).can_save


def test_low_confidence_suggestion_is_a_warning():
    sug = Prediction(D("23"), 0.45, "guess")
    ln = Line("Thing", D("10.00"), None, D("23"), "suggested", True, sug, 0.95)
    r = policy.needs_review(good_doc(lines=[ln], total=ocr_field(D("10.00"))))
    assert r.can_save and ("line:0", "low_confidence") in kinds(r, "warning")


def test_a_band_outside_the_allowed_set_is_rejected():          # risk R5
    ln = Line("Paper", D("10.00"), D("28"), D("28"), "printed", False, None, 0.95)
    r = policy.needs_review(good_doc(lines=[ln], total=ocr_field(D("10.00"))))
    assert not r.can_save and ("line:0", "rate") in kinds(r, "blocking")
    ln.band, ln.band_source = D("23"), "user"                    # the user picks a valid band
    assert policy.needs_review(good_doc(lines=[ln], total=ocr_field(D("10.00")))).can_save


def test_no_lines_blocks():
    r = policy.needs_review(good_doc(lines=[], total=ocr_field(D("10.00"))))
    assert not r.can_save and ("document", "missing") in kinds(r, "blocking")


def test_missing_amount_blocks():
    r = policy.needs_review(good_doc(lines=[Line("Paper", None, D("23"), D("23"), "printed")]))
    assert not r.can_save and ("line:0", "missing") in kinds(r, "blocking")


def test_printed_vat_that_disagrees_with_the_calculation_is_a_warning():
    d = good_doc(printed_vat={"23": D("9.99")})
    r = policy.needs_review(d)
    assert r.can_save and ("document", "vat") in kinds(r, "warning")
    assert not policy.needs_review(good_doc(printed_vat={"23": D("2.30")})).flags


def test_user_override_of_a_printed_rate_is_flagged_as_a_warning():
    ln = Line("Paper", D("10.00"), D("23"), D("0"), "user", True, None, None)
    r = policy.needs_review(good_doc(lines=[ln], total=ocr_field(D("10.00"))))
    assert r.can_save and ("line:0", "rate") in kinds(r, "warning")

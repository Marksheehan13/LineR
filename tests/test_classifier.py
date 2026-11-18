from decimal import Decimal as D

import pytest

from liner.business.classifier import MODEL_NAME, NaiveBayesClassifier, load_or_train
from liner.config import ALLOWED_BANDS
from liner.data_access.model_store import LocalModelStore
from tools.synthetic_lines import generate_lines


@pytest.fixture(scope="module")
def clf():
    return NaiveBayesClassifier(generate_lines(1500, seed=13))


@pytest.mark.parametrize("supplier,detail", [
    ("", ""), ("", "   "), ("Corrib Fuels", "diesel"), ("", "xyzzy qwerty"), ("", "x" * 10_000),
    ("", "ÉCLAIR café – 日本語"), ("", "12.30 23% 9%"), ("A" * 500, "paper"), (None, None),
])
def test_always_an_allowed_band_and_a_confidence_between_0_and_1(clf, supplier, detail):
    p = clf.predict(supplier, detail)
    assert p.band in ALLOWED_BANDS and 0.0 <= p.confidence <= 1.0 and p.reason


def test_learns_obvious_items(clf):
    assert clf.predict("Corrib Fuels", "unleaded petrol").band == D("0")
    assert clf.predict("", "A4 copy paper").band == D("23")
    assert clf.predict("", "electricity charges").band == D("13.5")
    assert clf.predict("", "newspaper").band == D("9")


def test_unseen_words_get_low_confidence_and_say_so(clf):
    p = clf.predict("", "zzzz qqqq")
    assert p.confidence <= 0.4 and "No words" in p.reason


def test_reason_names_the_words_not_an_authority(clf):
    p = clf.predict("", "diesel")
    assert '"diesel"' in p.reason and "suggestion" in p.reason.lower()


def test_same_training_data_gives_same_predictions():
    ex = generate_lines(400, seed=3)
    a, b = NaiveBayesClassifier(ex), NaiveBayesClassifier(ex)
    for detail in ["diesel", "paper", "ticket", "mystery item"]:
        assert a.predict("", detail).confidence == b.predict("", detail).confidence


def test_payload_round_trip_keeps_predictions(clf):
    again = NaiveBayesClassifier.from_payload(clf.to_payload(), version=2)
    for detail in ["diesel", "paper", "cinema ticket", "unknown thing"]:
        assert again.predict("", detail).band == clf.predict("", detail).band
    assert again.info()["version"] == 2 and again.info()["examples"] == 1500


def test_load_or_train_trains_once_then_reuses(tmp_path):
    store = LocalModelStore(tmp_path)
    calls = []
    first = load_or_train(store, lambda: calls.append(1) or generate_lines(300, 1))
    second = load_or_train(store, lambda: calls.append(1) or generate_lines(300, 1))
    assert len(calls) == 1 and first.version == second.version == 1
    assert store.load_latest(MODEL_NAME)[0] == 1


def test_training_without_examples_is_an_error():
    with pytest.raises(ValueError):
        NaiveBayesClassifier([])


def test_examples_with_unknown_bands_are_ignored():
    ex = generate_lines(100, 1) + [("", "weird", D("21"))]
    assert NaiveBayesClassifier(ex).info()["examples"] == 100

"""Layer 3, Classifier (the second AI component): suggests a VAT band for a line that prints none.

A Naive Bayes text classifier from NLTK. NLTK's stemmer and tokeniser prepare the text (both on this
module's syllabus and neither needs a data download). Class probabilities are the confidence score.
The model is saved as its training lines (JSON), not as a pickle: loading a pickle can run code, and
retraining ~2,000 short lines takes well under a second (deviation log D-05).

It is a suggestion only. Every suggested band must be confirmed by the user, line by line."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable, Sequence

import nltk
from nltk.stem import PorterStemmer
from nltk.tokenize import RegexpTokenizer

from ..config import ALLOWED_BANDS, RATE_TABLE_AS_OF
from ..interfaces import ModelStore
from ..models import Prediction
from ..parsing import band_key

MODEL_NAME = "band-classifier"
_TOKENISER = RegexpTokenizer(r"[a-z]+")
_STEM = PorterStemmer().stem
_SUPPLIER_STOP = {"ltd", "limited", "co", "the", "and", "of", "inc", "plc", "t", "a"}
_MAX_TEXT = 300
_NO_EVIDENCE_CAP = 0.4     # confidence is capped when none of the words were seen in training

Example = tuple[str, str, Decimal]   # supplier, detail, band


def _raw_tokens(text: str) -> list[str]:
    return [t for t in _TOKENISER.tokenize(text[:_MAX_TEXT].lower()) if len(t) >= 2]


def _tokens(text: str) -> list[str]:
    return [_STEM(t) for t in _raw_tokens(text)]


def featurise(supplier: str, detail: str) -> dict[str, bool]:
    feats = {f"w:{t}": True for t in _tokens(detail)}
    feats.update({f"s:{t}": True for t in _tokens(supplier) if t not in _SUPPLIER_STOP})
    return feats


class NaiveBayesClassifier:
    def __init__(self, examples: Sequence[Example], bands: Sequence[Decimal] = ALLOWED_BANDS,
                 seed: int = 0, trained_at: str | None = None, version: int = 0):
        self._bands = {band_key(b): b for b in bands}
        self._examples = [(s, d, b) for s, d, b in examples if band_key(b) in self._bands]
        if not self._examples:
            raise ValueError("no usable training examples")
        self.seed = seed
        self.version = version
        self.trained_at = trained_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        train = [(featurise(s, d), band_key(b)) for s, d, b in self._examples]
        self._model = nltk.NaiveBayesClassifier.train(train)
        self._seen_features = {f for feats, _ in train for f in feats}
        # document frequency of each word per band, used only to explain a prediction
        self._word_bands: dict[str, Counter] = defaultdict(Counter)
        for s, d, b in self._examples:
            for t in set(_tokens(d)):
                self._word_bands[t][band_key(b)] += 1

    # -- the interface -----------------------------------------------------------------------
    def predict(self, supplier: str, detail: str) -> Prediction:
        feats = featurise(supplier or "", detail or "")
        dist = self._model.prob_classify(feats)
        key = max(dist.samples(), key=dist.prob)
        confidence = float(dist.prob(key))
        known = [(raw, _STEM(raw)) for raw in _raw_tokens(detail or "") if _STEM(raw) in self._word_bands]
        if not any(f in self._seen_features for f in feats):
            confidence = min(confidence, _NO_EVIDENCE_CAP)
        confidence = min(1.0, max(0.0, confidence))
        return Prediction(self._bands[key], confidence, self._reason(key, known))

    def info(self) -> dict:
        return {"version": self.version, "trained_at": self.trained_at, "examples": len(self._examples),
                "seed": self.seed, "rate_table_as_of": RATE_TABLE_AS_OF}

    # -- persistence -------------------------------------------------------------------------
    def to_payload(self) -> dict:
        return {"trained_at": self.trained_at, "seed": self.seed, "rate_table_as_of": RATE_TABLE_AS_OF,
                "bands": [band_key(b) for b in self._bands.values()],
                "examples": [[s, d, band_key(b)] for s, d, b in self._examples]}

    @classmethod
    def from_payload(cls, payload: dict, version: int = 0,
                     bands: Sequence[Decimal] = ALLOWED_BANDS) -> "NaiveBayesClassifier":
        examples = [(s, d, Decimal(b)) for s, d, b in payload["examples"]]
        return cls(examples, bands=bands, seed=payload.get("seed", 0),
                   trained_at=payload.get("trained_at"), version=version)

    # -- internals ---------------------------------------------------------------------------
    def _reason(self, key: str, known: list[tuple[str, str]]) -> str:
        rate = f"{key}%"
        if not known:
            return f"No words in this description were seen in training; {rate} is the most common band. Check it."
        scored = []
        for raw, stem in dict(known).items():       # shown as the user typed it, scored by its stem
            counts = self._word_bands[stem]
            total = sum(counts.values())
            scored.append((counts[key] / total, counts[key], raw))
        scored.sort(reverse=True)
        words = ", ".join(f'"{t}"' for _, _, t in scored[:2])
        return f"Words like {words} were most often coded {rate} in the training lines. This is a suggestion, not tax advice."


def load_or_train(store: ModelStore, make_examples: Callable[[], Iterable[Example]], seed: int = 0,
                  bands: Sequence[Decimal] = ALLOWED_BANDS) -> NaiveBayesClassifier:
    """Load the latest saved model; if there is none, train one from ``make_examples()`` and save it."""
    latest = store.load_latest(MODEL_NAME)
    if latest is not None:
        version, payload = latest
        return NaiveBayesClassifier.from_payload(payload, version=version, bands=bands)
    clf = NaiveBayesClassifier(list(make_examples()), bands=bands, seed=seed)
    clf.version = store.save(MODEL_NAME, clf.to_payload())
    return clf

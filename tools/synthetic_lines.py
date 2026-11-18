"""Synthetic invoice/receipt lines with known bands, for training and testing the classifier.

Deterministic for a given seed. See tools/vocabulary.py for the (illustrative) labels."""
from __future__ import annotations

import random
from decimal import Decimal

from .vocabulary import ITEMS, SUPPLIERS, TYPE_SUPPLIERS

_QTY = ["", "", "", "1 x ", "2 x ", "3 x ", "x2 ", "4 "]
_SUFFIX = ["", "", "", "", " (large)", " pack", " each", " - promo", " inc delivery"]
_ABBREV = {"litres": "ltr", "monthly": "mthly", "service": "svc", "delivery": "delv", "charges": "chg",
           "premium": "prem", "annual": "ann", "cartridge": "cart", "repair": "rep"}


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 5:
        return word
    i = rng.randrange(1, len(word) - 1)
    kind = rng.choice(["drop", "swap", "dup"])
    if kind == "drop":
        return word[:i] + word[i + 1:]
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    return word[:i] + word[i] + word[i:]


def vary(phrase: str, rng: random.Random, noise: float = 0.1) -> str:
    """Small realistic variations: quantities, abbreviations, typos, capitals."""
    words = phrase.split()
    out = []
    for w in words:
        if w in _ABBREV and rng.random() < 0.3:
            w = _ABBREV[w]
        elif rng.random() < noise:
            w = _typo(w, rng)
        out.append(w)
    text = rng.choice(_QTY) + " ".join(out) + rng.choice(_SUFFIX)
    style = rng.random()
    if style < 0.25:
        text = text.upper()
    elif style < 0.40:
        text = text.title()
    return text.strip()


def random_supplier(item_type: str, rng: random.Random, p_matching: float = 0.8) -> str:
    groups = TYPE_SUPPLIERS[item_type] if rng.random() < p_matching else list(SUPPLIERS)
    return rng.choice(SUPPLIERS[rng.choice(groups)])


def generate_lines(n: int, seed: int, noise: float = 0.1) -> list[tuple[str, str, Decimal]]:
    """Returns (supplier, detail, band) triples, spread evenly over bands and item types."""
    rng = random.Random(seed)
    pool = [(band, itype, phrase) for band, types in ITEMS.items()
            for itype, phrases in types.items() for phrase in phrases]
    rng.shuffle(pool)   # so even a small n covers every band
    out = []
    for i in range(n):
        band, itype, phrase = pool[i % len(pool)] if i < len(pool) else rng.choice(pool)
        out.append((random_supplier(itype, rng), vary(phrase, rng, noise), Decimal(band)))
    rng.shuffle(out)
    return out

"""Train, evaluate and (optionally) save the band classifier.

    python -m tools.train_classifier                 # report held-out accuracy and a confusion matrix
    python -m tools.train_classifier --save          # also save a new model version for the app

The held-out lines are never used for training. They are synthetic, written by me from the same item
lists as the training lines, so the accuracy shown flatters real-world performance."""
from __future__ import annotations

import argparse
from collections import Counter

from liner.business.classifier import MODEL_NAME, NaiveBayesClassifier
from liner.config import Config
from liner.data_access.model_store import LocalModelStore
from liner.parsing import band_key

from .synthetic_lines import generate_lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--save", action="store_true", help="save the model trained on all lines as a new version")
    args = ap.parse_args()

    lines = generate_lines(args.n, args.seed)
    cut = int(len(lines) * 0.8)
    train, test = lines[:cut], lines[cut:]
    model = NaiveBayesClassifier(train, seed=args.seed)
    confusion: Counter = Counter()
    for supplier, detail, band in test:
        confusion[(band_key(band), band_key(model.predict(supplier, detail).band))] += 1
    right = sum(v for (a, b), v in confusion.items() if a == b)
    print(f"held-out accuracy: {right}/{len(test)} = {right / len(test):.1%}  (trained on {len(train)} synthetic lines)")
    keys = ["23", "13.5", "9", "0"]
    print("rows = true band, columns = predicted band")
    print("        " + "".join(f"{k:>7}" for k in keys))
    for a in keys:
        print(f"{a:>6}% " + "".join(f"{confusion[(a, b)]:>7}" for b in keys))

    if args.save:
        final = NaiveBayesClassifier(lines, seed=args.seed)
        store = LocalModelStore(Config().model_dir)
        version = store.save(MODEL_NAME, final.to_payload())
        print(f"saved model version {version} to {Config().model_dir}")


if __name__ == "__main__":
    main()

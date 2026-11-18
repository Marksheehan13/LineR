"""Measure field-level accuracy of OCR + field extraction on a folder made by tools.make_documents.

    python -m tools.evaluate --dir data/synthetic

Prints accuracy per quality level and layout. Synthetic documents flatter real-world accuracy:
the layouts are my own. Report clean, noisy and poor results separately and do not generalise."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from liner.business.field_extractor import RuleBasedFieldExtractor
from liner.integration.ocr_service import TesseractOcrEngine
from liner.models import OcrError


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def score(truth: dict, extraction) -> dict[str, tuple[int, int]]:
    """{metric: (correct, total)} for one document."""
    out: dict[str, tuple[int, int]] = {}
    out["supplier"] = (int(norm(extraction.supplier.value or "") == norm(truth["supplier"])), 1)
    out["date"] = (int(extraction.date.value is not None and extraction.date.value.isoformat() == truth["date"]), 1)
    out["total"] = (int(extraction.total.value is not None and str(extraction.total.value) == truth["total"]), 1)
    got = list(extraction.lines)
    amount_ok = detail_ok = rate_ok = rate_total = 0
    for t in truth["lines"]:
        hit = next((g for g in got if str(g.amount) == t["amount"]), None)
        if hit is not None:
            got.remove(hit)
            amount_ok += 1
            detail_ok += int(norm(hit.detail) == norm(t["detail"]))
            if t["printed_rate"]:
                rate_total += 1
                rate_ok += int(hit.printed_rate is not None and Decimal(t["band"]) == hit.printed_rate)
        elif t["printed_rate"]:
            rate_total += 1
    out["line amounts"] = (amount_ok, len(truth["lines"]))
    out["line details"] = (detail_ok, len(truth["lines"]))
    if rate_total:
        out["printed rates"] = (rate_ok, rate_total)
    out["no extra lines"] = (int(len(got) == 0), 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=Path("data/synthetic"))
    args = ap.parse_args()
    ocr, extractor = TesseractOcrEngine(), RuleBasedFieldExtractor()
    totals: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    unreadable = defaultdict(int)
    for truth_file in sorted(args.dir.glob("*.json")):
        truth = json.loads(truth_file.read_text())
        img = next((truth_file.with_suffix(e) for e in (".png", ".jpg") if truth_file.with_suffix(e).exists()), None)
        if img is None:
            continue
        key = (truth["quality"], "all")
        try:
            res = ocr.read_text(img.read_bytes())
        except OcrError:
            unreadable[key] += 1
            continue
        for metric, (ok, n) in score(truth, extractor.extract_fields(res)).items():
            totals[key][metric][0] += ok
            totals[key][metric][1] += n
    for key in sorted(totals):
        print(f"\n{key[0]}  (unreadable: {unreadable[key]})")
        for metric, (ok, n) in totals[key].items():
            print(f"  {metric:<15} {ok:>4}/{n:<4} {ok / n:6.1%}")


if __name__ == "__main__":
    main()

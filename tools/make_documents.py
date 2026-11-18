"""Generate synthetic invoice and receipt images with known answers.

    python -m tools.make_documents --out data/synthetic --n 30 --seed 7

Each document is rendered at three quality levels (clean, noisy, poor) and saved with a JSON file
holding the correct supplier, date, total and lines. All content is invented: no real business,
customer or invoice is used. Results measured on these documents flatter the real-world
performance, because the layouts are my own (Deliverable 1, section 1.6)."""
from __future__ import annotations

import argparse
import io
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from liner.parsing import quantize
from .synthetic_lines import random_supplier, vary
from .vocabulary import ADDRESS_LINES, ITEMS, TOWNS

QUALITIES = ("clean", "noisy", "poor")
LAYOUTS = ("invoice", "receipt", "receipt_rated")
MAX_DETAIL = 20            # descriptions are cut here so the printed text and the answer file agree


# Fonts are looked up by role on Linux, Windows and macOS, so the sample documents look the
# same on any machine (the OCR results depend on a normal-sized, readable font).
_FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("C:/Windows/Fonts"),
              Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts")]
_FONT_FILES = {
    "DejaVuSans.ttf": ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"],
    "DejaVuSans-Bold.ttf": ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"],
    "DejaVuSansMono.ttf": ["DejaVuSansMono.ttf", "consola.ttf", "cour.ttf", "Courier New.ttf"],
    "DejaVuSansMono-Bold.ttf": ["DejaVuSansMono-Bold.ttf", "consolab.ttf", "courbd.ttf", "Courier New Bold.ttf"],
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for file in _FONT_FILES.get(name, [name]):
        for folder in _FONT_DIRS:
            candidate = folder / file
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)               # Pillow's built-in font, scaled to the size


@dataclass
class SpecLine:
    detail: str
    amount: Decimal
    band: str
    item_type: str


@dataclass
class Spec:
    layout: str
    supplier: str
    address: str
    when: date
    doc_no: str
    lines: list[SpecLine]

    @property
    def total(self) -> Decimal:
        return quantize(sum((l.amount for l in self.lines), Decimal(0)))

    def vat_by_band(self) -> dict[str, Decimal]:
        gross: dict[str, Decimal] = {}
        for l in self.lines:
            gross[l.band] = gross.get(l.band, Decimal(0)) + l.amount
        return {b: quantize(g * Decimal(b) / (100 + Decimal(b))) for b, g in gross.items()}

    def truth(self, quality: str) -> dict:
        printed = self.layout in ("invoice", "receipt_rated")
        return {"layout": self.layout, "quality": quality, "supplier": self.supplier,
                "date": self.when.isoformat(), "total": str(self.total),
                "lines": [{"detail": l.detail, "amount": str(l.amount), "band": l.band,
                           "printed_rate": printed, "item_type": l.item_type} for l in self.lines],
                "printed_vat": {b: str(v) for b, v in self.vat_by_band().items()} if self.layout != "receipt_rated" else {}}


def make_spec(rng: random.Random, layout: str | None = None, n_lines: int | None = None) -> Spec:
    layout = layout or rng.choice(LAYOUTS)
    pool = [(band, itype, phrase) for band, types in ITEMS.items() for itype, phrases in types.items()
            for phrase in phrases]
    n = n_lines or rng.randint(1, 6)
    anchor = rng.choice(pool)                      # one supplier per document, matching its main item
    supplier = random_supplier(anchor[1], rng, p_matching=1.0)
    lines = []
    for i in range(n):
        band, itype, phrase = anchor if i == 0 else rng.choice(pool)
        amount = quantize(Decimal(rng.randint(100, 12000)) / 100)
        lines.append(SpecLine(vary(phrase, rng, noise=0.0)[:MAX_DETAIL].rstrip(), amount, band, itype))
    when = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
    return Spec(layout, supplier, f"{rng.randint(1, 120)} {rng.choice(ADDRESS_LINES)}, {rng.choice(TOWNS)}",
                when, f"INV-{rng.randint(1000, 9999)}", lines)


def _fmt_date(d: date, rng: random.Random) -> str:
    style = rng.choice(["slash", "dash", "text", "dot"])
    return {"slash": d.strftime("%d/%m/%Y"), "dash": d.strftime("%d-%m-%Y"),
            "text": f"{d.day} {d.strftime('%B %Y')}", "dot": d.strftime("%d.%m.%y")}[style]


def render(spec: Spec, rng: random.Random) -> Image.Image:
    return _invoice(spec, rng) if spec.layout == "invoice" else _receipt(spec, rng)


def _invoice(spec: Spec, rng: random.Random) -> Image.Image:
    W, H = 1240, 1500
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    big, mid, small = _font("DejaVuSans-Bold.ttf", 44), _font("DejaVuSans.ttf", 26), _font("DejaVuSans.ttf", 28)
    y = 70
    d.text((80, y), spec.supplier, font=big, fill="black"); y += 64
    d.text((80, y), spec.address, font=mid, fill="black"); y += 36
    d.text((80, y), f"Tel 0{rng.randint(21, 66)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}", font=mid, fill="black"); y += 80
    d.text((80, y), "INVOICE", font=_font("DejaVuSans-Bold.ttf", 36), fill="black"); y += 56
    d.text((80, y), f"Invoice No: {spec.doc_no}", font=small, fill="black"); y += 40
    d.text((80, y), f"Date: {_fmt_date(spec.when, rng)}", font=small, fill="black"); y += 80
    d.text((80, y), "Description", font=small, fill="black")
    d.text((700, y), "Amount (incl. VAT)", font=small, fill="black")
    d.text((1010, y), "VAT %", font=small, fill="black"); y += 46
    d.line((80, y - 6, W - 80, y - 6), fill="black", width=2)
    for l in spec.lines:
        d.text((80, y), l.detail, font=small, fill="black")
        d.text((820, y), f"{l.amount:.2f}", font=small, fill="black")
        d.text((1010, y), f"{Decimal(l.band).normalize():f}%", font=small, fill="black"); y += 44
    y += 30
    d.line((80, y, W - 80, y), fill="black", width=2); y += 20
    for b, v in spec.vat_by_band().items():
        d.text((80, y), f"VAT {Decimal(b).normalize():f}%", font=small, fill="black")
        d.text((820, y), f"{v:.2f}", font=small, fill="black"); y += 40
    y += 10
    d.text((80, y), "Total", font=_font("DejaVuSans-Bold.ttf", 32), fill="black")
    d.text((820, y), f"{spec.total:.2f}", font=_font("DejaVuSans-Bold.ttf", 32), fill="black"); y += 90
    d.text((80, y), "Thank you for your business.", font=mid, fill="black")
    return img.crop((0, 0, W, min(H, y + 120)))


def _receipt(spec: Spec, rng: random.Random) -> Image.Image:
    W = 640
    rated = spec.layout == "receipt_rated"
    mono, monob = _font("DejaVuSansMono.ttf", 24), _font("DejaVuSansMono-Bold.ttf", 28)
    rows = len(spec.lines) + len(spec.vat_by_band()) + 14
    img = Image.new("RGB", (W, 60 * rows // 2 + 260), "white")
    d = ImageDraw.Draw(img)
    y = 40
    d.text((W // 2, y), spec.supplier, font=monob, fill="black", anchor="ma"); y += 44
    d.text((W // 2, y), spec.address, font=mono, fill="black", anchor="ma"); y += 50
    d.text((40, y), f"Date: {_fmt_date(spec.when, rng)}  {rng.randint(8, 20)}:{rng.randint(10, 59)}", font=mono, fill="black"); y += 36
    d.text((40, y), f"Till {rng.randint(1, 6)}  Receipt {rng.randint(1000, 99999)}", font=mono, fill="black"); y += 50
    d.text((40, y), "-" * 40, font=mono, fill="black"); y += 34
    for l in spec.lines:
        text = l.detail
        d.text((40, y), text, font=mono, fill="black")
        if rated:
            d.text((360, y), f"{Decimal(l.band).normalize():f}%", font=mono, fill="black")
        d.text((470, y), f"{l.amount:6.2f}", font=mono, fill="black"); y += 34
    d.text((40, y), "-" * 40, font=mono, fill="black"); y += 40
    if not rated and rng.random() < 0.5:           # some receipts print VAT per rate, most print no rate per line
        for b, v in spec.vat_by_band().items():
            d.text((40, y), f"VAT {Decimal(b).normalize():f}%", font=mono, fill="black")
            d.text((470, y), f"{v:6.2f}", font=mono, fill="black"); y += 34
        y += 6
    d.text((40, y), "TOTAL", font=monob, fill="black")
    d.text((440, y), f"{spec.total:7.2f}", font=monob, fill="black"); y += 52
    d.text((40, y), f"Card {'*' * 12}{rng.randint(1000, 9999)}", font=mono, fill="black"); y += 40
    d.text((W // 2, y), "Thank you", font=mono, fill="black", anchor="ma"); y += 60
    return img.crop((0, 0, W, y))


def degrade(img: Image.Image, quality: str, rng: random.Random) -> tuple[bytes, str]:
    """Returns (file bytes, extension). 'clean' stays a PNG; the others become JPEGs with blur/rotation/noise."""
    if quality == "clean":
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue(), "png"
    angle = rng.uniform(-1.5, 1.5) if quality == "noisy" else rng.uniform(-3.5, 3.5)
    blur = 0.7 if quality == "noisy" else 1.4
    jpeg_q = 55 if quality == "noisy" else 28
    sigma = 6 if quality == "noisy" else 16
    im = img.rotate(angle, expand=True, fillcolor="white", resample=Image.BICUBIC)
    im = im.filter(ImageFilter.GaussianBlur(blur))
    arr = np.asarray(im).astype(np.float32)
    nprng = np.random.default_rng(rng.randint(0, 2**31))
    arr += nprng.normal(0, sigma, arr.shape)
    if quality == "poor":
        arr = 40 + arr * 0.75                      # washed out
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=jpeg_q)
    return out.getvalue(), "jpg"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--n", type=int, default=30, help="number of documents (each saved at 3 quality levels)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for i in range(args.n):
        spec = make_spec(rng, layout=LAYOUTS[i % len(LAYOUTS)])
        base = render(spec, rng)
        for q in QUALITIES:
            data, ext = degrade(base, q, rng)
            stem = f"doc{i:03d}_{spec.layout}_{q}"
            (args.out / f"{stem}.{ext}").write_bytes(data)
            (args.out / f"{stem}.json").write_text(json.dumps(spec.truth(q), indent=2))
    print(f"wrote {args.n * len(QUALITIES)} images and answer files to {args.out}")


if __name__ == "__main__":
    main()

"""Settings in one place. Nothing secret is stored here: the only secret (Flask's session key)
is generated at start-up or read from the LINER_SECRET_KEY environment variable."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# Irish VAT bands a line can be coded to. 0% also stands for VAT that cannot be reclaimed
# (see Deliverable 1, section 1.2). Checked against Revenue's rates page on 3 November 2026.
ALLOWED_BANDS: tuple[Decimal, ...] = (Decimal("23"), Decimal("13.5"), Decimal("9"), Decimal("0"))
RATE_TABLE_AS_OF = "2026-01-01"

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("LINER_DATA_DIR", ROOT / "var")))
    # Upload limits (risk R10)
    max_upload_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    allowed_extensions: tuple[str, ...] = ("png", "jpg", "jpeg", "pdf")
    max_pdf_pages: int = 1
    # OCR
    ocr_timeout_seconds: int = 30
    ocr_min_words: int = 4          # fewer words than this and the file counts as unreadable (R4)
    ocr_min_mean_conf: float = 35.0  # mean word confidence (0-100) below this counts as unreadable
    # Review thresholds (R1). Confidence values are 0-1.
    doubtful_field_conf: float = 0.80
    low_suggestion_conf: float = 0.70
    # Reconciliation / printed VAT check, in euro
    printed_vat_tolerance: Decimal = Decimal("0.02")
    # Classifier
    classifier_seed: int = 13
    # The prototype has one hard-coded demo user (mocked login, Deliverable 1 section 1.4)
    demo_user_id: str = "demo"
    demo_user_name: str = "Demo bookkeeper"
    secret_key: str = field(default_factory=lambda: os.environ.get("LINER_SECRET_KEY") or os.urandom(24).hex())

    @property
    def db_path(self) -> Path:
        return self.data_dir / "liner.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def model_dir(self) -> Path:
        return self.data_dir / "models"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.upload_dir, self.model_dir):
            p.mkdir(parents=True, exist_ok=True)

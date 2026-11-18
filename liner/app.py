"""Composition root: the one place that chooses the concrete component behind each interface.

To swap a component (SQLite -> PostgreSQL, Tesseract -> a managed OCR service, the demo user -> real
accounts) write one class that satisfies the interface in ``liner.interfaces`` and change one line here."""
from __future__ import annotations

import logging

from flask import Flask

from .business.accounts import DemoAuthenticator
from .business.classifier import load_or_train
from .business.document_coding import DocumentCodingService
from .business.document_numbering import SequentialNumbering
from .business.field_extractor import RuleBasedFieldExtractor
from .business.review_policy import ConfidenceReviewPolicy
from .business.vat_calculator import IrishVatCalculator
from .config import ALLOWED_BANDS, Config
from .data_access.audit_log import SqliteAuditLog
from .data_access.document_repository import SqliteDocumentRepository
from .data_access.image_store import LocalImageStore
from .data_access.model_store import LocalModelStore
from .database.sqlite_db import Database
from .integration.excel_exporter import OpenpyxlExcelExporter
from .integration.ocr_service import TesseractOcrEngine
from .integration.pdf_renderer import PillowPopplerRenderer
from .presentation_logic.controllers import build_blueprint
from .presentation_logic.input_validation import UploadLimits

log = logging.getLogger(__name__)


def build_services(config: Config, *, ocr=None, make_training_lines=None) -> DocumentCodingService:
    """Wire every component. ``ocr`` lets tests pass a fake engine behind the same interface."""
    config.ensure_dirs()
    if make_training_lines is None:
        from tools.synthetic_lines import generate_lines     # first run only: train on synthetic lines
        make_training_lines = lambda: generate_lines(2000, config.classifier_seed)

    db = Database(config.db_path)                                             # layer 5
    repository = SqliteDocumentRepository(db)                                 # layer 4
    images = LocalImageStore(config.upload_dir)
    models = LocalModelStore(config.model_dir)
    audit = SqliteAuditLog(db)

    classifier = load_or_train(models, make_training_lines, seed=config.classifier_seed)   # layer 3
    calculator = IrishVatCalculator(ALLOWED_BANDS, config.printed_vat_tolerance)
    policy = ConfidenceReviewPolicy(calculator, ALLOWED_BANDS, config.doubtful_field_conf,
                                    config.low_suggestion_conf, config.printed_vat_tolerance)
    return DocumentCodingService(
        renderer=PillowPopplerRenderer(timeout_seconds=config.ocr_timeout_seconds,       # layer 6
                                       max_pixels=config.max_image_pixels),
        ocr=ocr or TesseractOcrEngine(config.ocr_timeout_seconds, max_pixels=config.max_image_pixels),
        extractor=RuleBasedFieldExtractor(), classifier=classifier, calculator=calculator, policy=policy,
        numbering=SequentialNumbering(repository), repository=repository, images=images,
        exporter=OpenpyxlExcelExporter(), audit=audit,
        ocr_min_words=config.ocr_min_words, ocr_min_mean_conf=config.ocr_min_mean_conf)


def create_app(config: Config | None = None, *, ocr=None, make_training_lines=None) -> Flask:
    config = config or Config()
    coder = build_services(config, ocr=ocr, make_training_lines=make_training_lines)
    limits = UploadLimits(config.max_upload_bytes, config.max_image_pixels, config.allowed_extensions,
                          config.max_pdf_pages)
    app = Flask(__name__, static_folder=None)    # static files are served by the GUI layer's blueprint
    app.config["SECRET_KEY"] = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_bytes + 512 * 1024   # headroom for form overhead
    app.register_blueprint(build_blueprint(
        coder, DemoAuthenticator(config.demo_user_id, config.demo_user_name), ALLOWED_BANDS, limits))
    app.extensions["liner_coder"] = coder
    return app

"""The code structure mirrors the logical architecture, and components talk only through interfaces.

Each layer may import only: itself, the shared types (models, parsing, config) and the interfaces.
Only ``liner/app.py`` (the composition root) may import across layers."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent.parent / "liner"
LAYERS = ["presentation_logic", "business", "data_access", "database", "integration"]
SHARED = {"models", "parsing", "config", "interfaces"}

# D1 component -> module, so a marker can match the diagram to the code
COMPONENTS = {
    "Input validation": "presentation_logic/input_validation.py", "Controllers": "presentation_logic/controllers.py",
    "View models": "presentation_logic/controllers.py", "Document coding": "business/document_coding.py",
    "VAT calculator": "business/vat_calculator.py", "Document numbering": "business/document_numbering.py",
    "Field extractor": "business/field_extractor.py", "Review and reconcile": "business/review_policy.py",
    "Classifier (AI)": "business/classifier.py", "Login and accounts": "business/accounts.py",
    "Doc repository": "data_access/document_repository.py", "Image store": "data_access/image_store.py",
    "Model store": "data_access/model_store.py", "Audit log": "data_access/audit_log.py",
    "Database": "database/sqlite_db.py", "Excel exporter": "integration/excel_exporter.py",
    "OCR service (AI)": "integration/ocr_service.py", "Accounting package": "integration/accounting_package.py",
    "GUI templates": "presentation_gui/templates/review.html",
}


def imported_liner_modules(path: Path) -> set[str]:
    """Top-level liner sub-packages/modules this file imports (relative or absolute)."""
    out = set()
    pkg_parts = path.relative_to(PKG.parent).with_suffix("").parts[:-1]      # e.g. ('liner', 'business')
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level:                                                    # from ..models import X
                base = list(pkg_parts[: len(pkg_parts) - (node.level - 1)])
                parts = base + (node.module.split(".") if node.module else [])
            else:
                parts = (node.module or "").split(".")
            if parts and parts[0] == "liner":
                if len(parts) > 1:
                    out.add(parts[1])
                else:
                    out.update(a.name for a in node.names)                    # from liner import x
        elif isinstance(node, ast.Import):
            for a in node.names:
                p = a.name.split(".")
                if p[0] == "liner" and len(p) > 1:
                    out.add(p[1])
    return out


def layer_files():
    for layer in LAYERS:
        for f in sorted((PKG / layer).glob("*.py")):
            if f.name != "__init__.py":
                yield layer, f


@pytest.mark.parametrize("layer,path", list(layer_files()), ids=lambda v: v.name if isinstance(v, Path) else v)
def test_layers_do_not_import_each_other(layer, path):
    foreign = {m for m in imported_liner_modules(path) if m in LAYERS and m != layer}
    # database is the one layer data_access is allowed to use directly (layer 4 -> layer 5)
    if layer == "data_access":
        foreign.discard("database")
    assert not foreign, f"{path.name} imports {sorted(foreign)}; use the interfaces in liner/interfaces.py instead"


def test_the_composition_root_is_the_only_module_that_wires_layers_together():
    imported = imported_liner_modules(PKG / "app.py")
    assert set(LAYERS) <= imported


def test_shared_modules_do_not_depend_on_any_layer():
    for name in ("models", "parsing", "config", "interfaces"):
        assert not (imported_liner_modules(PKG / f"{name}.py") & set(LAYERS)), name


def test_every_diagram_component_has_a_module():
    missing = [c for c, rel in COMPONENTS.items() if not (PKG / rel).exists()]
    assert not missing, missing


def test_ai_components_are_reached_only_through_their_interfaces():
    """Nothing outside app.py and the AI modules themselves mentions Tesseract or NLTK."""
    allowed = {PKG / "integration/ocr_service.py", PKG / "business/classifier.py", PKG / "app.py"}
    for f in PKG.rglob("*.py"):
        text = f.read_text()
        if f in allowed:
            continue
        assert "pytesseract" not in text and "import nltk" not in text and "from nltk" not in text, f.name
        assert "TesseractOcrEngine" not in text or f.name == "app.py", f.name
        assert "NaiveBayes" not in text or f.name == "app.py", f.name


def test_business_layer_names_no_concrete_data_or_integration_classes():
    for _, f in (x for x in layer_files() if x[0] == "business"):
        text = f.read_text()
        for concrete in ("Sqlite", "Local", "Openpyxl", "sqlite3", "openpyxl", "pdf2image"):
            assert concrete not in text, f"{f.name} mentions {concrete}"

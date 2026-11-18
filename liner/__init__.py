"""LineR: reads Irish invoices and receipts with OCR and splits them into VAT-band rows.

Package layout mirrors the six layers of the target architecture (Deliverable 1, section 1.3):

    presentation_gui    layer 1  templates and static files
    presentation_logic  layer 2  input validation, controllers, view models
    business            layer 3  coding, VAT, numbering, extraction, review, classifier, accounts
    data_access         layer 4  repository, image store, model store, audit log
    database            layer 5  SQLite connection and schema
    integration         layer 6  OCR, PDF rendering, Excel exporter, accounting package (deferred)

Layers do not import each other. They depend on the interfaces in ``liner.interfaces`` and are
joined together in one place only: ``liner.app`` (the composition root).
"""

__version__ = "0.2.0"

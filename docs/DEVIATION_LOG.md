# Deviation log (Deliverable 2)

Each decision where the prototype differs from the Deliverable 1 target design, or where the design itself changed. Source: the Deliverable 2 technical document.

| ID | Decision | Context | Alternatives considered | Consequence | To reach target |
|---|---|---|---|---|---|
| D-01 | Components depend on interfaces.py and are wired in one app.py, instead of each layer importing the layer below. | Deliverable 1 said calls go down one layer at a time. Literal imports would make the business layer import SQLite and Tesseract classes. | Direct imports between layers. | Replacing a component is one class and one line. A test enforces the boundaries. Slightly more indirection to read. | No change: each class can later become a network client behind the same interface. |
| D-02 | code_document(upload, user) instead of code_document(upload). | A document must belong to a user for R8. | Read the user from a global or request object. | The interface is explicit; the prototype passes the one demo user. | None. |
| D-03 | Added a document renderer (PDF first page to image) in layer 6. | Tesseract reads images only, and the review screen needs a page image. | Convert inside the OCR service. | A new dependency (Poppler). Images are re-encoded, which drops EXIF data. | Run the renderer inside the OCR worker once OCR is split out. |
| D-04 | Added next_counter(user_id) to the repository interface. | Numbering needs an atomic counter. | Count confirmed documents (unsafe if requests overlap). | A row lock inside one transaction, tested with six threads. | Use a PostgreSQL sequence behind the same method. |
| D-05 | The model file holds training lines as JSON and the classifier is retrained on load. | A pickle can run code when loaded. | Pickle the trained model. | Safe and deterministic; retraining about 2,000 lines is under a second. Would not scale to a large model. | Store a trained artefact in managed storage and verify its checksum. |
| D-06 | No rounding difference on the last row: VAT is rounded once per band and net = gross minus VAT. | Deliverable 1 put any rounding difference on the last row. | Round per line and adjust the last row. | Net plus VAT equals gross on every row. Tested on 300 random documents. | None. |
| D-07 | Printed VAT is used only if within 2 cents of my calculation; otherwise the calculated figure is used and a warning shown. | Deliverable 1 said use the printed figure and check it. | Always use the printed figure. | A misread printed VAT cannot reach the sheet silently. | Make the tolerance a setting per supplier or country. |
| D-08 | Drafts are saved in the repository between screens. | Deliverable 1 did not say where a document waits during review. | Hidden form fields or the session. | Edits survive a reload and the corrections log has the original. Abandoned drafts accumulate. | Add a retention job (also needed for R9). |
| D-09 | Added info() to the classifier and model_info() to the coder. | R5 says the training date is shown. | Hard-code the text in the template. | The footer shows model version, training date and rate table date. | None. |
| D-10 | Rate configuration is one allowed set of bands (23, 13.5, 9, 0) with an 'as of' date. | Rates by date were not needed for one demo. | A table of rates with start and end dates. | A document dated before a rate change is checked against today's bands. | Replace with a table keyed by date. |

Not built: the Should and Could features from Deliverable 1 (batch upload, learning from corrections, camera capture).

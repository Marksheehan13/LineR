# Risk register: progress (Deliverable 2)

## Risks from Deliverable 1 (R1-R11)

| Risk | Topic | Status now |
|---|---|---|
| R1 | Wrong OCR read | Built and tested: image beside fields, doubtful fields flagged, no save unless lines add up. |
| R2 | AI suggestion mistaken for advice | Built: 'suggestion only' label on every screen; each suggested line needs a tick. |
| R3 | Accuracy unknown | tools/evaluate.py built; results go in Deliverable 3. |
| R4 | OCR failure | Built and tested with failing, timing-out, blank and blurred input; the app keeps working. |
| R5 | Rates and model drift | Out-of-set bands rejected, training date shown. Dated rates simplified (D-10). |
| R6 | Corrections not tracked | Built: every confirmed document logs corrections. Not yet reported. |
| R7 | Excel formula injection | Built and tested for = + - @, tab and return. |
| R8 | One user sees another's data | Built and tested; one demo user in practice. |
| R9 | Real data exposure | Synthetic data only, banner on every page. Retention and hosting not built. |
| R10 | Hostile files and text | Built and tested: type, size, pixel and page limits; a forged 'Total 0.00' line is caught by the reconcile check. |
| R11 | Rows not matching total | Built and tested; a failed save does not use up a number. |

## New risks found during Deliverable 2 (R12-R16)

| Risk | Category | New risk | Mitigation |
|---|---|---|---|
| R12 | Security | No login or CSRF protection. | Listens on 127.0.0.1 with synthetic data. Target: accounts and CSRF tokens. |
| R13 | Privacy | Images and abandoned drafts are never deleted. | Synthetic data only. Target: retention job (D-08). |
| R14 | Security | Tesseract and Poppler parse untrusted files in native code. | Limits and timeouts built. Target: sandboxed OCR worker. |
| R15 | Operational | Invoices printing net amounts break the VAT-inclusive assumption. | Caught by the reconcile check, which refuses to save. |
| R16 | Ethical | Classifier labels are my own illustrative choices, not checked by a tax professional. | Flagged as illustrative; every suggestion is confirmed by the user. Real use needs an accountant's labels. |

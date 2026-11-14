# AutoWiring v0.3.13 — Terminal Match Diagnostics

Run `py viewer.py` then hard-refresh http://127.0.0.1:8765.

After **Find candidate circuits** and **OCR all detected circles**, click **Diagnose terminal matches**. Yellow markers show segment endpoints. The report lists OCR-circle alternatives for each fuse path, with normalized vertical offset, horizontal gap, OCR confidence, and exact rejection reasons. Export **diagnostic JSON** for inspection, especially unmatched IG COIL paths.

This is intentionally a diagnostic-only release: it does not change path-matching thresholds, assert IG COIL→6, or increase verified connections. A/B CONT localized OCR remains experimental; v0.3.12 returned zero suggestions and is not claimed fixed. Run tests with `py -m unittest discover -s tests -v`.

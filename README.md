# AutoWiring v0.3.14 — Conservative Gap Audit + Targeted OCR

Run `py viewer.py`, hard refresh http://127.0.0.1:8765.

1. Run **Find candidate circuits** (10 candidates expected from v0.3.12 data).
2. Click **Audit collinear segment gaps**. Orange dashed lines show possible same-row gaps between nearby *candidate-wire* segments. These are suggestions only; the program does not merge them, cross junctions, or claim continuity.
3. Click **Diagnose terminal matches**, then **OCR unmatched endpoints (raw)**. This performs small-crop OCR at 2×/4× scales and Tesseract PSM 6/11/12, preserving raw output for inspection.
4. Export **gap audit JSON** and **raw OCR JSON** for next iteration.

**Limitations:** No electrical verification, no inferred connector-pin mappings. The current OCR crop is endpoint-centered and may not cover A/B CONT; A/B OCR remains unresolved. Segment continuity is not established by collinearity alone. Tests: `py -m unittest discover -s tests -v`.

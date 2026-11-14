# AutoWiring v0.3.15 — Visual Gap Inspection

Run `py viewer.py` and hard-refresh http://127.0.0.1:8765.

1. Run **Find candidate circuits**.
2. Click **Audit collinear segment gaps** (v0.3.14).
3. Click **Inspect gap image crops** (v0.3.15). The application displays original-diagram crop evidence with orange endpoint markers and a cyan row reference.
4. Export **gap-visual JSON**. Compare all four recurring gaps (IG COIL, MTR, ABS, BACK) to determine whether the common gap represents a symbol, border, missing detection, or something else.
5. To investigate terminal numbers, run **Diagnose terminal matches** then **OCR unmatched endpoints (raw)**.

Visual classification only distinguishes dark content from light gap; it **does not** recognize component symbols, prove segment continuity, merge paths, or assign terminal numbers. The IG COIL→6 and A/B CONT issues remain open. Electrically verified connections: **0**.

Run tests: `py -m unittest discover -s tests -v`.

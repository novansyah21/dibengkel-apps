# AutoWiring v0.3.12 — Split Fuse Association + Localized A/B OCR

Run `py viewer.py` then hard refresh http://127.0.0.1:8765.

**To rebuild associations:** click **Find candidate circuits** again after upgrading. The updated association module now includes OCR-grounded split-token IG COIL labels from the fuse audit. Then click **Match fuse paths to OCR circles** again; existing v0.3.10 results are not retroactively modified.

**A/B CONT:** click **Scan A/B CONT (tile OCR)**. The backend performs overlapping-tile Tesseract OCR and displays green suggestions; inspect the image and export localized OCR JSON. Localized A/B OCR suggestions are NOT yet promoted to fuse associations. This deliberately avoids automatic false-positive wiring.

All results are geometric/OCR hypotheses. No connector-pin mapping, junction verification, or electrical continuity is asserted. Back up output/autowiring.db. Tests: `py -m unittest discover -s tests -v`.

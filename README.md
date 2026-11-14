# AutoWiring v0.3.11 — Fuse Recognition & Association Audit

Run `py viewer.py` and hard refresh http://127.0.0.1:8765.

After OCR/graph/segmentation and **Find candidate circuits**, select **Audit missing fuse labels**. Orange indicators show OCR-recognized fuse labels that were not included in v0.3.5 candidate associations, with nearby horizontal candidate segments shown dashed. Export the audit JSON for review.

Supports direct and adjacent-token recognition for IG COIL and A/B CONT, without fabricating labels missing from source OCR. This is an **audit**, not automatic rewiring: it does not add associations, force terminal matches, infer crossings or verify continuity. If no IG COIL/A/B appears, upstream OCR failed and a localized OCR crop or manual review is required.

Tables: fuse_audit_runs_v0311 and fuse_audit_items_v0311. Back up output/autowiring.db. Tests: `py -m unittest discover -s tests -v`.

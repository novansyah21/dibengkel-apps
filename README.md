# AutoWiring v0.3.5 — Candidate Terminal Association (Beta)

Local-first diagram viewer. Run `py -m pip install -r requirements-auto.txt` then `py viewer.py`. Open http://127.0.0.1:8765.

## Workflow
1. Select Junction Block diagram.
2. Analyze diagram automatically (if no OCR/CV data).
3. Build geometry graph.
4. Segment & group paths.
5. **Find candidate circuits**.
6. Select fuse candidate → **Highlight candidate path**.
7. **Export candidates JSON** for technical review.

## What is and isn't implemented
- Matches OCR fuse labels to nearby retained horizontal geometric segments.
- Groups collinear segments based on v0.3.4 segmentation; may identify nearby OCR terminal number when unambiguous.
- Stores evidence in `association_runs_v035` and `association_candidates_v035` SQLite tables.
- Highlights candidate segments in yellow and shows status in Inspector.
- **Does not** infer connector ownership, verified terminal pins, actual wire continuity, crossing connectivity, or electrical end-to-end circuit. The term “candidate circuit” is only a visual association.
- A terminal OCR number (e.g. 6) is **not** a verified connector terminal mapping.
- Vehicle applicability remains unverified.
- The heuristics are tuned to the first Junction Block benchmark, not validated across manufacturers.
- Sample diagram assets are intentionally excluded from Git due to uncertain redistribution rights.

Tests: `py -m unittest discover -s tests -v`.

Back up local `output/autowiring.db` before testing a new version.

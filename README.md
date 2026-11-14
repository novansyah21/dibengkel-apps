# AutoWiring v0.3.8 — Visual Evidence Audit (Experimental)

## Windows
```powershell
py -m pip install -r requirements-auto.txt
py viewer.py
```
Open http://127.0.0.1:8765 and hard-refresh.

## Workflow
1. Analyze diagram automatically (if needed).
2. Build geometry graph.
3. Segment & group paths.
4. Find candidate circuits.
5. Detect terminal numbers near path endpoints.
6. Detect terminal circles & OCR.
7. **Audit all detected circles**.
8. Enable **Show all detected circles (debug)** and inspect orange rejected/green OCR-match circles; export full evidence JSON.

## New in v0.3.8
- Audit every Hough-detected circle, including unmatched/rejected hypotheses.
- Store reasons for missing endpoints, excessive distance, ambiguous proximity and failed OCR.
- Show status breakdown and inspectable SVG overlay.
- Persist data in `evidence_runs_v038` and `evidence_circles_v038`.

**Not implemented:** True circuit path reconstruction, validated connector-pin mapping, verified electrical connectivity, OCR crop preview. These require further image-level validation. Debug circles can overlap fuse symbols or unrelated marks. The v0.3.7 baseline remains unchanged. No sample images are committed due to uncertain redistribution rights.

Back up `output/autowiring.db` before testing. Tests: `py -m unittest discover -s tests -v`.

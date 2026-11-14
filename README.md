# AutoWiring v0.3.7 — Strict Circle-First OCR (Experimental)

## Windows
```powershell
py -m pip install -r requirements-auto.txt
py viewer.py
```
Open http://127.0.0.1:8765 and hard refresh.

## Steps
1. Analyze diagram automatically.
2. Build geometry graph.
3. Segment & group paths.
4. Find candidate circuits.
5. Detect terminal numbers near path endpoints (v0.3.6, baseline).
6. **Detect terminal circles & OCR** (v0.3.7).
7. Enable **Show detected terminal evidence**, review orange circle overlays and export JSON.

v0.3.7 runs Hough circle detection, matches circles to nearby geometric endpoints, OCRs only inside circle interiors, and rejects ambiguous or low-confidence matches. Its output is stored in `circle_runs_v037` and `circle_candidates_v037`.

**Limitations:** This is experimental. Circle parameters are tuned for small diagrams, may miss valid terminal symbols, and may detect unrelated circular marks. A strict zero-result outcome is possible and preferable to inventing mappings. Connector ownership is NOT asserted. No verified electrical continuity, verified pinout, or source applicability. The older v0.3.6 output remains visible separately for debugging but is not promoted to verified data.

Keep licensed source images in local `sample_assets/`; no images are committed. Back up `output/autowiring.db` before testing.

Tests: `py -m unittest discover -s tests -v`.

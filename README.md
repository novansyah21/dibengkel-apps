# AutoWiring v0.3.6 — Experimental Terminal OCR

## Run (Windows)
```powershell
py -m pip install -r requirements-auto.txt
py viewer.py
```
Open http://127.0.0.1:8765, then hard-refresh browser.

## Workflow
1. Select Junction Block.
2. Analyze diagram automatically (if needed).
3. Build geometry graph.
4. Segment & group paths.
5. Find candidate circuits.
6. **Detect terminal numbers near path endpoints**.
7. Review the terminal/connector candidate list and export JSON.

## What's new
- Crop around the rightmost endpoint of retained candidate segments, upscale and contrast-enhance, then OCR digits using Tesseract.
- Compare endpoint x position to OCR connector headers; reject close ties.
- Persist output in `terminal_runs_v036` and `terminal_candidates_v036`.
- Each candidate remains `ocr_visual_candidate_unverified`.

## Critical limitations
- Endpoint crop is **not** a reliable terminal detector; diagrams may place terminal numbers elsewhere.
- Connector x-alignment is not proof of pin ownership.
- No verified electrical continuity, terminal-pin mapping, or cross-diagram validation.
- OCR can return wrong numbers. Always compare against the original source.
- Assets not committed due to uncertain redistribution rights; keep authorized local images in `sample_assets/`.
- Back up `output/autowiring.db` before upgrading.

Tests: `py -m unittest discover -s tests -v`.

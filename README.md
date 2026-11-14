# AutoWiring v0.3.17 — One-click Fuse Recognition & Circuit Tracing

This feature **continues the saved v0.3.16 analysis**. It does **not** rerun earlier image OCR, geometric graph building, segmentation, association, independent circle OCR, gap inspection, or component detection.

## Run on Windows

Keep the **same** `output/autowiring.db` and `sample_assets/` as v0.3.16 (do not delete or reset the database).

```powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
git fetch origin
git switch --track origin/feature/v0.3.17
py viewer.py
```

Open `http://127.0.0.1:8765` and press Ctrl+Shift+R once if the old JS is cached. Select **Junction Block**, then click the **single blue button at the top: "▶ Continue saved analysis (v0.3.17)"**. Do not run the old analysis buttons again. The app consumes persisted v0.3.16 components and older OCR/segmentation.

## What happens, exactly?

- Existing four fuse-component hypotheses are **reused by ID** and evaluated against **unannotated original pixels** for waveform-like evidence. A match is still only a visual candidate.
- Existing terminal circle numbers and geometric segments are **read from SQLite**; one candidate trace is proposed only where endpoints meet geometrically. It does not cross ambiguous intersections or assume every visually nearby line is connected.
- Fuse rating OCR **first reuses prior OCR tokens**. If a rating is not available, a **focused, small-image crop** is OCR'd (at most two configurations per fuse). Tesseract being unavailable does not block building the non-OCR trace.
- Each result is cached against the component run, independent-circle OCR run, image hash, prior OCR run, and segmentation IDs. Clicking the blue button **again** returns `cache_hit: true`; no previous stage or focused OCR runs again for unchanged inputs.
- Manual *visual* confirmation of fuse symbols and their ampere rating is separately saved; it **never confirms electrical continuity** or physical connector ownership.
- The overlay is **dashed amber** (unverified). All previews and JSON exports retain `electrically_verified: false`.
- Export **`autowiring-junction_block-trace-review-v0317.json`** and share it to inspect candidate traces and OCR evidence.

## Prerequisites / limitations

- Existing `output/autowiring.db` with a v0.3.16 component run is **required**. There is deliberately **no automatic legacy pipeline rebuild** if the database is empty.
- Independent-circle OCR is optional: if absent, the app explicitly reports it, without running circle detection again.
- The vehicle/diagram applicability remains unverified. Same-row proximity, OCR text, apparent waveform, and endpoint collinearity are not proof of electrical connectivity, fusing, connector pin number, or circuit direction.
- Pillow and pytesseract/Tesseract are only used when already available for focused image analysis. Existing run can be reviewed without rerunning OCR.

## Regression tests

```powershell
py -m unittest discover -s tests -p "test_trace_review.py" -v
```

CI additionally compiles Python and syntax-checks `web/app.js`. All results remain visual hypotheses, not electrical evidence.

# AutoWiring v0.3.9 — Endpoint-independent Circle OCR (Experimental)

Run on Windows:
```powershell
py -m pip install -r requirements-auto.txt
py viewer.py
```
Open http://127.0.0.1:8765 and hard refresh.

Workflow: run the v0.3.8 audit sequence, then click **OCR all detected circles (no endpoint filter)**. Toggle **Show independently read circles** to highlight purple candidates and export independent OCR JSON.

Unlike v0.3.8, this stage attempts OCR on **every** detected Hough circle, including the 86 previously marked too far from candidate endpoints. Results are stored in independent_runs_v039 and independent_circles_v039. This can take longer due to many Tesseract invocations.

**Important:** These numbers are UNASSOCIATED visual OCR readings, not fuse pinouts, reconstructed circuit paths, verified connector identities, or electrical continuity. False positives from fuse symbols or other circles remain possible. No sample source images are redistributed.

Next planned: OCR crop preview, segment-to-circle matching and conservative multi-branch reconstruction. Back up output/autowiring.db before testing.

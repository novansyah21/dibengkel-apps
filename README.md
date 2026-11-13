# AutoWiring — Project Bengkel

Local-first wiring diagram analysis prototype (current development version: **v0.3.3**).

## Setup (Windows)

```powershell
py -m pip install -r requirements-auto.txt
py viewer.py
```

Open `http://127.0.0.1:8765`. OCR requires a local Tesseract installation.

## Repository workflow

- `main`: working version.
- Development changes should be proposed in branches / pull requests.
- Keep local databases, OCR outputs, downloaded source material and temporary files out of Git.
- Only commit diagram assets when redistribution rights are confirmed.

**Status:** repository initialized. The v0.3.3 application source has **not yet been uploaded**; it must be committed from the local v0.3.3 folder once. See the accompanying setup instructions in chat.

## Data caution

OCR and geometric graph outputs are unverified candidates, **not** electrically validated wiring paths. Do not rely on them alone for vehicle diagnosis.

# AutoWiring v0.3.16 — Component-aware fuse hypotheses

Run `py viewer.py` and refresh http://127.0.0.1:8765.

Sequence: **Find candidate circuits** → **Audit collinear segment gaps** → **Inspect gap image crops** → **Identify fuse component candidates**. Click a candidate for a graph preview or export **component-graph JSON**.

Candidate graph is `source_wire -> fuse_symbol_candidate -> target_wire`. No direct wire-to-wire joins, no electrical verification, no fuse-rating OCR claim, and no automatic terminal assignment. This is a **rule-based candidate** based on fuse-associated gaps and image ink, not a trained symbol classifier. Inspect each image crop manually before treating the component type as confirmed.

Audit buttons now write compact summaries to the status bar instead of showing raw JSON alerts. Other legacy analysis buttons may still show alerts.

Tests: `py -m unittest discover -s tests -v`.

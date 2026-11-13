# AutoWiring v0.3.4 — Diagram Segmentation & Candidate Path Grouping

Run: `py -m pip install -r requirements-auto.txt` then `py viewer.py`. Open http://127.0.0.1:8765.

Workflow: Analyze diagram → Build geometry graph → **Segment & group paths (beta)**.

New: region-aware filtering for Junction Block, optional red overlay of excluded lines, green overlay of retained candidate segments, collinear grouping, and Inspector synchronization.

**Limitations:** Junction Block thresholds are heuristics, not trained segmentation. Some genuine wires may be excluded and structural lines may remain. Groups are geometric, NOT verified electrical paths. No electrical connectivity or terminal mapping is inferred. Other diagrams use generic classification.

Tests: `py -m unittest discover -s tests -v`.

Diagram assets require appropriate permissions before redistribution.

# AutoWiring v0.3.3 — Candidate Circuit Graph (Beta)

Local-first extension of v0.3.2. No hosting required.

## Windows

```powershell
cd D:\dibengkelapp\AutoWiring-v0.3.3
py -m pip install -r requirements-auto.txt
py viewer.py
```
Open http://127.0.0.1:8765 (stop prior server first). Tesseract OCR executable must be installed separately and discoverable in PATH.

## Workflow
1. Choose Junction Block diagram.
2. Click **Analisis diagram otomatis** to run OCR + CV.
3. Click **Build geometry graph**.
4. Use **Display layers** to toggle connectors, fuses, raw lines, candidate graph, ambiguous crossings.
5. Select a detected label and click **Highlight nearby segment**. This is **nearest line**, NOT an electrically traced path.
6. **Export graph JSON** for review.

## Critical limitations
- Crossings are **never** treated as electrical junctions; all are ambiguous.
- Label-to-line associations are proximity-based and unverified.
- No reliable automatic terminal mapping, fuse-rating association, circuit continuity, graph traversal, or troubleshooting.
- The graph is a geometric index of CV-detected horizontal/vertical segments only.
- All sample vehicle applicability is unverified. Do not use for electrical repair decisions without qualified verification.
- Sample images are for local evaluation; confirm source rights before redistributing.

## Existing DB
Use `py viewer.py --db "D:\dibengkelapp\AutoWiring-v0.3.2\output\autowiring.db"` to reuse prior analysis. Backup first. New tables: `graph_runs_v033`, `graph_edges_v033`, `graph_events_v033`, `graph_label_links_v033`. Existing data is not deleted.

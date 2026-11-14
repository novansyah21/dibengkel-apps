# AutoWiring v0.3.10 — Geometric Path-to-Terminal Candidates

Run: `py viewer.py`, then hard refresh http://127.0.0.1:8765.

After **Find candidate circuits** and **OCR all detected circles (no endpoint filter)**, click **Match fuse paths to OCR circles**. Cyan rings indicate geometric matches. Inspect candidates and export path match JSON.

The matching algorithm compares the rightmost end of each candidate's existing horizontal segment group to independently OCR-read circles on approximately the same row. It rejects missing and near-tied alternatives. It does **not** infer connector identity, branches, crossings, or electrical continuity. All results are `geometric_candidate_unverified`. If zero matches appear, inspect exported JSON rather than forcing thresholds.

Tables: `path_match_runs_v0310`, `path_matches_v0310`. Source images stay local in sample_assets. Back up output/autowiring.db before testing. Tests: `py -m unittest discover -s tests -v`.

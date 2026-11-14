"""Vehicle-agnostic, unverified OCR/CV proposal scanner with input-hash cache.

This is NOT vehicle-agnostic electrical netlist recognition. Only image text
and line segments are proposed; no connection is automatically confirmed.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from autowiring.auto_mapping import extract as auto_extract,SCHEMA as AUTO_SCHEMA

SCHEMA="""
CREATE TABLE IF NOT EXISTS universal_scan_runs_v0400(
 id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,
 image_sha256 TEXT NOT NULL,algorithm TEXT NOT NULL,
 auto_run_id TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,
 UNIQUE(diagram_id,image_sha256,algorithm)
);
"""
ALGORITHM="generic_ocr_cv_proposals_v0400.1"

def _last(db,diagram_id):
    row=db.execute("""SELECT * FROM universal_scan_runs_v0400
           WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1""",
           (diagram_id,)).fetchone()
    return dict(row) if row else None

def _result(db,row,cache_hit):
    summary=json.loads(row["summary_json"])
    candidates=[dict(x) for x in db.execute("""
        SELECT kind,label,x,y,w,h,confidence,source,verification
        FROM auto_candidates_v032 WHERE run_id=?
        ORDER BY confidence DESC,kind LIMIT 120""",(row["auto_run_id"],))]
    return {"scan_id":row["id"],"auto_run_id":row["auto_run_id"],
            "cache_hit":cache_hit,
            "image_sha256":row["image_sha256"],
            "summary":summary,"candidates":candidates,
            "electrically_verified_connections":0,
            "status":"unverified_text_and_line_proposals_only"}

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        db.executescript(AUTO_SCHEMA+SCHEMA)
        row=_last(db,diagram_id)
        if not row:return {"run":None,"candidates":[]}
        return {"run":_result(db,row,True),"candidates":[]}

def scan(dbpath,diagram_id,image_path):
    p=Path(image_path)
    if not p.is_file():raise ValueError("Original diagram image not found")
    image_hash=hashlib.sha256(p.read_bytes()).hexdigest()
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        db.executescript(AUTO_SCHEMA+SCHEMA)
        row=db.execute("""SELECT * FROM universal_scan_runs_v0400
              WHERE diagram_id=? AND image_sha256=? AND algorithm=?""",
              (diagram_id,image_hash,ALGORITHM)).fetchone()
        if row:return _result(db,dict(row),True)
    # Existing generic OCR/CV extraction; NO old fuse-component graph or
    # matching pipeline runs are triggered for unfamiliar vehicle diagrams.
    extraction=auto_extract(p,diagram_id,dbpath,ocr=True,lines=True,max_candidates=450)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        counts=[dict(x) for x in db.execute("""
           SELECT kind,count(*) AS count FROM auto_candidates_v032
           WHERE run_id=? GROUP BY kind ORDER BY kind""",
           (extraction["run_id"],))]
        summary={
            "diagram_id":diagram_id,"candidate_count":extraction["candidates"],
            "ocr_available":extraction["ocr_available"],
            "cv_available":extraction["cv_available"],
            "kinds":counts,"notes":extraction["notes"],
            "older_stages_rerun":0,
            "no_validated_electrical_connections":True,
            "manual_review_required":True,
            "warning":"Text/line image recognition is generic; auto mapping and vehicle-specific diagnosis are NOT verified. Lines crossing or collinear are NOT joined.",
        }
        rid=uuid.uuid4().hex
        db.execute("""INSERT OR IGNORE INTO universal_scan_runs_v0400
           (id,diagram_id,image_sha256,algorithm,auto_run_id,summary_json)
           VALUES(?,?,?,?,?,?)""",
           (rid,diagram_id,image_hash,ALGORITHM,extraction["run_id"],
            json.dumps(summary,ensure_ascii=False)))
        db.commit()
        row=db.execute("""SELECT * FROM universal_scan_runs_v0400
            WHERE diagram_id=? AND image_sha256=? AND algorithm=?""",
            (diagram_id,image_hash,ALGORITHM)).fetchone()
        return _result(db,dict(row),False)

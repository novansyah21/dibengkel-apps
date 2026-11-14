"""AutoWiring 0.3.22 — usable review-first MVP snapshot, NOT a diagnostic netlist.

Reads persisted v0.3.20 six-fuse/branch hypotheses and v0.3.21 disputed
terminal OCR. No OCR, geometry, tracing, or image-wide analysis is triggered.
Unresolved labels require user visual review; visual confirmation is not an
electrical continuity claim. The exact source diagram is SHA locked.
"""
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import uuid

from autowiring.trace_review import newest_id
from autowiring.branch_tracing import JUNCTION_IMAGE_SHA256,JUNCTION_SIZE

SCHEMA="""
CREATE TABLE IF NOT EXISTS mvp_snapshots_v0322(
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 branch_run_id TEXT NOT NULL,
 accuracy_run_id TEXT NOT NULL,
 snapshot_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 report_json TEXT NOT NULL,
 UNIQUE(diagram_id,snapshot_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_mvp_snaps_v0322 ON mvp_snapshots_v0322(diagram_id,created_at);
"""
LABEL_ORDER={"IG COIL":0,"MTR":1,"A/B":2,"IG1 SIG":3,"ABS":4,"BACK":5}

def _as_dicts(db,query,args=()):
    return [dict(x) for x in db.execute(query,args)]

def _decode(row,field,fallback=None):
    if fallback is None:fallback={}
    return json.loads(row[field]) if row[field] else fallback

def _previews(image,center):
    """Present a human-readable glyph view without running additional OCR."""
    from PIL import Image
    x=round(float(center[0])*image.width)
    y=round(float(center[1])*image.height)
    box=(x-12,y-12,x+13,y+13)
    raw=image.crop(box).convert("L")
    # Purely a diagnostic view. Radial suppression can erase outer digit
    # strokes; NEVER interpret this as recognition evidence or a corrected OCR.
    cleaned=raw.copy()
    pixels=cleaned.load()
    for py in range(cleaned.height):
        for px in range(cleaned.width):
            if math.hypot(px-12,py-12)>8.65:
                pixels[px,py]=255
    def encode(im):
        buff=io.BytesIO();im.save(buff,format="PNG")
        return base64.b64encode(buff.getvalue()).decode("ascii")
    return {"original_png_base64":encode(raw),
            "experimental_circle_border_suppression_png_base64":encode(cleaned),
            "crop_box":list(box),
            "warning":"Circle suppression is ONLY for human review; it can erase digit strokes and does not yield an OCR result."}

def _state_for_terminal(terminal,path_key,accuracy_by_key,visual_by_key):
    terminal=terminal or {}
    disputed=accuracy_by_key.get(path_key)
    original=terminal.get("number")
    if disputed:
        visual=visual_by_key.get(path_key,{})
        manually_confirmed=(visual.get("review_status")=="visually_confirmed" and
                            bool(visual.get("manual_number")))
        effective=visual["manual_number"] if manually_confirmed else None
        provenance=("human_visual_review_only" if manually_confirmed
                    else "unresolved_ocr_requires_visual_review")
        return {
            "number":effective,"status":provenance,
            "machine_ocr_candidate":disputed.get("new_ocr_number"),
            "previous_machine_ocr_candidate":disputed.get("prior_ocr_number"),
            "independent_visual_reference_not_ocr":disputed["reference_number"],
            "human_visual_status":visual.get("review_status","needs_review"),
            "human_visual_number":visual.get("manual_number"),
            "reference_consistent_with_human_review":
                bool(manually_confirmed and effective==disputed["reference_number"]),
            "circle_id":disputed["circle_id"],
            "source":"saved_v0321_evidence",
            "electrically_verified":False,"connector_pinout_verified":False
        }
    # Even previously OCR-recognized numbers stay unverified suggestions.
    return {
        "number":str(original) if original not in (None,"") else None,
        "status":"historical_ocr_candidate_unverified" if original else "not_read",
        "machine_ocr_candidate":original,
        "human_visual_status":"needs_review",
        "circle_id":terminal.get("circle_id"),
        "ocr_confidence_not_connectivity_confidence":terminal.get("ocr_confidence"),
        "source":"saved_v0320_terminal_candidate",
        "electrically_verified":False,"connector_pinout_verified":False
    }

def assemble(dbpath,diagram_id,image_path=None,with_previews=True):
    """Return a reviewable six-fuse sample report with strictly honest status."""
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        branch_id=newest_id(db,"branch_runs_v0320",diagram_id)
        accuracy_id=newest_id(db,"terminal_accuracy_runs_v0321",diagram_id)
        if not branch_id or not accuracy_id:
            raise ValueError("Need saved v0.3.20 and v0.3.21 results in the SAME output/autowiring.db. Older stages will not be rerun.")
        ar=db.execute("SELECT * FROM terminal_accuracy_runs_v0321 WHERE id=?",
                      (accuracy_id,)).fetchone()
        if ar["parent_run_id"]!=branch_id:
            raise ValueError("v0.3.21 terminal evidence does not match latest v0.3.20 branch run; no automatic reconstruction.")
        a_summary=json.loads(ar["summary_json"])
        if (diagram_id!="junction_block" or
                a_summary.get("source_image_sha256")!=JUNCTION_IMAGE_SHA256):
            raise ValueError("MVP source lock mismatch. The visual reference is only valid for this exact Junction Block.")
        accuracy=_as_dicts(db,
            "SELECT * FROM terminal_accuracy_items_v0321 WHERE run_id=?",(accuracy_id,))
        if len(accuracy)!=4:
            raise ValueError("Expected four disputed terminals in saved v0.3.21 run; got "+str(len(accuracy)))
        a_by_key={a["path_key"]:a for a in accuracy}
        visual_by_key={a["path_key"]:a for a in _as_dicts(db,
            "SELECT * FROM terminal_accuracy_reviews_v0321 WHERE diagram_id=?",(diagram_id,))}
        branch_reviews={a["branch_key"]:a for a in _as_dicts(db,
            "SELECT * FROM branch_reviews_v0320 WHERE diagram_id=?",(diagram_id,))}
        raw_fuses=_as_dicts(db,
            "SELECT * FROM branch_items_v0320 WHERE run_id=?",(branch_id,))
        if len(raw_fuses)!=6 or {r["fuse_label"] for r in raw_fuses}!=set(LABEL_ORDER):
            raise ValueError("MVP needs the six persisted Junction Block fuse candidates. No new CV/graph stages will run.")
        image=None
        if image_path is not None:
            p=Path(image_path)
            if not p.is_file():raise ValueError("Original image missing; restore sample_assets.")
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            if sha!=JUNCTION_IMAGE_SHA256:raise ValueError("Original image SHA changed; saved geometry is not reusable.")
            if with_previews:
                from PIL import Image
                with Image.open(p) as src:
                    if src.size!=JUNCTION_SIZE:raise ValueError("Diagram source dimensions mismatch.")
                    image=src.convert("L")
        output=[];terminal_count=0;branch_count=0;continuations=0
        for row in sorted(raw_fuses,key=lambda r:LABEL_ORDER[r["fuse_label"]]):
            evidence=_decode(row,"evidence_json")
            branches=_decode(row,"branches_json",[])
            geometry=_decode(row,"geometry_json")
            main=_decode(row,"main_path_json")
            fuse=row["fuse_label"]
            principal=_state_for_terminal(evidence.get("primary_terminal"),
                    "main:"+fuse,a_by_key,visual_by_key)
            terminal_count+=1
            paths=[]
            for b in branches:
                if b.get("kind")=="off_page_continuation":
                    continuations+=1
                    dest={"kind":"off_page_continuation","marker":(b.get("continuation") or {}).get("marker_text"),
                          "status":"source_visual_candidate_not_connector_pin",
                          "electrically_verified":False}
                else:
                    dest=_state_for_terminal(b.get("terminal"),b["branch_key"],
                                             a_by_key,visual_by_key)
                    dest["kind"]="connector_terminal_candidate"
                    terminal_count+=1
                paths.append({
                    "path_key":b.get("branch_key"),"kind":b.get("kind"),
                    "side":b.get("side"),"status":b.get("status"),
                    "visual_review":branch_reviews.get(b.get("branch_key"),{}).get("visual_status","needs_review"),
                    "destination":dest,"points":b.get("points",[]),
                    "pixel_support":b.get("horizontal_ink_coverage"),
                    "electrically_verified":False
                })
                branch_count+=1
            output.append({
                "fuse_label":fuse,
                "rating_candidate":row["rating_text"],
                "rating_status":row["rating_status"],
                "source_kind":row["source_kind"],
                "fuse_row_y_px":geometry.get("fuse_y_px"),
                "main":{"status":main.get("status"),
                        "points":main.get("points",[]),
                        "pixel_support":main.get("horizontal_ink_coverage"),
                        "destination":principal,
                        "electrically_verified":False},
                "branches":paths,
                "electrically_verified":False
            })
        review_queue=[]
        for item in accuracy:
            visual=visual_by_key.get(item["path_key"],{})
            entry={
                "path_key":item["path_key"],"fuse_label":item["fuse_label"],
                "path_kind":item["path_kind"],
                "circle_id":item["circle_id"],
                "reference_number":item["reference_number"],
                "reference_origin":item["reference_origin"],
                "new_machine_ocr":item["new_ocr_number"],
                "previous_machine_ocr":item["prior_ocr_number"],
                "ocr_status":item["ocr_status"],
                "human_visual_status":visual.get("review_status","needs_review"),
                "manual_number":visual.get("manual_number"),
                "electrically_verified":False
            }
            evidence=json.loads(item["evidence_json"])
            entry["circle_center"]=evidence.get("circle_center")
            if image and entry["circle_center"]:
                entry["preview"]=_previews(image,entry["circle_center"])
            review_queue.append(entry)
        reviews_done=sum(r["human_visual_status"]=="visually_confirmed"
                         and bool(r["manual_number"]) for r in review_queue)
        flags={
            "viewer_and_assisted_review_mvp":True,
            "fully_automatic_diagram_interpretation":False,
            "reliable_automated_terminal_ocr":False,
            "automotive_diagnostic_decision_support":False,
            "electrical_continuity_proven":False,
            "other_vehicle_diagrams_supported_by_this_profile":False
        }
        return {
            "report_version":"MVP-0.1/v0322",
            "diagram_id":diagram_id,
            "source_sha256":JUNCTION_IMAGE_SHA256,
            "parent_branch_run_id":branch_id,
            "parent_terminal_accuracy_run_id":accuracy_id,
            "summary":{
                "fuse_visual_candidates":len(output),
                "rating_visual_candidates":sum(bool(f["rating_candidate"]) for f in output),
                "main_paths":len(output),
                "visual_branch_candidates":branch_count,
                "off_page_continuations":continuations,
                "terminal_positions_reviewed_or_proposed":terminal_count,
                "disputed_terminal_positions":len(review_queue),
                "visually_reviewed_disputed_terminals":reviews_done,
                "disputed_terminals_remaining_visual_review":len(review_queue)-reviews_done,
                "older_stages_rerun":0,"electrically_verified_connections":0,
                "mvp_mode":("assisted_visual_review_ready" if reviews_done==len(review_queue)
                            else "assisted_visual_review_with_open_items"),
                "diagnostic_ready":False,
                "feature_gates":flags
            },
            "circuits":output,"review_queue":review_queue,
            "limitations":[
                "Only the exact source-locked Suzuki SX4 Junction Block sample is supported by these six-fuse layout anchors.",
                "Circuits/branches are geometric hypotheses. No electrical continuity or connector pinout has been verified.",
                "Manual visual corrections override a disputed OCR number only as a visual review; no diagnostic accuracy claim.",
                "Experimental circle border removal crops are for human inspection and can erase strokes; they are NOT independent OCR.",
                "No fault diagnosis, power-flow direction, other-car generalization, or safety-critical repair advice is supported."
            ]
        }

def snapshot(dbpath,diagram_id,image_path=None):
    report=assemble(dbpath,diagram_id,image_path=image_path,with_previews=False)
    fingerprint=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        row=db.execute("SELECT id FROM mvp_snapshots_v0322 WHERE diagram_id=? AND snapshot_fingerprint=?",
                       (diagram_id,fingerprint)).fetchone()
        if row:return {"snapshot_id":row["id"],"cache_hit":True,
                      "summary":report["summary"],"older_stages_rerun":0}
        rid=uuid.uuid4().hex
        db.execute("""INSERT OR IGNORE INTO mvp_snapshots_v0322
          (id,diagram_id,branch_run_id,accuracy_run_id,snapshot_fingerprint,report_json)
          VALUES(?,?,?,?,?,?)""",
          (rid,diagram_id,report["parent_branch_run_id"],
           report["parent_terminal_accuracy_run_id"],fingerprint,
           json.dumps(report,ensure_ascii=False)))
        db.commit()
        return {"snapshot_id":rid,"cache_hit":False,"summary":report["summary"],
                "older_stages_rerun":0}

def snapshots(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        return _as_dicts(db,"""SELECT id,created_at,branch_run_id,accuracy_run_id,
                          snapshot_fingerprint FROM mvp_snapshots_v0322
                          WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 20""",
                         (diagram_id,))

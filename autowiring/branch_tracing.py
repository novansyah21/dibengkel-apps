"""AutoWiring v0.3.20 — branch-aware, source-locked VISUAL circuit hypotheses.

This module does not rebuild any legacy analysis stage. It reuses v0.3.19
components, OCR circle candidates and junctions; only the two uncovered fuse
rows, their ratings and previously unread endpoint circles receive new analysis.

IMPORTANT: line ink, filled dots, and OCR are diagram evidence, never a
confirmed electrical connection, vehicle pinout, or circuit direction.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

from autowiring.trace_review import newest_id, measure_shape
from autowiring.trace_corrected import (
    detect_junction_dots, targeted_unread_circle_ocr, visually_locate_column,
    _check_source_image,
)
from autowiring.trace_enhanced import crop_rating_evidence

SCHEMA = """
CREATE TABLE IF NOT EXISTS branch_runs_v0320(
 id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,corrected_run_id TEXT NOT NULL,
 input_fingerprint TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,UNIQUE(diagram_id,input_fingerprint)
);
CREATE TABLE IF NOT EXISTS branch_items_v0320(
 id TEXT PRIMARY KEY,run_id TEXT NOT NULL,fuse_label TEXT NOT NULL,
 source_kind TEXT NOT NULL,component_id TEXT,
 rating_text TEXT,rating_status TEXT NOT NULL,
 geometry_json TEXT NOT NULL,main_path_json TEXT NOT NULL,
 branches_json TEXT NOT NULL,evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS branch_reviews_v0320(
 diagram_id TEXT NOT NULL,branch_key TEXT NOT NULL,
 visual_status TEXT NOT NULL,visual_terminal_text TEXT,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(diagram_id,branch_key)
);
CREATE INDEX IF NOT EXISTS idx_branch_items_v0320 ON branch_items_v0320(run_id);
"""
VERSION="v0320.1"
# This source diagram is user-provided and visually inspected. Layout anchors
# only apply when its exact SHA256 and dimensions match; NEVER reuse these
# anchor rows against other vehicles, wiring diagrams or image revisions.
JUNCTION_IMAGE_SHA256="c9954639ad0fb133cedbe6591fd75325b6517a06239f51b3069c285d2972fde5"
JUNCTION_SIZE=(1136,1598)
FUSE_ROW_ANCHORS=(
    ("IG COIL",248),("MTR",372),("A/B",453),
    ("IG1 SIG",842),("ABS",951),("BACK",1051),
)
NUM_RE=re.compile(r"^(?:[1-9]|[1-3][0-9])$")

def _dark(gray,x,y,cutoff=145):
    return 0<=x<gray.width and 0<=y<gray.height and gray.getpixel((x,y))<cutoff

def _has_vertical(gray,x,y):
    return any(_dark(gray,x+dx,y) for dx in (-1,0,1))

def _row_ink(gray,x0,x1,y):
    """High coverage on thin single-pixel horizontal strokes only (local test)."""
    a=max(0,round(x0));b=min(gray.width,round(x1))
    if b<=a:return 0.
    return round(sum(any(_dark(gray,x,y+dy) for dy in (-1,0,1))
                     for x in range(a,b))/(b-a),4)

def verify_source_layout(gray,image_hash):
    """No portable '6 fuse' detection is claimed. This is a strict diagram profile."""
    return bool(gray and gray.size==JUNCTION_SIZE and image_hash==JUNCTION_IMAGE_SHA256)

def find_row(gray,seed_y,anchor=(230,270),radius=3):
    scored=[]
    for y in range(seed_y-radius,seed_y+radius+1):
        a=_row_ink(gray,*anchor,y)
        b=_row_ink(gray,445,510,y)
        scored.append((round(a*.7+b*.3,4),y))
    value,row=max(scored,key=lambda p:(p[0],-abs(p[1]-seed_y)))
    return row,value

def _circle_near_row(circles,y_px,w,h,min_x_px=620,start_x=None,exclude_ids=()):
    ranked=[]
    for c in circles:
        if c["id"] in exclude_ids:continue
        px=c["x"]*w;py=c["y"]*h
        if px<min_x_px or abs(py-y_px)>15:continue
        if start_x is not None and px<=start_x+35:continue
        ranked.append((abs(py-y_px),-px,c))
    ranked.sort(key=lambda z:(z[0],z[1]))
    return ranked[0][2] if ranked else None

def _primary_terminal(corrected_item,circles,y_px,gray):
    """Prefer the already saved v0.3.19 terminal evidence; no OCR reread."""
    old=corrected_item.get("terminal_evidence",{}) if corrected_item else {}
    cached=old.get("best_geometric_candidate")
    if cached:
        return dict(id=cached["circle_id"],x=cached["x"],y=cached["y"],
                    r=.007,ocr_text=cached["number"],
                    ocr_confidence=cached["ocr_confidence"])
    return _circle_near_row(circles,y_px,*gray.size)

def _terminal_result(circle,gray,diagram_id,known_terminal=None,reader=None,focus_cache=None):
    if circle is None:
        return {"status":"no_existing_circle_on_path_row","number":None,
                "manual_visual_review_required":True,"connector_hint":None,
                "electrically_verified":False}
    circle=dict(circle)
    number=str(circle.get("ocr_text") or "").strip()
    confidence=float(circle.get("ocr_confidence") or 0.)
    ocr_report={"status":"reused_cached_circle_ocr","attempts":[]}
    if known_terminal and not number:
        number=str(known_terminal["number"]);confidence=float(known_terminal["ocr_confidence"])
        ocr_report={"status":"reused_corrected_v0319_ocr","attempts":[]}
    if not (NUM_RE.fullmatch(number) and confidence>=.60):
        key=circle["id"]
        if focus_cache is not None and key in focus_cache:
            new,ocr_report=focus_cache[key]
        else:
            # Only one already-detected UNREAD circle is OCR'd. This is not
            # whole-image OCR, circle detection or any legacy processing stage.
            cx=circle["x"];cy=circle["y"]
            new,ocr_report=targeted_unread_circle_ocr(
                gray,[cx-.008,cy],[circle],reader)
            if focus_cache is not None:focus_cache[key]=(new,ocr_report)
        if new and NUM_RE.fullmatch(str(new.get("ocr_text"))) and float(new.get("ocr_confidence") or 0)>=.60:
            number=str(new["ocr_text"]);confidence=float(new["ocr_confidence"])
        else:number=None
    column=visually_locate_column(diagram_id,circle,gray.size)
    return {"status":("cached_or_focused_ocr_geometric_candidate_unverified" if number else
                       "circle_present_number_unresolved"),
            "number":number,"circle_id":circle["id"],
            "center":[round(circle["x"],6),round(circle["y"],6)],
            "ocr_confidence":round(confidence,3) if number else None,
            "ocr_evidence":ocr_report,
            "connector_hint":column,"manual_visual_review_required":True,
            "electrically_verified":False,"connector_pinout_verified":False}

def _continuation_candidate(circles,x,y,gray):
    """A bottom-of-page boxed 1 is an off-page continuation, NOT a connector."""
    if y < gray.height*.72:return None
    matches=sorted((math.hypot(c["x"]*gray.width-x,c["y"]*gray.height-y),c)
                   for c in circles if c.get("ocr_text") and
                   abs(c["x"]*gray.width-x)<25 and
                   -10<(c["y"]*gray.height-y)<35)
    if not matches or matches[0][0]>34:return None
    circle=matches[0][1]
    return {"kind":"off_page_continuation_candidate","marker_text":circle["ocr_text"],
            "marker_center":[round(circle["x"],6),round(circle["y"],6)],
            "reason":"bottom-page boxed symbol; not a connector terminal",
            "electrically_verified":False}

def inspect_vertical_branch(gray,dot,source_circles,reader=None,focus_cache=None,
                            diagram_id="junction_block",max_distance=1100):
    """Follow original pixels perpendicular to the saved horizontal main wire.

    Vertical intersections with other horizontal wires are NOT treated as
    branches unless a visible end/corner or filled junction is present.
    """
    x=round(dot["x"]*gray.width);y=round(dot["y"]*gray.height)
    options=[]
    for sign in (-1,1):
        if not _has_vertical(gray,x,y+sign*12):continue
        last=y;gaps=0;arms=[];crossings=[]
        for dist in range(10,min(max_distance,gray.height-y-2 if sign>0 else y-2)):
            yy=y+sign*dist
            if _has_vertical(gray,x,yy):
                last=yy;gaps=0
            else:
                gaps+=1
                if gaps>4:break
            if dist<23 or dist%2:continue
            right_ink=_row_ink(gray,x+12,x+75,yy)
            if right_ink>=.82:arms.append((right_ink,yy))
        travel=abs(last-y)
        if travel<24:continue
        endpoint_candidates=[r for r in arms if abs(r[1]-last)<=7]
        if endpoint_candidates:
            _,turn_y=max(endpoint_candidates,key=lambda z:(z[0],-abs(z[1]-last)))
            circle=_circle_near_row(source_circles,turn_y,gray.width,gray.height,
                                    min_x_px=x+70,start_x=x)
            target=_terminal_result(circle,gray,diagram_id,reader=reader,
                                    focus_cache=focus_cache)
            far_x=(circle["x"]*gray.width if circle else x+75)
            coverage=_row_ink(gray,x+12,max(x+13,far_x-(circle.get("r",.008)*1598 if circle else 0)-5),turn_y)
            if coverage<.68:
                status="weak_horizontal_pixel_support_manual_review"
            else:
                status="corner_and_horizontal_ink_candidate_unverified"
            options.append({
                "kind":"orthogonal_branch","status":status,
                "side":"up" if sign<0 else "down",
                "pixel_points":[[x,y],[x,turn_y],[round(far_x),turn_y]],
                "points":[[round(x/gray.width,6),round(y/gray.height,6)],
                          [round(x/gray.width,6),round(turn_y/gray.height,6)],
                          [round(far_x/gray.width,6),round(turn_y/gray.height,6)]],
                "horizontal_ink_coverage":coverage,
                "terminal":target,"junction":dot,"electrically_verified":False,
                "geometry_note":"Unique drawn vertical corner to horizontal arm; crossings without dots ignored."})
        else:
            marker=_continuation_candidate(source_circles,x,last,gray)
            if marker:
                options.append({
                    "kind":"off_page_continuation","status":"bottom_continuation_visual_candidate",
                    "side":"down" if sign>0 else "up",
                    "pixel_points":[[x,y],[x,last]],
                    "points":[[round(x/gray.width,6),round(y/gray.height,6)],
                              [round(x/gray.width,6),round(last/gray.height,6)]],
                    "continuation":marker,"terminal":None,
                    "junction":dot,"electrically_verified":False,
                    "geometry_note":"Continue marker is not a connector pin; crossings without dots ignored."})
    return options

def _main_path(gray,y,circle,fuse_label,rating,source_kind):
    start=round(.18573943662*gray.width)
    far=round(circle["x"]*gray.width) if circle else round(.63*gray.width)
    if far<=start:return None
    reach=max(start+12,far-(round(float(circle.get("r") or .007)*1598)+4 if circle else 2))
    coverage=_row_ink(gray,start+17,reach,y)
    return {"kind":"horizontal_main_path","fuse":fuse_label,
            "status":"pixel_supported_geometric_hypothesis" if coverage>=.72 else "weak_ink_support_requires_review",
            "pixel_points":[[start,y],[far,y]],
            "points":[[round(start/gray.width,6),round(y/gray.height,6)],
                      [round(far/gray.width,6),round(y/gray.height,6)]],
            "horizontal_ink_coverage":coverage,
            "electrically_verified":False,"rating_candidate":rating,"source_kind":source_kind}

def _dot_candidates(gray,row,old,main):
    prior=old.get("junction_dots",[]) if old else []
    if prior:return prior
    if not main:return []
    # New fuse rows only. This is an original-pixel check, NOT a repeat
    # of earlier OCR/segmentation/whole-diagram analysis.
    return detect_junction_dots(gray,{"points":main["points"]},"junction_block")

def _review_key(fuse_label,branch):
    bits=(fuse_label,branch["kind"],branch.get("side"),tuple(tuple(p) for p in branch["pixel_points"]))
    return hashlib.sha256(repr(bits).encode()).hexdigest()[:24]

def build(dbpath,diagram_id,image_path,reader=None,rating_reader=None):
    """Read all v0.3.19 evidence without mutating it. Cache by exact inputs."""
    image_path=Path(image_path)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        corrected_id=newest_id(db,"corrected_runs_v0319",diagram_id)
        if not corrected_id:
            raise ValueError("Hasil v0.3.19 belum tersedia. Pertahankan output/autowiring.db lama; tahapan sebelumnya TIDAK dijalankan ulang.")
        corrected_run=db.execute("SELECT * FROM corrected_runs_v0319 WHERE id=?",(corrected_id,)).fetchone()
        if corrected_run["enhanced_run_id"]!=newest_id(db,"enhanced_runs_v0318",diagram_id):
            raise ValueError("Hasil v0.3.19 sudah stale; tahapan lama tidak diulang otomatis.")
        source_hash=_check_source_image(db,diagram_id,image_path)
        if not image_path.is_file():raise ValueError("Gambar asli tidak ditemukan; restore sample_assets, jangan proses ulang database.")
        try:
            from PIL import Image
            with Image.open(image_path) as src:gray=src.convert("L")
        except (ImportError,OSError) as exc:raise ValueError("Pillow dan gambar sumber diperlukan") from exc
        if not verify_source_layout(gray,source_hash):
            raise ValueError("Source-specific 6-fuse profile unavailable for this image. No diagram applicability/pinout guessed.")
        independent_id=newest_id(db,"independent_runs_v039",diagram_id)
        fingerprint=hashlib.sha256(json.dumps({
            "version":VERSION,"diagram_id":diagram_id,"corrected_run_id":corrected_id,
            "image_sha256":source_hash,"independent_run_id":independent_id,
        },sort_keys=True).encode()).hexdigest()
        existing=db.execute("SELECT id,summary_json FROM branch_runs_v0320 WHERE diagram_id=? AND input_fingerprint=?",
                            (diagram_id,fingerprint)).fetchone()
        if existing:
            return dict(json.loads(existing["summary_json"]),run_id=existing["id"],cache_hit=True)
        old={}
        for item in db.execute("SELECT * FROM corrected_items_v0319 WHERE run_id=?",(corrected_id,)):
            e=dict(item)
            e["terminal_evidence"]=json.loads(e["terminal_evidence_json"])
            e["junction_dots"]=json.loads(e["junction_evidence_json"])
            old[e["fuse_label"]]=e
        circles=[dict(e) for e in db.execute("SELECT * FROM independent_circles_v039 WHERE run_id=?",
                   (independent_id,))] if independent_id else []
        # Previous ABS targeted-read terminal 9 is preferred over unread old circle.
        rows=[];dot_total=branch_total=terminal_leads=ratings=extra_ocr=0
        focus_cache={};rating_ocr_calls=0
        for label,seed_y in FUSE_ROW_ANCHORS:
            row,strength=find_row(gray,seed_y)
            old_item=old.get(label)
            if old_item:
                source_kind="reused_v0319_component"
                rating=old_item["rating_text"]
                rating_status=old_item["rating_status"]
                rating_evidence={"source":"reused_v0319","new_ocr_attempts":0}
                component_id=old_item["component_id"]
            else:
                source_kind="source_locked_fuse_layout_candidate"
                component_id=None
                # Only the two new rows are assessed, never all six again.
                gap={"neighbor_x":.18573943662,"endpoint_y":row/gray.height,"neighbor_y":row/gray.height}
                rating,rating_status,hits,crops,attempts=crop_rating_evidence(gray,gap,reader=rating_reader)
                rating_evidence={"source":"new_fuse_only_targeted_ocr","hits":hits,
                                 "crop_provenance":[{"roi":c["roi"],"box":c["pixel_box"],
                                    "attempts":c["attempts"]} for c in crops],
                                 "new_ocr_attempts":attempts}
                rating_ocr_calls+=attempts
            circle=_primary_terminal(old_item,circles,row,gray)
            known=(old_item.get("terminal_evidence",{}).get("best_geometric_candidate") if old_item else None)
            term=_terminal_result(circle,gray,diagram_id,known_terminal=known,
                                  reader=reader,focus_cache=focus_cache)
            main=_main_path(gray,row,circle,label,rating,source_kind)
            dots=_dot_candidates(gray,row,old_item,main) if main else []
            branches=[]
            for dot in dots:
                for b in inspect_vertical_branch(gray,dot,circles,reader=reader,
                                                 focus_cache=focus_cache,diagram_id=diagram_id):
                    b["branch_key"]=_review_key(label,b)
                    branches.append(b)
            dot_total+=len(dots);branch_total+=len(branches)
            ratings+=bool(rating)
            terminal_leads+=bool(term.get("number"))
            terminal_leads+=sum(bool((b.get("terminal") or {}).get("number")) for b in branches)
            geom={"image_sha256":source_hash,"fuse_y_px":row,
                  "seed_y_px":seed_y,"line_anchor_strength":strength,
                  "waveform":{"status":"reused_v0319" if old_item else
                              measure_shape(gray,{"endpoint_x":.128,"neighbor_x":.18573943662,
                                  "endpoint_y":row/gray.height,"neighbor_y":row/gray.height})[0]},
                  "junctions":dots,"layout_guide":"source-image-locked visual anchors only",
                  "confirmed_electrical_connections":0}
            evidence={"primary_terminal":term,"rating":rating_evidence,
                      "warning":"All labels, joins, dots and connector columns are visual hypotheses.",
                      "source_reference":"user-provided Junction Block image (not generic auto pinout)"}
            rows.append((uuid.uuid4().hex,label,source_kind,component_id,rating,
                         rating_status,json.dumps(geom),json.dumps(main),
                         json.dumps(branches),json.dumps(evidence)))
        extra_ocr=sum(len(v[1].get("attempts",[])) for v in focus_cache.values())
        summary={"fuse_candidates_total":len(rows),
                 "reused_fuses_from_v0319":sum(r[2]=="reused_v0319_component" for r in rows),
                 "new_source_locked_fuse_candidates":sum(r[2]=="source_locked_fuse_layout_candidate" for r in rows),
                 "rating_candidates_total":ratings,
                 "visual_junctions":dot_total,"branch_path_hypotheses":branch_total,
                 "geometric_terminal_ocr_leads":terminal_leads,
                 "new_targeted_rating_ocr_attempts":rating_ocr_calls,
                 "new_targeted_circle_ocr_attempts":extra_ocr,
                 "older_stages_rerun":0,"electrically_verified_connections":0,
                 "warning":"Source-locked sample analysis only. Branches and terminal OCR never establish electrical continuity."}
        rid=uuid.uuid4().hex
        db.execute("INSERT INTO branch_runs_v0320(id,diagram_id,corrected_run_id,input_fingerprint,summary_json) VALUES(?,?,?,?,?)",
                   (rid,diagram_id,corrected_id,fingerprint,json.dumps(summary)))
        db.executemany("INSERT INTO branch_items_v0320(id,run_id,fuse_label,source_kind,component_id,rating_text,rating_status,geometry_json,main_path_json,branches_json,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       [(r[0],rid,*r[1:]) for r in rows])
        db.commit()
        return dict(summary,run_id=rid,cache_hit=False)

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        run=db.execute("SELECT * FROM branch_runs_v0320 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                       (diagram_id,)).fetchone()
        if not run:return {"run":None,"items":[]}
        if run["corrected_run_id"]!=newest_id(db,"corrected_runs_v0319",diagram_id):
            return {"run":None,"items":[],"stale":True}
        reviews={r["branch_key"]:dict(r) for r in db.execute(
            "SELECT * FROM branch_reviews_v0320 WHERE diagram_id=?",(diagram_id,))}
        items=[]
        for row in db.execute("SELECT * FROM branch_items_v0320 WHERE run_id=? ORDER BY fuse_label",(run["id"],)):
            item=dict(row)
            for key,new in (("geometry_json","geometry"),("main_path_json","main_path"),
                            ("branches_json","branches"),("evidence_json","evidence")):
                item[new]=json.loads(item.pop(key))
            for b in item["branches"]:
                review=reviews.get(b["branch_key"])
                b["visual_review"]=review["visual_status"] if review else "needs_review"
                b["visual_terminal_text"]=review["visual_terminal_text"] if review else None
                b["electrically_verified"]=False
            item["electrically_verified"]=False
            items.append(item)
        return {"run":dict(id=run["id"],**json.loads(run["summary_json"])),"items":items}

def save_visual_review(dbpath,diagram_id,branch_key,visual_status,visual_terminal_text=None):
    if visual_status not in ("needs_review","visually_matches_source","rejected_visual_path"):
        raise ValueError("Invalid visual review status")
    if visual_terminal_text not in (None,"") and not re.fullmatch(r"(?:[1-9]|[1-3][0-9])",str(visual_terminal_text)):
        raise ValueError("Visual terminal label must be a 1-39 number or blank")
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        row=db.execute("""
          SELECT 1 FROM branch_items_v0320 i JOIN branch_runs_v0320 r ON r.id=i.run_id
          WHERE r.diagram_id=? ORDER BY r.created_at DESC,r.rowid DESC LIMIT 1""",(diagram_id,)).fetchone()
        if not row:raise ValueError("No branch run for this diagram")
        valid=False
        for r in db.execute("""
          SELECT i.branches_json FROM branch_items_v0320 i
          JOIN branch_runs_v0320 br ON br.id=i.run_id
          WHERE br.diagram_id=? AND br.id=(
            SELECT id FROM branch_runs_v0320 WHERE diagram_id=?
            ORDER BY created_at DESC,rowid DESC LIMIT 1)""",(diagram_id,diagram_id)):
            if any(b.get("branch_key")==branch_key for b in json.loads(r["branches_json"])):
                valid=True;break
        if not valid:raise ValueError("Branch key not found in current analysis")
        db.execute("""
          INSERT INTO branch_reviews_v0320(diagram_id,branch_key,visual_status,visual_terminal_text)
          VALUES(?,?,?,?)
          ON CONFLICT(diagram_id,branch_key) DO UPDATE SET
          visual_status=excluded.visual_status,
          visual_terminal_text=excluded.visual_terminal_text,
          updated_at=CURRENT_TIMESTAMP""",
          (diagram_id,branch_key,visual_status,visual_terminal_text or None))
        db.commit()
    return {"branch_key":branch_key,"visual_status":visual_status,
            "visual_terminal_text":visual_terminal_text or None,
            "electrically_verified":False}

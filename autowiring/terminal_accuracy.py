"""v0.3.21: source-bounded, incremental terminal numeral review.

Only four problematic terminal CIRCLES from persisted v0.3.20 are processed.
This never reruns legacy fuse/circle detection/graph/trace/whole-image OCR.
Visual reference labels from one explicitly source-locked, human-inspected
diagram are retained as independent review clues, NEVER disguised as OCR.
All electrical connections and connector pinouts remain UNVERIFIED.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import uuid

from autowiring.trace_review import newest_id
from autowiring.branch_tracing import JUNCTION_IMAGE_SHA256, JUNCTION_SIZE

VERSION="v0321.1"
SCHEMA="""
CREATE TABLE IF NOT EXISTS terminal_accuracy_runs_v0321(
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 parent_run_id TEXT NOT NULL,
 input_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,
 UNIQUE(diagram_id,input_fingerprint)
);
CREATE TABLE IF NOT EXISTS terminal_accuracy_items_v0321(
 id TEXT PRIMARY KEY,run_id TEXT NOT NULL,
 fuse_label TEXT NOT NULL,path_kind TEXT NOT NULL,
 path_key TEXT NOT NULL,circle_id TEXT NOT NULL,
 prior_ocr_number TEXT,prior_ocr_confidence REAL,
 new_ocr_number TEXT,new_ocr_confidence REAL,
 ocr_status TEXT NOT NULL,reference_number TEXT NOT NULL,
 reference_origin TEXT NOT NULL,evidence_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_terminal_accuracy_items_v0321
 ON terminal_accuracy_items_v0321(run_id);
CREATE TABLE IF NOT EXISTS terminal_accuracy_reviews_v0321(
 diagram_id TEXT NOT NULL,path_key TEXT NOT NULL,
 review_status TEXT NOT NULL,manual_number TEXT,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(diagram_id,path_key)
);
"""
# These ARE NOT machine labels or electrical pinouts. Source-locked visual
# transcription of four circled digits on the exact attached 1136x1598 image.
# They serve as a comparison/reference for the new OCR and can be corrected
# via explicit user review. Never apply to any other image SHA or size.
VISUAL_REFERENCE={
    ("IG1 SIG","main"):{"number":"12","header":"E325"},
    ("IG1 SIG","branch"):{"number":"16","header":"G272"},
    ("ABS","branch"):{"number":"6","header":"L315"},
    ("BACK","branch"):{"number":"8","header":"G272"},
}
NUMBER=re.compile(r"^(?:[1-9]|[1-3][0-9])$")

def normalized_number(value):
    raw=str(value or "").strip()
    return raw if NUMBER.fullmatch(raw) else None

def _image_source(path):
    from PIL import Image
    path=Path(path)
    if not path.is_file():raise ValueError(
        "Gambar sumber tidak ditemukan. Kembalikan sample_assets lama, jangan jalankan ulang analisis sebelumnya.")
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as original:im=original.convert("L")
    if sha!=JUNCTION_IMAGE_SHA256 or im.size!=JUNCTION_SIZE:
        raise ValueError("Diagram sumber berbeda dari v0.3.20; referensi visual khusus gambar ini tidak berlaku.")
    return im,sha

def _ocr_words(image,psm,reader=None):
    if reader is not None:
        return reader(image,psm)
    from pytesseract import Output,image_to_data
    result=image_to_data(image,output_type=Output.DICT,
                          config=f"--psm {psm} -c tessedit_char_whitelist=0123456789")
    out=[]
    for token,conf in zip(result.get("text",[]),result.get("conf",[])):
        try:score=float(conf)/100
        except (ValueError,TypeError):score=0
        out.append((str(token).strip(),score))
    return out

def _roi(gray,circle):
    """Crop glyph interior, excluding as much circular border/lead as possible."""
    from PIL import ImageOps,ImageEnhance,Image
    w,h=gray.size
    x=round(float(circle["x"])*w)
    y=round(float(circle["y"])*h)
    radius=max(6,round(float(circle.get("r") or .007)*max(w,h)))
    crops=[]
    for name,x_scale,y_scale,mode,psm in (
        ("tight_clean",.60,.64,"clean",8),
        ("medium_contrast",.79,.72,"contrast",13),
        ("tight_binary",.64,.69,"binary",7),
    ):
        hx=max(5,round(radius*x_scale))
        hy=max(5,round(radius*y_scale))
        box=(max(0,x-hx),max(0,y-hy),min(w,x+hx+1),min(h,y+hy+1))
        raw=gray.crop(box)
        if mode=="contrast":
            clean=ImageOps.autocontrast(raw)
        elif mode=="binary":
            clean=ImageOps.autocontrast(raw).point(lambda p:0 if p<155 else 255)
        else:
            clean=ImageEnhance.Contrast(ImageOps.autocontrast(raw)).enhance(1.8)
        # Add whitespace around the glyph so Tesseract does not treat fragments
        # or the clipped circle border as a single joined graphic.
        blown=clean.resize((clean.width*8,clean.height*8),Image.Resampling.NEAREST)
        padded=Image.new("L",(blown.width+32,blown.height+32),255)
        padded.paste(blown,(16,16))
        buff=io.BytesIO()
        raw.save(buff,format="PNG")
        crops.append((padded,psm,{
            "variant":name,"pixel_box":list(box),
            "original_crop_png_base64":base64.b64encode(buff.getvalue()).decode(),
            "raw_tokens":[],"candidates":[]}))
    return crops

def multi_scale_review(gray,circle,reader=None):
    """Three bounded NEW OCR configurations on ONE previously located circle.

    OCR confidence is NOT calibrated connectivity confidence. Do not accept an
    isolated high-confidence '2' when another variant or visual source says '8'.
    """
    if circle is None:return None,None,"circle_coordinates_missing",{"attempts":[]}
    tries=[];leads=[]
    for image,psm,info in _roi(gray,circle):
        try:
            words=_ocr_words(image,psm,reader)
            info["raw_tokens"]=[{"text":str(t)[:32],"confidence":round(float(c),3)}
                                for t,c in words if str(t).strip()][:12]
            for token,confidence in words:
                n=normalized_number(token)
                try:cf=float(confidence)
                except (ValueError,TypeError):continue
                if n and cf>=.50:
                    info["candidates"].append({"number":n,"ocr_confidence":round(cf,3)})
                    leads.append((n,cf,info["variant"]))
        except Exception as exc:
            info["error"]=type(exc).__name__
        tries.append(info)
    distinct={num for num,_,_ in leads}
    if not leads:
        return None,None,"no_confident_new_ocr",{"attempts":tries,"ocr_vote_count":0}
    if len(distinct)>1:
        return None,None,"conflicting_new_ocr_variants",{
            "attempts":tries,"ocr_vote_count":len(leads),"numbers":sorted(distinct)}
    chosen=next(iter(distinct))
    by_variant={variant for num,_,variant in leads if num==chosen}
    if len(by_variant)<2:
        return None,None,"single_variant_ocr_not_enough",{
            "attempts":tries,"ocr_vote_count":len(leads),"single_candidate":chosen}
    # This is an OCR vote count, not evidence that wires are electrically joined.
    return chosen,round(max(cf for _,cf,_ in leads),3),"multi_variant_ocr_lead_unverified",{
        "attempts":tries,"ocr_vote_count":len(leads),
        "agreeing_variants":sorted(by_variant)}

def _targets(parent_items):
    """Exactly four problem circles; neither re-OCRs healthy terminals nor
    applies visual numbers by generic label matching.
    """
    by_name={i["fuse_label"]:i for i in parent_items}
    targets=[]
    for (fuse,kind),reference in VISUAL_REFERENCE.items():
        item=by_name.get(fuse)
        if item is None:raise ValueError("Missing saved fuse "+fuse+" in v0.3.20. No older stage was rerun.")
        if kind=="main":
            terminal=item["evidence"].get("primary_terminal") or {}
            path_key="main:"+fuse
        else:
            branch=[b for b in item["branches"]
                    if b.get("kind")=="orthogonal_branch"
                    and b.get("terminal",{}).get("circle_id")]
            if len(branch)!=1:
                raise ValueError("Expected exactly one saved orthogonal branch on "+fuse)
            terminal=branch[0]["terminal"]
            path_key=str(branch[0]["branch_key"])
        circle_id=terminal.get("circle_id")
        if not circle_id:raise ValueError("Saved terminal circle missing on "+fuse+" "+kind)
        targets.append({"fuse":fuse,"kind":kind,"key":path_key,
                        "circle_id":circle_id,
                        "old_number":normalized_number(terminal.get("number")),
                        "old_confidence":terminal.get("ocr_confidence"),
                        "reference":reference})
    return targets

def build(dbpath,diagram_id,image_path,reader=None):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        parent_id=newest_id(db,"branch_runs_v0320",diagram_id)
        if not parent_id:raise ValueError(
            "Hasil v0.3.20 tidak ditemukan. Gunakan output/autowiring.db yang sama; tidak perlu ulang tahap lama.")
        parent=db.execute("SELECT * FROM branch_runs_v0320 WHERE id=?",(parent_id,)).fetchone()
        if parent["corrected_run_id"]!=newest_id(db,"corrected_runs_v0319",diagram_id):
            raise ValueError("Hasil v0.3.20 stale terhadap v0.3.19; tahap lama tidak diulang otomatis.")
        gray,sha=_image_source(image_path)
        fingerprint=hashlib.sha256(json.dumps({
            "version":VERSION,"parent":parent_id,"source_sha256":sha
        },sort_keys=True).encode()).hexdigest()
        cached=db.execute("SELECT id,summary_json FROM terminal_accuracy_runs_v0321 WHERE diagram_id=? AND input_fingerprint=?",
                          (diagram_id,fingerprint)).fetchone()
        if cached:
            return dict(json.loads(cached["summary_json"]),run_id=cached["id"],
                        cache_hit=True,new_ocr_attempts=0,older_stages_rerun=0)
        items=[]
        for row in db.execute("SELECT * FROM branch_items_v0320 WHERE run_id=?",(parent_id,)):
            item=dict(row)
            item["branches"]=json.loads(item["branches_json"])
            item["evidence"]=json.loads(item["evidence_json"])
            items.append(item)
        targets=_targets(items)
        circle_ids=[t["circle_id"] for t in targets]
        # Earlier independent OCR run may contain multiple historical instances
        # of the same circle IDs; use exact source center returned in v0.3.20.
        circle_records=[]
        with sqlite3.connect(dbpath) as source:
            source.row_factory=sqlite3.Row
            for cid in circle_ids:
                row=source.execute(
                    "SELECT id,x,y,r FROM independent_circles_v039 WHERE id=?",(cid,)).fetchone()
                if not row:raise ValueError("Saved circle coordinates not found: "+cid)
                circle_records.append(dict(row))
        run_id=uuid.uuid4().hex;rows=[]
        new_counts=0;matching=0;conflict=0;unresolved=0
        for t,circle in zip(targets,circle_records):
            number,confidence,status,evidence=multi_scale_review(gray,circle,reader)
            new_counts+=len(evidence.get("attempts",[]))
            ref=t["reference"]["number"]
            if number is None:
                outcome="unresolved_ocr_visual_reference_available"
                unresolved+=1
            elif number!=ref:
                outcome="new_ocr_conflicts_with_source_visual_reference"
                conflict+=1
            else:
                outcome="ocr_matches_independent_visual_reference_review_required"
                matching+=1
            if t["old_number"] and t["old_number"]!=ref:
                evidence["previous_ocr_conflict"]={
                    "raw":t["old_number"],"ocr_confidence":t["old_confidence"],
                    "human_transcribed_visual_reference":ref}
            evidence["circle_center"]=[round(float(circle["x"]),7),round(float(circle["y"]),7)]
            evidence["comparison_status"]=outcome
            evidence["electrically_verified"]=False
            rows.append((uuid.uuid4().hex,run_id,t["fuse"],t["kind"],t["key"],
                         t["circle_id"],t["old_number"],t["old_confidence"],
                         number,confidence,status,ref,
                         "visual_transcription_exact_source_not_machine_ocr",
                         json.dumps(evidence)))
        summary={
            "source_image_sha256":sha,"reused_v0320_run":parent_id,
            "targeted_problem_circles":len(rows),
            "new_ocr_attempts":new_counts,
            "new_ocr_agreed_with_visual_reference":matching,
            "new_ocr_conflicts_with_reference":conflict,
            "unresolved_ocr_targets":unresolved,
            "older_stages_rerun":0,"electrically_verified_connections":0,
            "warning":"OCR/ref numbers are visual evidence only; no electrical or connector pinout verification. Visual source references are explicitly human-transcribed."}
        db.execute("INSERT INTO terminal_accuracy_runs_v0321(id,diagram_id,parent_run_id,input_fingerprint,summary_json) VALUES(?,?,?,?,?)",
                   (run_id,diagram_id,parent_id,fingerprint,json.dumps(summary)))
        db.executemany("""
            INSERT INTO terminal_accuracy_items_v0321
            (id,run_id,fuse_label,path_kind,path_key,circle_id,prior_ocr_number,
             prior_ocr_confidence,new_ocr_number,new_ocr_confidence,
             ocr_status,reference_number,reference_origin,evidence_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",rows)
        db.commit()
        return dict(summary,run_id=run_id,cache_hit=False)

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        run=db.execute("SELECT * FROM terminal_accuracy_runs_v0321 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                       (diagram_id,)).fetchone()
        if not run:return {"run":None,"items":[]}
        if run["parent_run_id"]!=newest_id(db,"branch_runs_v0320",diagram_id):
            return {"run":None,"items":[],"stale":True}
        reviews={r["path_key"]:dict(r) for r in db.execute(
            "SELECT * FROM terminal_accuracy_reviews_v0321 WHERE diagram_id=?",(diagram_id,))}
        rows=[]
        for row in db.execute(
            "SELECT * FROM terminal_accuracy_items_v0321 WHERE run_id=? ORDER BY fuse_label,path_kind",
            (run["id"],)):
            item=dict(row);item["evidence"]=json.loads(item.pop("evidence_json"))
            review=reviews.get(item["path_key"])
            item["visual_review"]=review["review_status"] if review else "needs_review"
            item["manual_number"]=review["manual_number"] if review else None
            item["display_number"]=item["manual_number"] or item["new_ocr_number"]
            item["electrically_verified"]=False
            rows.append(item)
        return {"run":dict(id=run["id"],**json.loads(run["summary_json"])),"items":rows}

def review(dbpath,diagram_id,path_key,status,manual_number=None):
    if status not in ("needs_review","visually_confirmed","rejected_ocr"):
        raise ValueError("Invalid visual review status")
    number=normalized_number(manual_number)
    if manual_number not in (None,"") and not number:raise ValueError(
        "Manual terminal number must be between 1 and 39, or blank")
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        run_id=newest_id(db,"terminal_accuracy_runs_v0321",diagram_id)
        if not run_id or not db.execute(
            "SELECT 1 FROM terminal_accuracy_items_v0321 WHERE run_id=? AND path_key=?",
            (run_id,path_key)).fetchone():
            raise ValueError("Terminal target not in current diagram run")
        db.execute("""INSERT INTO terminal_accuracy_reviews_v0321
          (diagram_id,path_key,review_status,manual_number) VALUES(?,?,?,?)
          ON CONFLICT(diagram_id,path_key) DO UPDATE SET
          review_status=excluded.review_status,manual_number=excluded.manual_number,
          updated_at=CURRENT_TIMESTAMP""",(diagram_id,path_key,status,number))
        db.commit()
    return {"path_key":path_key,"review_status":status,
            "manual_number":number,"electrically_verified":False}

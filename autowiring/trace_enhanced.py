"""AutoWiring v0.3.18: incremental fuse-rating evidence and endpoint-based trace review.

Runs solely from existing v0.3.17 + persisted v0.3.16 and earlier geometry/OCR.
Does NOT execute image-wide OCR, circle detection, segmentation, component creation,
v0.3.17 tracing or any other prior stage. Every path and pin remains UNVERIFIED.
"""
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

from autowiring.trace_review import normalize_rating, newest_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS enhanced_runs_v0318(
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 trace_run_id TEXT NOT NULL,
 source_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,
 UNIQUE(diagram_id,source_fingerprint)
);
CREATE TABLE IF NOT EXISTS enhanced_items_v0318(
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL,
 component_id TEXT NOT NULL,
 fuse_label TEXT NOT NULL,
 rating_text TEXT,
 rating_status TEXT NOT NULL,
 rating_evidence_json TEXT NOT NULL,
 crop_evidence_json TEXT NOT NULL,
 trace_json TEXT NOT NULL,
 terminal_ranking_json TEXT NOT NULL,
 trace_status TEXT NOT NULL,
 warning TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enhanced_items_v0318 ON enhanced_items_v0318(run_id);
"""
VALID_TERMINAL = re.compile(r'^(?:[1-9]|[1-3][0-9])$')
CROP_SETTINGS = (
    # Distinct from previous v0.3.17 broad ROI. x is relative to right fuse-pin.
    ("right_compact",  .004, .047, -.016, .016),
    ("right_above",   .002, .082, -.032, .001),
    ("right_below",   .002, .082, -.002, .032),
)
PROCESSOR_VERSION="v0318.2"

def source_snapshot(db,diagram_id):
    trace_id=newest_id(db,"trace_runs_v0317",diagram_id)
    if trace_id is None:
        raise ValueError("Tidak ada hasil v0.3.17. Jangan ulang tahapan lama; pastikan memakai output/autowiring.db yang sebelumnya.")
    trace_run=db.execute("SELECT * FROM trace_runs_v0317 WHERE id=?",(trace_id,)).fetchone()
    comp_id=newest_id(db,"component_runs_v0316",diagram_id)
    if trace_run["component_run_id"]!=comp_id:
        raise ValueError("v0.3.17 tertinggal dari component run terbaru. Periksa database sebelum melanjutkan.")
    return trace_run

def _normalized_box(settings,gap,w,h):
    _,dx0,dx1,dy0,dy1=settings
    end=float(gap["neighbor_x"])
    y=(float(gap["endpoint_y"])+float(gap["neighbor_y"]))/2
    left=max(0,min(w,round((end+dx0)*w)))
    right=max(0,min(w,round((end+dx1)*w)))
    top=max(0,min(h,round((y+dy0)*h)))
    bottom=max(0,min(h,round((y+dy1)*h)))
    return left,top,right,bottom

def _make_crop(gray,settings,gap):
    from PIL import ImageOps
    w,h=gray.size
    box=_normalized_box(settings,gap,w,h)
    if box[2]-box[0]<8 or box[3]-box[1]<8:
        return None,box
    crop=ImageOps.autocontrast(gray.crop(box))
    return crop,box

def _variants(crop,settings,gap,box,full_size):
    """Original and line-cleaned variants; remove near-continuous center row,
    but not text rows. This is localized OCR only.
    """
    from PIL import ImageOps,ImageEnhance
    enlarged=ImageEnhance.Contrast(crop.resize((crop.width*4,crop.height*4))).enhance(1.5)
    variants=[("contrast",enlarged)]
    # Only suppress ink if a row is almost fully dark and near schematic wire.
    cleaned=crop.copy()
    gray_pixels=cleaned.load()
    cx=(float(gap["endpoint_y"])+float(gap["neighbor_y"]))/2*full_size[1]-box[1]
    erased=0
    for row in range(max(0,int(cx)-2),min(cleaned.height,int(cx)+3)):
        black=sum(gray_pixels[x,row]<135 for x in range(cleaned.width))
        if black/cleaned.width>=.80:
            for x in range(cleaned.width):gray_pixels[x,row]=255
            erased+=1
    if erased:
        clean=ImageOps.autocontrast(cleaned)
        variants.append(("line_suppressed",clean.resize((clean.width*4,clean.height*4))))
    return variants

def parse_rating_words(words):
    """Only literal ampere labels, not bare 10/15 or nearby connector numbers."""
    toks=[(str(t).strip(),float(conf)) for t,conf in words if str(t).strip()]
    results=[]
    for i,(word,conf) in enumerate(toks):
        candidate=normalize_rating(word)
        if candidate and conf>=.45:
            results.append(dict(rating=candidate,confidence=round(conf,3),raw=word))
        elif i+1<len(toks) and re.fullmatch(r'(?:[0-9]{1,3}|7[.,]5)',word):
            next_word,next_conf=toks[i+1]
            candidate=normalize_rating(word+next_word)
            if candidate and next_conf>=.45 and conf>=.45:
                results.append(dict(rating=candidate,confidence=round(min(conf,next_conf),3),
                                    raw=word+" "+next_word))
    return results

def _read_data(image,psm,reader):
    """reader(image, psm) for dependency-injected tests; return list of words."""
    if reader is not None:return reader(image,psm)
    import pytesseract
    from pytesseract import Output
    data=pytesseract.image_to_data(
        image,output_type=Output.DICT,
        config=f'--psm {psm} -c tessedit_char_whitelist=0123456789Aa.,')
    # Tesseract conf -1 means no confident token.
    result=[]
    for raw,conf in zip(data.get("text",[]),data.get("conf",[])):
        try:score=float(conf)/100
        except (ValueError,TypeError):score=0
        result.append((raw,score))
    return result

def crop_rating_evidence(gray,gap,reader=None,max_attempts=6):
    """Return rating *candidate* and annotated ROI previews, never confirmed rating.

    Try new, compact/above/below ROIs, stop after unique conservative reading.
    For ambiguous/conflicting readings emit no rating selection.
    """
    if gray is None or gap is None:
        return None,"image_or_gap_missing",[],[],0
    try:
        from PIL import Image
    except ImportError:
        return None,"pillow_unavailable",[],[],0
    if reader is None:
        try:import pytesseract  # noqa
        except ImportError:
            reader_unavailable=True
        else:reader_unavailable=False
    else:reader_unavailable=False
    crops=[];hits=[];attempts=0
    for settings in CROP_SETTINGS:
        crop,box=_make_crop(gray,settings,gap)
        if crop is None:continue
        stream=io.BytesIO();crop.save(stream,format="PNG")
        preview=base64.b64encode(stream.getvalue()).decode("ascii")
        evidence={"roi":settings[0],"pixel_box":list(box),
                  "box_norm":[round(box[0]/gray.width,5),round(box[1]/gray.height,5),
                              round(box[2]/gray.width,5),round(box[3]/gray.height,5)],
                  "crop_png_base64":preview,"attempts":[]}
        crops.append(evidence)
        if reader_unavailable:continue
        # 2 PSM maximum per crop; 4x upscale makes small labels readable.
        variants=_variants(crop,settings,gap,box,gray.size)
        # Two *new* OCR checks per ROI, so compact/above/below are all covered.
        # If the wire row was cleaned, use it once rather than OCRing the same
        # patch four times with nearly identical settings.
        selections=[(variants[0][0],variants[0][1],7)]
        if len(variants)>1:
            selections.append((variants[1][0],variants[1][1],8))
        else:
            selections.append((variants[0][0],variants[0][1],8))
        for variant,upscaled,psm in selections:
            if attempts>=max_attempts:break
            attempts+=1
            try:
                words=_read_data(upscaled,psm,reader)
                valid=parse_rating_words(words)
                safe_raw=[str(w[0])[:60] for w in words if str(w[0]).strip()][:16]
                evidence["attempts"].append({"variant":variant,"psm":psm,
                                              "raw_tokens":safe_raw,"candidate_ratings":valid})
                hits.extend([dict(v,roi=settings[0],variant=variant,psm=psm) for v in valid])
            except Exception as exc:
                evidence["attempts"].append({"variant":variant,"psm":psm,
                                              "error":type(exc).__name__})
        # Cross-check ROI families; contradictory ratings remain unresolved.
    unique={h["rating"] for h in hits}
    if len(unique)>1:return None,"conflicting_new_roi_ocr",hits,crops,attempts
    if len(unique)==1:return hits[0]["rating"],"new_localized_rating_candidate_unverified",hits,crops,attempts
    return None,"tesseract_unavailable" if reader_unavailable else "rating_not_read",hits,crops,attempts

def follow_endpoint_graph(target,segments,max_hops=24,tol=.0028):
    """Follow uniquely touching endpoints, INCLUDING orthogonal bends.

    At branches or at near-endpoint-to-line-interior, stop with ambiguity
    instead of implying joined wires. Pure crossings are NOT joins.
    """
    if not target:return {"points":[],"edge_ids":[],"status":"target_edge_missing","junctions":[]}
    start_id=target["id"]
    a=(float(target["x1"]),float(target["y1"]))
    b=(float(target["x2"]),float(target["y2"]))
    # Right side of fuse normally starts at lesser x; retain actual orientation.
    if a[0]>b[0]:a,b=b,a
    poly=[list(a),list(b)];visited=[start_id];at=b;junctions=[]
    pool={s["source_edge_id"]:s for s in segments if s.get("classification")=="candidate_wire"}
    def dist(p,q):return math.hypot(p[0]-q[0],p[1]-q[1])
    status="single_segment"
    for _ in range(max_hops-1):
        candidates=[];possible_t=[]
        for sid,s in pool.items():
            if sid in visited:continue
            p=(float(s["x1"]),float(s["y1"]))
            q=(float(s["x2"]),float(s["y2"]))
            d1=dist(at,p);d2=dist(at,q)
            d=min(d1,d2)
            if d<=tol:
                other=q if d1<=d2 else p
                if dist(at,other)>tol:candidates.append((d,sid,other))
            else:
                # Segment interior near endpoint: T-junction possibility, not automatic join.
                length2=(q[0]-p[0])**2+(q[1]-p[1])**2
                if length2<1e-12:continue
                f=((at[0]-p[0])*(q[0]-p[0])+(at[1]-p[1])*(q[1]-p[1]))/length2
                if .05<f<.95:
                    foot=(p[0]+f*(q[0]-p[0]),p[1]+f*(q[1]-p[1]))
                    if dist(at,foot)<=tol:possible_t.append(sid)
        if possible_t:
            junctions.extend(possible_t[:12]);status="tee_or_interior_junction_requires_review";break
        if not candidates:break
        candidates.sort(key=lambda x:(x[0],x[1]))
        if len(candidates)>1:
            junctions.extend([item[1] for item in candidates[:12]])
            status="branching_endpoint_requires_review";break
        _,eid,other=candidates[0]
        poly.append([other[0],other[1]])
        visited.append(eid);at=other
        status="endpoint_join_geometric_hypothesis"
    if len(visited)>=max_hops:status="hop_limit_requires_review"
    return {"points":poly,"edge_ids":visited,"status":status,"junctions":junctions,
            "endpoint":[at[0],at[1]],"verified":False}

def rank_terminal_evidence(endpoint,circles,prior):
    """Rank CURRENT cached circle OCR and HISTORICAL suggestions separately.

    A historical conflicting number cannot silently disappear; it flags review.
    No confidence score returned here represents probability of connectivity.
    """
    ranked=[]
    if endpoint is not None:
        for c in circles:
            label=str(c["ocr_text"] or "").strip()
            if not VALID_TERMINAL.fullmatch(label):continue
            dx=float(c["x"])-endpoint[0];dy=float(c["y"])-endpoint[1]
            if not -.020<=dx<=.11 or abs(dy)>.035:continue
            confidence=max(0,min(1,float(c["ocr_confidence"] or 0)))
            gap=math.hypot(max(dx,0),dy)
            eligible=confidence>=.60 and -.020<=dx<=.065 and abs(dy)<=.018
            # Sorting heuristic only, not calibrated probability.
            score=round(1.0-min(gap/.12,.8)*.6+confidence*.2,4)
            ranked.append({"number":label,"circle_id":c["id"],"x":c["x"],"y":c["y"],
                           "ocr_confidence":round(confidence,3),
                           "distance":round(gap,5),"score_for_sort_only":score,
                           "evidence":"cached_circle_ocr_geometric","eligible":eligible,
                           "verification":"unverified"})
    history=[]
    for h in prior:
        label=str(h.get("terminal_text") or "").strip()
        if VALID_TERMINAL.fullmatch(label):
            history.append({"number":label,"circle_id":h.get("circle_id"),
                            "distance":h.get("geometric_distance"),
                            "evidence":"prior_path_match_geometric",
                            "eligible":False,"verification":"unverified"})
    ranked.sort(key=lambda z:(not z["eligible"],z["distance"],-z["ocr_confidence"],z["circle_id"]))
    eligible=[r for r in ranked if r["eligible"]]
    conflict_history=sorted({h["number"] for h in history})
    chosen=None;status="no_current_eligible_terminal"
    if len({r["number"] for r in eligible})>1:
        status="conflicting_current_terminal_numbers_review_required"
    elif len(eligible)>1 and eligible[1]["distance"]-eligible[0]["distance"]<.008:
        status="multiple_close_current_terminals"
    elif eligible:
        chosen=eligible[0]
        status="unique_geometric_candidate_unverified"
    if chosen and any(h["number"]!=chosen["number"] for h in history):
        status="conflicting_historical_terminal_numbers_review_required"
        # Keep the strongest geometric lead visible but do not claim an unambiguous result.
    elif not chosen and history:
        status="historical_only_or_ambiguous"
    return {"best_geometric_candidate":chosen,
            "status":status,"current_candidates":ranked[:15],
            "historical_suggestions":history[:15],
            "historical_numbers":conflict_history,
            "conflict":status in ("multiple_close_current_terminals",
                                 "conflicting_current_terminal_numbers_review_required",
                                 "conflicting_historical_terminal_numbers_review_required"),
            "electrically_verified":False,"connector_ownership_verified":False}

def build(dbpath,diagram_id,image_path,reader=None):
    image_path=Path(image_path)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        trace=source_snapshot(db,diagram_id)
        old_items=[dict(r) for r in db.execute(
            "SELECT * FROM trace_items_v0317 WHERE run_id=? ORDER BY fuse_label",
            (trace["id"],))]
        fingerprint=hashlib.sha256(json.dumps({
            "processor":PROCESSOR_VERSION,"trace_run_id":trace["id"],
            "trace_input_fingerprint":json.loads(trace["summary_json"]).get("input_fingerprint"),
            "components":[x["component_id"] for x in old_items]
        },sort_keys=True).encode()).hexdigest()
        existing=db.execute(
            "SELECT id,summary_json FROM enhanced_runs_v0318 WHERE diagram_id=? AND source_fingerprint=?",
            (diagram_id,fingerprint)).fetchone()
        if existing:
            return dict(json.loads(existing["summary_json"]),run_id=existing["id"],cache_hit=True)
        circ_id=newest_id(db,"independent_runs_v039",diagram_id)
        circles=[dict(c) for c in db.execute(
            "SELECT id,x,y,ocr_text,ocr_confidence FROM independent_circles_v039 WHERE run_id=?",
            (circ_id,))] if circ_id else []
        gray=None
        if image_path.is_file():
            try:
                from PIL import Image
                with Image.open(image_path) as im:gray=im.convert("L")
            except (ImportError,OSError):pass
        rows=[];rating_found=conflicts=terminal_candidates=tries=bends=0
        for item in old_items:
            comp_id=item["component_id"]
            component=db.execute(
                "SELECT * FROM component_items_v0316 WHERE id=?",(comp_id,)).fetchone()
            if component is None:continue
            gap=db.execute(
                "SELECT * FROM continuity_items_v0314 WHERE id=?",(component["source_gap_id"],)).fetchone()
            gap=dict(gap) if gap is not None else None
            old_trace=json.loads(item["trace_json"])
            # Skip new OCR if v0.3.17 OCR already gave a reading or user confirmed a rating.
            review=db.execute(
                "SELECT * FROM trace_reviews_v0317 WHERE component_id=?",(comp_id,)).fetchone()
            reviewed_rating=review["rating_override"] if review else None
            old_rating=item["rating_text"]
            rating=reviewed_rating or old_rating
            if rating:
                rating_status="reused_human_rating" if reviewed_rating else "reused_v0317_rating"
                hits=[];crops=[];attempts=0
            else:
                rating,rating_status,hits,crops,attempts=crop_rating_evidence(gray,gap,reader)
            rating_found+=bool(rating);tries+=attempts
            target=db.execute(
                "SELECT id,x1,y1,x2,y2 FROM graph_edges_v033 WHERE id=?",
                (component["target_edge_id"],)).fetchone()
            segrow=db.execute("""
                SELECT ar.segment_run_id FROM continuity_items_v0314 gap
                JOIN association_candidates_v035 a ON a.id=gap.association_id
                JOIN association_runs_v035 ar ON ar.id=a.run_id
                WHERE gap.id=?""",(component["source_gap_id"],)).fetchone()
            segments=[dict(e) for e in db.execute(
                """SELECT source_edge_id,classification,x1,y1,x2,y2
                   FROM segment_edges_v034 WHERE run_id=?""",
                (segrow["segment_run_id"],))] if segrow else []
            route=follow_endpoint_graph(dict(target) if target else None,segments)
            bends+=len(route["edge_ids"])>1
            prior=old_trace.get("prior_terminal_suggestions",[])
            ranking=rank_terminal_evidence(route.get("endpoint"),circles,prior)
            conflicts+=ranking["conflict"]
            terminal_candidates+=bool(ranking["best_geometric_candidate"])
            note=("Path is a GEOMETRIC HYPOTHESIS. No electrical continuity proven. "
                  "Connector/terminal ownership not established. Review bends, junctions and image.")
            rows.append((uuid.uuid4().hex,comp_id,item["fuse_label"],rating,rating_status,
                         json.dumps(hits),json.dumps(crops),json.dumps(route),
                         json.dumps(ranking),ranking["status"],note))
        summary={"reused_v0317_components":len(old_items),
                 "new_rating_candidates":rating_found,
                 "targeted_new_ocr_attempts":tries,
                 "terminal_geometric_candidates":terminal_candidates,
                 "terminal_evidence_conflicts":conflicts,
                 "traces_with_endpoint_extensions":bends,
                 "older_stages_rerun":0,
                 "electrically_verified_connections":0,
                 "warning":"All proposed ratings, circuit branches, and terminal numbers require diagram/manual verification."}
        rid=uuid.uuid4().hex
        db.execute("""
            INSERT INTO enhanced_runs_v0318(id,diagram_id,trace_run_id,source_fingerprint,summary_json)
            VALUES(?,?,?,?,?)""",(rid,diagram_id,trace["id"],fingerprint,json.dumps(summary)))
        db.executemany("""
            INSERT INTO enhanced_items_v0318
              (id,run_id,component_id,fuse_label,rating_text,rating_status,
               rating_evidence_json,crop_evidence_json,trace_json,terminal_ranking_json,trace_status,warning)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       [(r[0],rid,*r[1:]) for r in rows])
        db.commit()
        return dict(summary,run_id=rid,cache_hit=False)

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        run=db.execute(
            "SELECT * FROM enhanced_runs_v0318 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
            (diagram_id,)).fetchone()
        if not run:return {"run":None,"items":[]}
        if newest_id(db,"trace_runs_v0317",diagram_id)!=run["trace_run_id"]:
            return {"run":None,"items":[],"stale":True,
                    "reason":"Saved trace input changed; click v0.3.18 once to reuse current analysis."}
        items=[]
        for r in db.execute(
            "SELECT * FROM enhanced_items_v0318 WHERE run_id=? ORDER BY fuse_label",(run["id"],)):
            d=dict(r)
            d["rating_evidence"]=json.loads(d.pop("rating_evidence_json"))
            d["crops"]=json.loads(d.pop("crop_evidence_json"))
            d["route"]=json.loads(d.pop("trace_json"))
            d["terminal_ranking"]=json.loads(d.pop("terminal_ranking_json"))
            manual=db.execute(
                "SELECT review_status,rating_override FROM trace_reviews_v0317 WHERE component_id=?",
                (d["component_id"],)).fetchone()
            d["human_review"]=manual["review_status"] if manual else "needs_review"
            d["human_rating"]=manual["rating_override"] if manual else None
            d["display_rating"]=d["human_rating"] or d["rating_text"]
            d["electrically_verified"]=False
            items.append(d)
        return {"run":dict(id=run["id"],**json.loads(run["summary_json"])),"items":items}

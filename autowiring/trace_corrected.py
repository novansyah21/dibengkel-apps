"""AutoWiring v0.3.19 — cached OCR correction, junction-dot inspection, terminal circle rescue.

Incremental-only: consumes persisted v0.3.18 outputs, v0.3.17/earlier circle
coordinates and original source pixels. It NEVER rebuilds the earlier pipeline.
Visual schematic hypotheses are NOT electrically verified circuits or pinouts.
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

from autowiring.trace_review import newest_id,normalize_rating
from autowiring.trace_enhanced import rank_terminal_evidence

PROCESSOR_VERSION="v0319.1"
SCHEMA="""
CREATE TABLE IF NOT EXISTS corrected_runs_v0319 (
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 enhanced_run_id TEXT NOT NULL,
 input_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,
 UNIQUE(diagram_id,input_fingerprint)
);
CREATE TABLE IF NOT EXISTS corrected_items_v0319 (
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL,
 component_id TEXT NOT NULL,
 fuse_label TEXT NOT NULL,
 rating_text TEXT,
 rating_status TEXT NOT NULL,
 rating_evidence_json TEXT NOT NULL,
 terminal_evidence_json TEXT NOT NULL,
 junction_evidence_json TEXT NOT NULL,
 pixel_evidence_json TEXT NOT NULL,
 status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corrected_items_v0319 ON corrected_items_v0319(run_id);
"""
# Manually transcribed connector header layout, specific to Junction Block image
# in this project (1136x1598). These are region hints, NEVER pinout proof.
JUNCTION_BLOCK_HEADER_COLUMNS=[
    ("BCM",606,652),("E323",652,698),("E324",698,744),("E325",744,790),
    ("G273",790,836),("G271",836,882),("G272",882,928),
    ("L312",928,974),("L313",974,1020),("L314",1020,1066),("L315",1066,1112),
]
TERMINAL_NUMBER_RE=re.compile(r'^(?:[1-9]|[1-3]\d)$')

def normalize_cached_token(raw):
    """OCR has dropped confidence in v0.3.18 raw_tokens; do not infer it.

    Only isolated ampere tokens with trailing OCR punctuation are allowed.
    A single token cannot pass the corroboration requirement.
    """
    if not isinstance(raw,str):return None
    token=raw.strip()
    if not re.fullmatch(r'(?:5|7[.,]5|10|15|20|25|30|40|50|60|70|80|100)\s*A[.,;:]?',token,re.I):
        return None
    return normalize_rating(token.rstrip('.,;:'))

def recover_cached_rating(old_rating,crops):
    if old_rating:
        return old_rating,"reused_v0318_rating",{"kind":"existing_rating","ocr_confirmation":"unverified"}
    sightings=[]
    for crop in crops:
        roi=crop.get('roi','unknown')
        for attempt in crop.get('attempts',[]):
            for raw in attempt.get('raw_tokens',[]):
                rate=normalize_cached_token(raw)
                if rate:sightings.append({'rating':rate,'token':raw,'roi':roi,
                                           'psm':attempt.get('psm'),
                                           'source':'cached_v0318_raw_token_no_confidence'})
    values=sorted(set(s['rating'] for s in sightings))
    distinct_roi={s['roi'] for s in sightings}
    evidence={'sightings':sightings,'distinct_roi_count':len(distinct_roi),
              'confidence_available':False,
              'human_confirmation_required':True}
    if len(values)>1:return None,"conflicting_cached_raw_ratings",evidence
    if len(values)==1 and len(distinct_roi)>=2:
        return values[0],"corroborated_cached_raw_ocr_review_required",evidence
    return None,"cached_raw_insufficient_for_rating",evidence

def visually_locate_column(diagram_id,circle,image_size):
    if diagram_id!="junction_block" or not circle or image_size is None:return None
    width,height=image_size
    if abs(width/height-1136/1598)>.025:return None
    px=circle['x']*1136  # scale-invariant image region reference
    for name,x0,x1 in JUNCTION_BLOCK_HEADER_COLUMNS:
        if x0<=px<x1:
            return {'label':name,'status':'connector_header_column_visual_candidate',
                    'source':'manually_transcribed_junction_block_header_layout',
                    'electrically_verified':False,'pinout_verified':False}
    return None

def split_prior_fuse_labels(prior,all_circles,component):
    """Prior path matcher sometimes calls circled fuse index 21 a terminal.

    Do NOT throw away it as evidence; classify by position relative to fuse
    symbol and preserve in excluded_suggestions for human review.
    """
    by_id={c['id']:c for c in all_circles}
    valid=[];excluded=[]
    for entry in prior:
        c=by_id.get(entry.get('circle_id'))
        is_near_fuse=(c is not None and
            abs(c['x']-component['x'])<.047 and
            abs(c['y']-component['y'])<.029)
        if is_near_fuse:
            excluded.append(dict(entry,
                classification='fuse_index_circle_not_terminal_candidate',
                circle_location=[round(c['x'],5),round(c['y'],5)],
                reason='Circle near fuse symbol, far from terminal/header area; visual classification only.'))
        else:valid.append(entry)
    return valid,excluded

def _ink(gray,x,y):
    return 0<=x<gray.width and 0<=y<gray.height and gray.getpixel((x,y))<125

def _dot_density(gray,x,y,r=5):
    dark=0;total=0
    for xx in range(max(0,x-r),min(gray.width,x+r+1)):
        for yy in range(max(0,y-r),min(gray.height,y+r+1)):
            dark+=_ink(gray,xx,yy);total+=1
    return round(dark/max(total,1),4)

def _max_vertical_run(gray,x,y,sign):
    # Ignore the horizontal line itself; only long coherent orthogonal strokes.
    best=cur=0
    for depth in range(10,71):
        yy=y+sign*depth
        yes=any(_ink(gray,x+dx,yy) for dx in (-1,0,1))
        cur=cur+1 if yes else 0
        if cur>best:best=cur
    return best

def detect_junction_dots(gray,route,diagram_id,max_dots=12):
    """Inspect original ink along cached horizontal wire; does NOT connect paths.

    Dense black dots with sustained vertical strokes are distinguishable from
    thin line crossings / long dashed borders in the sample image. Still
    classified only as candidate schematic junctions.
    """
    if gray is None:return []
    points=route.get('points') or []
    if len(points)<2:return []
    candidates=[]
    width,height=gray.size
    right_clip=int(width*(.53 if diagram_id=="junction_block" else .94))
    for p,q in zip(points,points[1:]):
        x0,y0=round(p[0]*width),round(p[1]*height)
        x1,y1=round(q[0]*width),round(q[1]*height)
        if abs(y0-y1)>2:continue
        y=round((y0+y1)/2)
        xa=max(8,min(x0,x1)+22)
        xb=min(width-8,max(x0,x1)-22,right_clip)
        for x in range(xa,xb):
            density=_dot_density(gray,x,y)
            if density<.70:continue
            up=_max_vertical_run(gray,x,y,-1)
            down=_max_vertical_run(gray,x,y,1)
            if max(up,down)<28:continue
            sign=-1 if up>=down else 1
            length=min(max(up,down)+10,70)
            candidates.append({'x':round(x/width,6),'y':round(y/height,6),
                               'pixel_x':x,'pixel_y':y,
                               'dot_11px_dark_fraction':density,
                               'vertical_up_run_px':up,'vertical_down_run_px':down,
                               'branch_preview_points':[
                                   [round(x/width,6),round(y/height,6)],
                                   [round(x/width,6),round((y+sign*length)/height,6)]],
                               'status':'dark_dot_plus_vertical_ink_visual_junction_candidate',
                               'electrically_verified':False})
    clusters=[]
    for a in candidates:
        if clusters and abs(clusters[-1][-1]['pixel_x']-a['pixel_x'])<=4 and (
                clusters[-1][-1]['pixel_y']==a['pixel_y']):
            clusters[-1].append(a)
        else:clusters.append([a])
    found=[]
    for cluster in clusters[:max_dots]:
        winner=max(cluster,key=lambda x:(x['dot_11px_dark_fraction'],
                                          max(x['vertical_up_run_px'],x['vertical_down_run_px'])))
        found.append(winner)
    return found

def pixel_terminal_probe(gray,endpoint,circle):
    """Visual ink inspection from last segment to unread/known terminal circle.

    Does not prove a conductor or an electrical connection.
    """
    if gray is None or endpoint is None or circle is None:
        return {'status':'missing_pixel_or_circle_evidence','electrically_verified':False}
    w,h=gray.size
    ex,ey=round(endpoint[0]*w),round(endpoint[1]*h)
    cx,cy=round(circle['x']*w),round(circle['y']*h)
    radius=round(float(circle.get('r') or .007)*max(w,h))
    stop=max(ex,cx-radius+2)
    xs=range(max(0,ex-10),min(w,stop+1))
    ink=[any(_ink(gray,x,y) for y in range(max(0,ey-1),min(h,ey+2))) for x in xs]
    coverage=round(sum(ink)/max(1,len(ink)),4)
    return {'status':'ink_near_terminal_circle_visual_only',
            'pixel_coverage':coverage,'sampled_columns':len(ink),
            'terminal_circle_radius_px':radius,
            'terminal_circle_xy_px':[cx,cy],
            'electrically_verified':False}

def _data_reader(image,psm):
    import pytesseract
    from pytesseract import Output
    out=pytesseract.image_to_data(
        image,config=f'--psm {psm} -c tessedit_char_whitelist=0123456789',
        output_type=Output.DICT)
    result=[]
    for raw,conf in zip(out.get('text',[]),out.get('conf',[])):
        try:score=float(conf)/100
        except (ValueError,TypeError):score=0
        result.append((str(raw).strip(),score))
    return result

def targeted_unread_circle_ocr(gray,endpoint,circles,reader=None):
    """One unread circle near endpoint, using a NEW tighter interior crop.

    Does not rerun circle detection or previous broad OCR. Persisted results
    are fingerprint-cached, so a repeated click causes zero OCR calls.
    """
    if gray is None or endpoint is None:
        return None,{'status':'original_image_unavailable','attempts':[]}
    candidates=[]
    for c in circles:
        if c.get('ocr_text'):continue
        dx=float(c['x'])-endpoint[0];dy=float(c['y'])-endpoint[1]
        dist=math.hypot(max(0,dx),dy)
        if -.015<=dx<=.028 and abs(dy)<=.015 and .0035<=float(c['r'])<=.016:
            candidates.append((dist,c))
    candidates.sort(key=lambda x:x[0])
    if not candidates:
        return None,{'status':'no_cached_unread_circle_near_endpoint','attempts':[]}
    if len(candidates)>1 and candidates[1][0]-candidates[0][0]<.005:
        return None,{'status':'ambiguous_nearby_unread_circles','attempts':[]}
    from PIL import ImageOps,ImageEnhance
    c=candidates[0][1]
    w,h=gray.size;x=round(c['x']*w);y=round(c['y']*h)
    r=max(4,round(float(c['r'])*max(w,h)))
    half=max(3,round(r*.58))
    box=(max(0,x-half),max(0,y-half),min(w,x+half+1),min(h,y+half+1))
    crop=ImageOps.autocontrast(gray.crop(box))
    out=io.BytesIO();crop.save(out,format='PNG')
    report={'status':'no_confident_focused_read',
            'circle_id':c['id'],'box':list(box),
            'crop_png_base64':base64.b64encode(out.getvalue()).decode('ascii'),
            'attempts':[],'original_ocr_text':None,
            'electrically_verified':False}
    if reader is None:
        try:import pytesseract # noqa
        except ImportError:
            report['status']='tesseract_unavailable'
            return None,report
        reader=_data_reader
    enlarged=ImageEnhance.Contrast(crop.resize((crop.width*8,crop.height*8))).enhance(1.3)
    # Two new configurations at most; stop once a unique >= .60 OCR lead appears.
    reads=[]
    for psm in (8,13):
        try:
            results=reader(enlarged,psm)
            report['attempts'].append({'psm':psm,
                'raw_tokens':[str(z[0]) for z in results if str(z[0])][:10]})
            for raw,confidence in results:
                number=str(raw).strip()
                if TERMINAL_NUMBER_RE.fullmatch(number) and float(confidence)>=.60:
                    reads.append((number,round(float(confidence),3)))
        except Exception as exc:
            report['attempts'].append({'psm':psm,'error':type(exc).__name__})
        if reads:break
    if len({v[0] for v in reads})>1:
        report['status']='conflicting_new_circle_ocr'
        return None,report
    if not reads:return None,report
    number,confidence=max(reads,key=lambda z:z[1])
    report.update(status='focused_unread_circle_ocr_candidate_needs_review',
                  new_terminal_text=number,ocr_confidence=confidence)
    updated=dict(c,ocr_text=number,ocr_confidence=confidence)
    return updated,report

def _check_source_image(db,diagram_id,image_path):
    image_sha=hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.is_file() else None
    cols={x['name'] for x in db.execute("PRAGMA table_info(auto_runs_v032)")}
    if image_sha and 'image_sha256' in cols:
        source=db.execute("""
            SELECT image_sha256 FROM auto_runs_v032 WHERE diagram_id=?
            ORDER BY created_at DESC,rowid DESC LIMIT 1""",(diagram_id,)).fetchone()
        if source and source['image_sha256'] and source['image_sha256']!=image_sha:
            raise ValueError('Source diagram changed; saved OCR and geometry may be stale. No older stages were rerun.')
    return image_sha

def build(dbpath,diagram_id,image_path,digit_reader=None):
    image_path=Path(image_path)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        db.executescript(SCHEMA)
        enhanced_id=newest_id(db,'enhanced_runs_v0318',diagram_id)
        if enhanced_id is None:
            raise ValueError('v0.3.18 result not found. Use original output/autowiring.db; DO NOT repeat old pipeline.')
        enhanced=db.execute('SELECT * FROM enhanced_runs_v0318 WHERE id=?',(enhanced_id,)).fetchone()
        if enhanced['trace_run_id']!=newest_id(db,'trace_runs_v0317',diagram_id):
            raise ValueError('Previous trace is stale. No older process was rerun.')
        image_sha=_check_source_image(db,diagram_id,image_path)
        independent_id=newest_id(db,'independent_runs_v039',diagram_id)
        fingerprint=hashlib.sha256(json.dumps({
            'processor':PROCESSOR_VERSION,'enhanced_id':enhanced_id,
            'original_image_sha256':image_sha,'independent_id':independent_id
        },sort_keys=True).encode()).hexdigest()
        prev=db.execute('SELECT id,summary_json FROM corrected_runs_v0319 WHERE diagram_id=? AND input_fingerprint=?',
                        (diagram_id,fingerprint)).fetchone()
        if prev:
            return dict(json.loads(prev['summary_json']),run_id=prev['id'],
                        cache_hit=True,older_stages_rerun=0,targeted_ocr_repeated=0)
        circles=[dict(row) for row in db.execute(
            'SELECT * FROM independent_circles_v039 WHERE run_id=?',(independent_id,)
        )] if independent_id else []
        gray=None
        if image_path.is_file():
            try:
                from PIL import Image
                with Image.open(image_path) as im:gray=im.convert('L')
            except (ImportError,OSError):pass
        rows=[];recovered_count=targeted_count=terminal_count=dot_count=filtered_count=conflict_count=0
        for old in db.execute('SELECT * FROM enhanced_items_v0318 WHERE run_id=? ORDER BY fuse_label',
                              (enhanced_id,)):
            a=dict(old)
            component=db.execute('SELECT * FROM component_items_v0316 WHERE id=?',
                                 (a['component_id'],)).fetchone()
            if not component:continue
            component=dict(component)
            crops=json.loads(a['crop_evidence_json'])
            rating,rating_status,rating_evidence=recover_cached_rating(a['rating_text'],crops)
            recovered_count+=rating_status=='corroborated_cached_raw_ocr_review_required'
            route=json.loads(a['trace_json'])
            old_ranking=json.loads(a['terminal_ranking_json'])
            parent=db.execute('SELECT trace_json FROM trace_items_v0317 WHERE component_id=? AND run_id=?',
                 (a['component_id'],enhanced['trace_run_id'])).fetchone()
            prior=json.loads(parent['trace_json']).get('prior_terminal_suggestions',[]) if parent else []
            valid_prior,excluded_prior=split_prior_fuse_labels(prior,circles,component)
            filtered_count+=len(excluded_prior)
            endpoint=route.get('endpoint')
            chosen,new_ocr=targeted_unread_circle_ocr(gray,endpoint,circles,digit_reader) if not old_ranking.get('best_geometric_candidate') else (
                None,{'status':'cached_readable_terminal_reused','attempts':[]})
            if chosen:
                circles_for_trace=circles+[chosen]  # New hypothesis stored only in v0.3.19.
                targeted_count+=1
            else:circles_for_trace=circles
            ranking=rank_terminal_evidence(endpoint,circles_for_trace,valid_prior)
            if ranking.get('best_geometric_candidate'):
                terminal_count+=1
            conflict_count+=ranking.get('conflict',False)
            ranking['excluded_prior_fuse_index_suggestions']=excluded_prior
            ranking['focused_circle_ocr']=new_ocr
            ranking['connector_column_candidate']=visually_locate_column(
                diagram_id,ranking.get('best_geometric_candidate'),
                gray.size if gray else None)
            all_candidates={c['id']:c for c in circles_for_trace}
            selected=ranking.get('best_geometric_candidate')
            pixel=pixel_terminal_probe(gray,endpoint,all_candidates.get(selected['circle_id']) if selected else None)
            junctions=detect_junction_dots(gray,route,diagram_id)
            dot_count+=len(junctions)
            status='visual_evidence_requires_manual_review'
            rows.append((uuid.uuid4().hex,a['component_id'],a['fuse_label'],rating,rating_status,
                         json.dumps(rating_evidence),json.dumps(ranking),json.dumps(junctions),
                         json.dumps(pixel),status))
        summary={'reused_v0318_components':len(rows),
                 'total_rating_candidates':sum(bool(r[3]) for r in rows),
                 'recovered_ratings_from_cached_raw':recovered_count,
                 'new_targeted_unread_circle_reads':targeted_count,
                 'terminal_geometric_leads':terminal_count,
                 'filtered_likely_fuse_index_misclassifications':filtered_count,
                 'remaining_terminal_conflicts':conflict_count,
                 'visual_junction_dot_candidates':dot_count,
                 'older_stages_rerun':0,'electrically_verified_connections':0,
                 'warning':'Visual hypotheses only. Dot/circle/column do not verify wire continuity or connector ownership.'}
        rid=uuid.uuid4().hex
        db.execute('INSERT INTO corrected_runs_v0319(id,diagram_id,enhanced_run_id,input_fingerprint,summary_json) VALUES(?,?,?,?,?)',
                   (rid,diagram_id,enhanced_id,fingerprint,json.dumps(summary)))
        db.executemany("""INSERT INTO corrected_items_v0319
          (id,run_id,component_id,fuse_label,rating_text,rating_status,
           rating_evidence_json,terminal_evidence_json,junction_evidence_json,
           pixel_evidence_json,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
           [(r[0],rid,*r[1:]) for r in rows])
        db.commit()
        return dict(summary,run_id=rid,cache_hit=False,targeted_ocr_repeated=0)

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        run=db.execute("""SELECT * FROM corrected_runs_v0319 WHERE diagram_id=?
                          ORDER BY created_at DESC,rowid DESC LIMIT 1""",(diagram_id,)).fetchone()
        if not run:return {'run':None,'items':[]}
        if run['enhanced_run_id']!=newest_id(db,'enhanced_runs_v0318',diagram_id):
            return {'run':None,'items':[],'stale':True}
        items=[]
        for row in db.execute('SELECT * FROM corrected_items_v0319 WHERE run_id=? ORDER BY fuse_label',
                              (run['id'],)):
            r=dict(row)
            for col,name in [('rating_evidence_json','rating_evidence'),
                             ('terminal_evidence_json','terminal_evidence'),
                             ('junction_evidence_json','junction_dots'),
                             ('pixel_evidence_json','pixel_evidence')]:
                r[name]=json.loads(r.pop(col))
            review=db.execute('SELECT review_status,rating_override FROM trace_reviews_v0317 WHERE component_id=?',
                              (r['component_id'],)).fetchone()
            r['human_review']=review['review_status'] if review else 'needs_review'
            r['human_rating']=review['rating_override'] if review else None
            r['display_rating']=r['human_rating'] or r['rating_text']
            r['electrically_verified']=False
            items.append(r)
        return {'run':dict(id=run['id'],**json.loads(run['summary_json'])),'items':items}

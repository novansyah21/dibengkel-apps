"""AutoWiring v0.3.17: idempotent, evidence-bounded fuse/circuit trace review.

IMPORTANT: all paths are visual hypotheses, not proved electrical connections.
Reads persisted v0.3.16 components and earlier OCR/segmentation; never calls
upstream OCR, segmentation, association, continuity, or component builders.
"""
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_runs_v0317 (
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 component_run_id TEXT NOT NULL,
 input_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 summary_json TEXT NOT NULL,
 UNIQUE(diagram_id,input_fingerprint)
);
CREATE TABLE IF NOT EXISTS trace_items_v0317 (
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL,
 component_id TEXT NOT NULL,
 fuse_label TEXT NOT NULL,
 shape_status TEXT NOT NULL,
 shape_evidence_json TEXT NOT NULL,
 rating_text TEXT,
 rating_status TEXT NOT NULL,
 rating_raw TEXT NOT NULL,
 terminal_text TEXT,
 terminal_circle_id TEXT,
 terminal_ocr_confidence REAL,
 trace_status TEXT NOT NULL,
 trace_reason TEXT NOT NULL,
 trace_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_run_v0317 ON trace_items_v0317(run_id);
CREATE TABLE IF NOT EXISTS trace_reviews_v0317 (
 component_id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 review_status TEXT NOT NULL,
 rating_override TEXT,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
RATING_RE = re.compile(r'^\s*(5|7[.,]5|10|15|20|25|30|40|50|60|70|80|100)\s*A\s*$', re.I)
TERMINAL_RE = re.compile(r'^(?:[1-9]|[1-3][0-9])$')
RATINGS = ('5A','7.5A','10A','15A','20A','25A','30A','40A','50A','60A','70A','80A','100A')

def normalize_rating(raw):
    if not isinstance(raw,str):
        return None
    cleaned = raw.upper().strip().replace(',','.')
    match = RATING_RE.fullmatch(cleaned)
    return match.group(1).replace(',','.')+'A' if match else None

def newest_id(db,table,diagram_id):
    row = db.execute(
        'SELECT id FROM '+table+' WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
        (diagram_id,)
    ).fetchone()
    return row['id'] if row else None

def measure_shape(gray,gap):
    """Original pixels, without orange/cyan v0.3.15 annotations.

    Waveform measurements are diagnostic; even a positive result needs review.
    """
    if gray is None or gap is None:
        return 'shape_not_available', {'reason':'original image or gap coordinates unavailable'}
    width,height=gray.size
    x0=round(gap['endpoint_x']*width)
    x1=round(gap['neighbor_x']*width)
    y=round((gap['endpoint_y']+gap['neighbor_y'])*height/2)
    a=max(0,min(x0,x1)+4)
    b=min(width,max(x0,x1)-4)
    if b-a<10:
        return 'shape_not_available',{'reason':'insufficient gap pixels','pixels':max(0,b-a)}
    px=gray.load()
    positions=[]
    center_ink=0
    for x in range(a,b):
        ys=[offset for offset in range(-7,8) if 0<=y+offset<height and px[x,y+offset]<155]
        if ys:positions.append(sorted(ys)[len(ys)//2])
        if 0<=y<height and px[x,y]<155:center_ink+=1
    coverage=round(len(positions)/(b-a),3)
    amplitude=max(positions)-min(positions) if positions else 0
    changes=[]
    for z1,z2 in zip(positions,positions[1:]):
        d=z2-z1
        if d:changes.append(1 if d>0 else -1)
    reversals=sum(u!=v for u,v in zip(changes,changes[1:]))
    evidence={'gap_pixel_width':b-a,'ink_column_coverage':coverage,
              'waveform_vertical_amplitude_px':amplitude,'direction_reversals':reversals,
              'centerline_fraction':round(center_ink/(b-a),3)}
    # No fuse assertion from pixels alone, nor from alignment with a fuse label.
    plausible=(coverage>=.25 and amplitude>=3 and reversals>=2)
    return ('waveform_like_visual_candidate' if plausible else
            'shape_ambiguous_review_crop'),evidence

def _prior_rating(candidates,component,gap):
    if gap is None:return None,'none',[]
    right=gap['neighbor_x']
    y=component['y']
    found=[]
    for c in candidates:
        rating=normalize_rating(str(c['label']))
        if not rating or (c['confidence'] or 0)<.45:continue
        x=c['x']+c['w']/2
        cy=c['y']+c['h']/2
        if right-.012<=x<=right+.085 and abs(cy-y)<=.022:
            found.append((rating,round(c['confidence'],3),c['label']))
    values={v[0] for v in found}
    if len(values)==1:
        return found[0][0],'reused_prior_ocr_unverified',[v[2] for v in found]
    if len(values)>1:
        return None,'conflicting_prior_ocr',[v[2] for v in found]
    return None,'no_usable_prior_rating',[]

def _focused_rating(gray,gap,reader=None):
    """OCR only fuse-rating ROI, never reprocess full diagram; at most two PSMs."""
    if gray is None or gap is None:return None,'image_unavailable',[],0
    if reader is None:
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError:
            return None,'tesseract_unavailable',[],0
        def reader(crop,psm):
            return pytesseract.image_to_data(
                crop,config='--psm '+str(psm)+' -c tessedit_char_whitelist=0123456789Aa.',
                output_type=Output.DICT)
    try:
        from PIL import ImageOps,ImageEnhance
        w,h=gray.size
        right=gap['neighbor_x']
        y=(gap['endpoint_y']+gap['neighbor_y'])/2
        # Rating is usually printed after/right of the drawn fuse symbol.
        box=(max(0,round((right-.015)*w)),max(0,round((y-.018)*h)),
             min(w,round((right+.090)*w)),min(h,round((y+.018)*h)))
        if box[2]-box[0]<8 or box[3]-box[1]<8:
            return None,'rating_crop_too_small',[],0
        crop=ImageOps.autocontrast(gray.crop(box))
        crop=ImageEnhance.Contrast(crop.resize((crop.width*3,crop.height*3))).enhance(1.4)
        reads=[];attempts=0
        for psm in (7,11):
            attempts+=1
            data=reader(crop,psm)
            for raw,confidence in zip(data.get('text',[]),data.get('conf',[])):
                rate=normalize_rating(str(raw))
                try:conf=float(confidence)
                except (TypeError,ValueError):continue
                if rate and conf>=50:reads.append((rate,round(conf/100,3),str(raw)))
            if reads:break
        values={a[0] for a in reads}
        if len(values)==1:return reads[0][0],'focused_rating_ocr_unverified',[z[2] for z in reads],attempts
        if len(values)>1:return None,'conflicting_focused_ocr',[z[2] for z in reads],attempts
        return None,'rating_not_read',[],attempts
    except Exception as exc:
        return None,'focused_ocr_error_'+type(exc).__name__,[],0

def _distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])

def _trace_chain(target_edge,edge_pool,max_hops=8,tol=.0025):
    """Only endpoint-to-endpoint geometric extensions; no cross/tee inference."""
    if not target_edge:
        return [],[],'target_edge_missing'
    x1,y1,x2,y2=[float(target_edge[k]) for k in ('x1','y1','x2','y2')]
    if abs(x2-x1)<abs(y2-y1):
        return [[x1,y1],[x2,y2]],[target_edge['id']],'target_not_horizontal'
    points=[[x1,y1],[x2,y2]]
    ids=[target_edge['id']]
    end=(x2,y2)
    available={e['source_edge_id']:e for e in edge_pool if e.get('classification')=='candidate_wire'}
    for _ in range(max_hops-1):
        options=[]
        for key,e in available.items():
            if key in ids:continue
            a=(float(e['x1']),float(e['y1']))
            b=(float(e['x2']),float(e['y2']))
            da=_distance(end,a);db=_distance(end,b)
            d=min(da,db)
            if d<=tol:
                other=b if da<=db else a
                if _distance(end,other)>tol:options.append((d,key,other))
        if not options:break
        options.sort(key=lambda v:v[0])
        if len(options)>1:return points,ids,'branch_or_crossing_ambiguous'
        _,key,other=options[0]
        ids.append(key);points.append([other[0],other[1]]);end=other
    return points,ids,'endpoint_chain_hypothesis' if len(ids)>1 else 'single_right_side_segment'

def trace_terminal(points,circles):
    """A circle with OCR near an end is a geometric lead, not a connector pinout."""
    if not points:return None,[], 'no_target_edge'
    endpoint=points[-1]
    ranked=[]
    for c in circles:
        number=str(c['ocr_text'] or '').strip()
        if not TERMINAL_RE.fullmatch(number) or float(c['ocr_confidence'])<.60:
            continue
        dx=c['x']-endpoint[0];dy=c['y']-endpoint[1]
        # Small negative x permits terminal-circle centers overlapping wire ends.
        if not (-.020<=dx<=.065 and abs(dy)<=.018):continue
        distance=math.hypot(max(0,dx),dy)
        ranked.append({'circle_id':c['id'],'terminal_text':number,
                       'ocr_confidence':round(c['ocr_confidence'],3),
                       'geometric_distance':round(distance,5),
                       'offset_x':round(dx,5),'offset_y':round(dy,5),
                       'x':c['x'],'y':c['y'],
                       'status':'geometric_candidate_requires_manual_pinout_review'})
    ranked.sort(key=lambda v:(v['geometric_distance'],-v['ocr_confidence'],v['circle_id']))
    if not ranked:return None,[],'no_eligible_cached_ocr_circle_near_endpoint'
    if len(ranked)>1 and ranked[1]['geometric_distance']-ranked[0]['geometric_distance']<.008:
        return None,ranked[:3],'ambiguous_terminal_circles'
    return ranked[0],ranked[:3],'terminal_geometric_candidate_unverified'

def _source_segment_run(db,gap_id):
    row=db.execute("""
      SELECT ar.segment_run_id FROM continuity_items_v0314 g
      JOIN association_candidates_v035 ac ON ac.id=g.association_id
      JOIN association_runs_v035 ar ON ar.id=ac.run_id
      WHERE g.id=?
    """,(gap_id,)).fetchone()
    return row['segment_run_id'] if row else None

def build(dbpath,diagram_id,image_path,ocr_reader=None):
    image_path=Path(image_path)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        db.executescript(SCHEMA)
        comp_id=newest_id(db,'component_runs_v0316',diagram_id)
        if comp_id is None:
            raise ValueError('v0.3.16 component results not found in this database. Keep your existing output/autowiring.db; no older processing will be rerun automatically.')
        components=[dict(row) for row in db.execute(
            'SELECT * FROM component_items_v0316 WHERE run_id=? ORDER BY fuse_label,id',(comp_id,))]
        independent_id=newest_id(db,'independent_runs_v039',diagram_id)
        auto_id=newest_id(db,'auto_runs_v032',diagram_id)
        gap_ids=[c['source_gap_id'] for c in components]
        gaps={}
        segment_ids={}
        for gid in gap_ids:
            row=db.execute('SELECT * FROM continuity_items_v0314 WHERE id=?',(gid,)).fetchone()
            if row:gaps[gid]=dict(row)
            segment_ids[gid]=_source_segment_run(db,gid)
        image_hash=hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.is_file() else 'missing_image'
        fingerprint=hashlib.sha256(json.dumps({
            'version':'v0317.1','component_run_id':comp_id,'independent_run_id':independent_id,
            'auto_run_id':auto_id,'segment_run_ids':segment_ids,'image_sha256':image_hash
        },sort_keys=True).encode('utf-8')).hexdigest()
        existing=db.execute('SELECT summary_json FROM trace_runs_v0317 WHERE diagram_id=? AND input_fingerprint=?',
                            (diagram_id,fingerprint)).fetchone()
        if existing:
            return dict(json.loads(existing['summary_json']),cache_hit=True,older_stages_rerun=0)
        circles=[dict(x) for x in db.execute('SELECT * FROM independent_circles_v039 WHERE run_id=?',
                                            (independent_id,))] if independent_id else []
        previous=[dict(x) for x in db.execute(
            "SELECT label,x,y,w,h,confidence FROM auto_candidates_v032 WHERE run_id=? AND kind LIKE 'ocr_%'",
            (auto_id,))] if auto_id else []
        edges={}
        all_seg_edges={}
        for c in components:
            tid=c['target_edge_id']
            if tid not in edges:
                row=db.execute('SELECT * FROM graph_edges_v033 WHERE id=?',(tid,)).fetchone()
                edges[tid]=dict(row) if row else None
            sid=segment_ids.get(c['source_gap_id'])
            if sid and sid not in all_seg_edges:
                all_seg_edges[sid]=[dict(x) for x in db.execute(
                    'SELECT * FROM segment_edges_v034 WHERE run_id=?',(sid,))]
        gray=None
        if image_path.is_file():
            try:
                from PIL import Image
                with Image.open(image_path) as im:gray=im.convert('L')
            except (ImportError,OSError):pass
        rows=[]
        shape_like=ratings=terminal_count=ambiguous=ocr_attempts=0
        for c in components:
            gap=gaps.get(c['source_gap_id'])
            shape,shape_evidence=measure_shape(gray,gap)
            shape_like+=shape=='waveform_like_visual_candidate'
            rating,rating_status,raw=_prior_rating(previous,c,gap)
            if rating is None and rating_status!='conflicting_prior_ocr':
                rating,rating_status,raw,attempts=_focused_rating(gray,gap,ocr_reader)
                ocr_attempts+=attempts
            ratings+=bool(rating)
            points,chain_ids,chain_status=_trace_chain(
                edges.get(c['target_edge_id']),all_seg_edges.get(segment_ids.get(c['source_gap_id']),[]))
            terminal,candidates,trace_status=trace_terminal(points,circles)
            terminal_count+=bool(terminal)
            ambiguous+=trace_status=='ambiguous_terminal_circles'
            reason=('Geometric trace using persisted right-side edge and unique endpoint joins only; '
                    'no crossings bridged and no electrical continuity or connector ownership established. '
                    +chain_status)
            if not independent_id:trace_status='cached_independent_ocr_missing'
            trace={'points':points,'edge_ids':chain_ids,'chain_status':chain_status,
                   'terminal_candidates':candidates,'left_side_edge_id':c['source_edge_id'],
                   'right_side_edge_id':c['target_edge_id'],
                   'component_node_id':c['id'],'connector_verified':False,
                   'electrically_verified':False,'source':'existing_database_runs_only'}
            rows.append((uuid.uuid4().hex,c['id'],c['fuse_label'],shape,
                         json.dumps(shape_evidence),rating,rating_status,json.dumps(raw),
                         terminal['terminal_text'] if terminal else None,
                         terminal['circle_id'] if terminal else None,
                         terminal['ocr_confidence'] if terminal else None,
                         trace_status,reason,json.dumps(trace)))
        summary={'component_hypotheses_reused':len(components),
                 'waveform_like_visual_candidates':shape_like,
                 'ratings_ocr_candidates':ratings,
                 'geometric_terminal_leads':terminal_count,
                 'ambiguous_terminals':ambiguous,
                 'focused_rating_ocr_attempts':ocr_attempts,
                 'older_stages_rerun':0,
                 'electrically_verified_connections':0,
                 'input_fingerprint':fingerprint,
                 'cached_independent_ocr_available':bool(independent_id),
                 'warning':'Visual hypotheses only. No electrical verification or confirmed connector pinouts.'}
        run_id=uuid.uuid4().hex
        cursor=db.execute(
            'INSERT OR IGNORE INTO trace_runs_v0317(id,diagram_id,component_run_id,input_fingerprint,summary_json) VALUES(?,?,?,?,?)',
            (run_id,diagram_id,comp_id,fingerprint,json.dumps(summary)))
        if cursor.rowcount==0:
            stored=db.execute(
                'SELECT summary_json FROM trace_runs_v0317 WHERE diagram_id=? AND input_fingerprint=?',
                (diagram_id,fingerprint)).fetchone()
            return dict(json.loads(stored['summary_json']),cache_hit=True,older_stages_rerun=0)
        db.executemany("""
            INSERT INTO trace_items_v0317
            (id,run_id,component_id,fuse_label,shape_status,shape_evidence_json,
             rating_text,rating_status,rating_raw,terminal_text,terminal_circle_id,
             terminal_ocr_confidence,trace_status,trace_reason,trace_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,[(row[0],run_id,*row[1:]) for row in rows])
        db.commit()
        return dict(summary,run_id=run_id,cache_hit=False)

def latest(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        db.executescript(SCHEMA)
        run=db.execute('SELECT * FROM trace_runs_v0317 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                       (diagram_id,)).fetchone()
        if not run:return {'run':None,'items':[]}
        reviews={r['component_id']:dict(r) for r in db.execute(
            'SELECT * FROM trace_reviews_v0317 WHERE diagram_id=?',(diagram_id,))}
        items=[]
        for row in db.execute('SELECT * FROM trace_items_v0317 WHERE run_id=? ORDER BY fuse_label',(run['id'],)):
            item=dict(row)
            item['shape_evidence']=json.loads(item.pop('shape_evidence_json'))
            item['rating_raw']=json.loads(item['rating_raw'])
            item['trace']=json.loads(item.pop('trace_json'))
            review=reviews.get(item['component_id'])
            item['human_review']=review['review_status'] if review else 'needs_review'
            item['human_rating']=review['rating_override'] if review else None
            item['display_rating']=item['human_rating'] or item['rating_text']
            item['electrically_verified']=False
            items.append(item)
        return {'run':dict(id=run['id'],**json.loads(run['summary_json']),
                           visual_reviewed_symbols=sum(x['human_review']=='confirmed_fuse_symbol' for x in items)),
                'items':items}

def review(dbpath,diagram_id,component_id,review_status,rating_override=None):
    if review_status not in ('needs_review','confirmed_fuse_symbol','rejected_not_fuse'):
        raise ValueError('invalid visual review status')
    if rating_override not in (None,'') and normalize_rating(rating_override) not in RATINGS:
        raise ValueError('manual rating must be a valid ampere rating, e.g. 10A')
    rating=normalize_rating(rating_override) if rating_override else None
    with sqlite3.connect(dbpath) as db:
        db.executescript(SCHEMA)
        if not db.execute(
            """SELECT 1 FROM component_items_v0316 c
               JOIN component_runs_v0316 r ON r.id=c.run_id
               WHERE c.id=? AND r.diagram_id=?""",(component_id,diagram_id)).fetchone():
            raise ValueError('component does not belong to selected diagram')
        db.execute("""
          INSERT INTO trace_reviews_v0317(component_id,diagram_id,review_status,rating_override)
          VALUES(?,?,?,?)
          ON CONFLICT(component_id) DO UPDATE SET
          review_status=excluded.review_status,
          rating_override=excluded.rating_override,
          updated_at=CURRENT_TIMESTAMP
        """,(component_id,diagram_id,review_status,rating))
        db.commit()
    return {'component_id':component_id,'human_visual_review':review_status,
            'human_rating':rating,'electrically_verified':False}

"""v0.3.6 experimental endpoint OCR, connector-column proximity and evidence.
Never certifies terminal-to-connector wiring.
"""
import json,sqlite3,uuid,re,math
from pathlib import Path
SCHEMA="""
CREATE TABLE IF NOT EXISTS terminal_runs_v036(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,association_run_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terminal_candidates_v036(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,association_id TEXT NOT NULL,fuse_label TEXT NOT NULL,terminal_text TEXT,connector_label TEXT,endpoint_x REAL NOT NULL,endpoint_y REAL NOT NULL,ocr_confidence REAL NOT NULL DEFAULT 0,reason TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'ocr_visual_candidate_unverified');
"""
CONNECTOR=re.compile(r'^[EGL]\s?\d{3}$',re.I)
TERMINAL=re.compile(r'^(?:[1-9]|[1-3][0-9])$')
def column_candidate(headers,x,threshold=.028):
 """Find unambiguous connector header at approximately the same x coordinate."""
 nearby=sorted(((abs((h['x']+h['w']/2)-x),h) for h in headers if CONNECTOR.fullmatch(h['label'].strip())),key=lambda z:z[0])
 if not nearby or nearby[0][0]>threshold:return None
 if len(nearby)>1 and nearby[1][0]-nearby[0][0]<.008:return None
 return nearby[0][1]['label'].replace(' ','').upper()
def endpoint(edges):
 """Rightmost geometric endpoint. Not an electrical terminal."""
 if not edges:return None
 e=max(edges,key=lambda e:max(e['x1'],e['x2']))
 return (max(e['x1'],e['x2']),(e['y1']+e['y2'])/2)
def crop_ocr(image,x,y):
 """Multi-scale OCR for a small endpoint region; returns text, OCR confidence, note."""
 try:
  from PIL import Image,ImageOps,ImageEnhance,ImageFilter
  import pytesseract
  from pytesseract import Output
 except ImportError:return None,0.,'Pillow/pytesseract unavailable'
 try:
  with Image.open(image) as im:
   im=im.convert('L');w,h=im.size
   # Endpoints may stop before terminal labels. Search a narrow region to the right.
   l=max(0,int((x-.025)*w));r=min(w,int((x+.065)*w))
   t=max(0,int((y-.022)*h));b=min(h,int((y+.022)*h))
   if r-l<5 or b-t<5:return None,0.,'crop too small'
   crop=im.crop((l,t,r,b));crop=ImageOps.autocontrast(crop).resize((crop.width*4,crop.height*4))
   crop=ImageEnhance.Contrast(crop).enhance(2.0).filter(ImageFilter.SHARPEN)
   best=None
   for psm in (6,11):
    data=pytesseract.image_to_data(crop,config=f'--psm {psm} -c tessedit_char_whitelist=0123456789()',output_type=Output.DICT)
    for txt,conf in zip(data['text'],data['conf']):
     txt=txt.strip().strip('()')
     if not TERMINAL.fullmatch(txt):continue
     try:score=float(conf)/100
     except (TypeError,ValueError):continue
     if score>=.40 and (best is None or score>best[1]):best=(txt,score)
   return (best[0],round(best[1],3),'endpoint-region OCR only') if best else (None,0.,'no confident digit in endpoint crop')
 except Exception as e:return None,0.,'OCR unavailable: '+type(e).__name__
def build(dbpath,diagram_id,image_path):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  ar=db.execute('SELECT * FROM association_runs_v035 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not ar:raise ValueError('Run Find candidate circuits first')
  sr=db.execute('SELECT * FROM segment_runs_v034 WHERE id=?',(ar['segment_run_id'],)).fetchone()
  gr=db.execute('SELECT * FROM graph_runs_v033 WHERE id=?',(sr['graph_run_id'],)).fetchone()
  headers=[dict(x) for x in db.execute("SELECT * FROM auto_candidates_v032 WHERE run_id=? AND kind='ocr_connector'",(gr['source_run_id'],))]
  edges={x['source_edge_id']:dict(x) for x in db.execute("SELECT * FROM segment_edges_v034 WHERE run_id=? AND classification='candidate_wire'",(sr['id'],))}
  associations=[dict(x) for x in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=?',(ar['id'],))]
  rid=uuid.uuid4().hex;rows=[];notes=[]
  for a in associations:
   matched=[edges[eid] for eid in json.loads(a['edge_ids_json']) if eid in edges]
   xy=endpoint(matched)
   if not xy:continue
   x,y=xy
   # Existing OCR evidence from v0.3.5 is retained, but not treated as verified.
   term=a['terminal_text'];conf=0.;reason='Existing full-image OCR terminal candidate; visual proximity only'
   if not term:
    term,conf,reason=crop_ocr(image_path,x,y)
   connector=column_candidate(headers,x)
   if connector:reason+='; nearest OCR connector header by x coordinate only'
   else:reason+='; no unambiguous connector column'
   rows.append((uuid.uuid4().hex,rid,a['id'],a['label'],term,connector,x,y,conf,reason))
  summary=dict(fuse_candidates_examined=len(associations),terminal_candidates=sum(bool(x[4]) for x in rows),connector_column_candidates=sum(bool(x[5]) for x in rows),electrically_verified_connections=0,warning='Endpoint crops and x-alignment are heuristics. No verified terminal-pin mapping or electrical connection.')
  db.execute('INSERT INTO terminal_runs_v036(id,diagram_id,association_run_id,summary_json) VALUES(?,?,?,?)',(rid,diagram_id,ar['id'],json.dumps(summary)))
  db.executemany('INSERT INTO terminal_candidates_v036(id,run_id,association_id,fuse_label,terminal_text,connector_label,endpoint_x,endpoint_y,ocr_confidence,reason) VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM terminal_runs_v036 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,candidates=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),candidates=[dict(x) for x in db.execute('SELECT * FROM terminal_candidates_v036 WHERE run_id=?',(r['id'],))])

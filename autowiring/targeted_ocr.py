"""Targeted OCR evidence near unmatched fuse endpoints; no auto-association."""
import sqlite3,json,uuid
SCHEMA="""
CREATE TABLE IF NOT EXISTS targeted_ocr_runs_v0314(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS targeted_ocr_items_v0314(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,fuse_label TEXT NOT NULL,endpoint_x REAL NOT NULL,endpoint_y REAL NOT NULL,psm INTEGER NOT NULL,scale INTEGER NOT NULL,raw_text TEXT NOT NULL);
"""
def scan(image_path,points):
 try:
  from PIL import Image,ImageOps,ImageEnhance
  import pytesseract
 except ImportError as exc:raise ValueError('Pillow and pytesseract required') from exc
 out=[]
 with Image.open(image_path) as src:
  im=src.convert('L');w,h=im.size
  for label,x,y in points:
   # Focus on a small region around each unmatched endpoint.
   left=max(0,int((x-.075)*w));right=min(w,int((x+.075)*w))
   top=max(0,int((y-.045)*h));bottom=min(h,int((y+.045)*h))
   if right<=left or bottom<=top:continue
   crop=ImageOps.autocontrast(im.crop((left,top,right,bottom)))
   for scale in (2,4):
    enlarged=ImageEnhance.Contrast(crop.resize((crop.width*scale,crop.height*scale))).enhance(1.5)
    for psm in (6,11,12):
     raw=pytesseract.image_to_string(enlarged,config=f'--psm {psm}').strip()
     out.append((label,x,y,psm,scale,raw[:1200]))
 return out
def build(dbpath,diagram_id,image_path):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  dr=db.execute('SELECT id FROM match_diagnostic_runs_v0313 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not dr:raise ValueError('Run Diagnose terminal matches first')
  points=[(r['fuse_label'],r['endpoint_x'],r['endpoint_y']) for r in db.execute("SELECT fuse_label,endpoint_x,endpoint_y FROM match_diagnostic_items_v0313 WHERE run_id=? AND reason!='geometric_row_candidate_only' AND endpoint_x IS NOT NULL",(dr['id'],))]
  results=scan(image_path,points);rid=uuid.uuid4().hex
  summary=dict(unmatched_endpoints=len(points),ocr_attempts=len(results),nonempty_reads=sum(bool(z[-1]) for z in results),electrically_verified_connections=0,warning='Raw OCR text for visual review only; not terminal assignments.')
  db.execute('INSERT INTO targeted_ocr_runs_v0314(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO targeted_ocr_items_v0314 VALUES(?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,*z) for z in results]);db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM targeted_ocr_runs_v0314 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,items=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),items=[dict(x) for x in db.execute('SELECT * FROM targeted_ocr_items_v0314 WHERE run_id=?',(r['id'],))])

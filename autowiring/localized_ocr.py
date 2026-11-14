"""Targeted tile OCR for missing A/B CONT labels; suggestions only."""
import sqlite3,json,uuid
SCHEMA="""
CREATE TABLE IF NOT EXISTS localized_ocr_runs_v0312(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS localized_ocr_items_v0312(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,label TEXT NOT NULL,x REAL,y REAL,w REAL,h REAL,confidence REAL,reason TEXT NOT NULL);
"""
def scan(image_path):
 try:
  from PIL import Image,ImageOps,ImageEnhance
  import pytesseract
  from pytesseract import Output
 except ImportError as e:raise ValueError('Pillow and pytesseract required') from e
 found=[]
 with Image.open(image_path) as im:
  im=im.convert('L');width,height=im.size
  # Overlapping tiles prevent missing words at crop boundaries.
  for row in range(4):
   for col in range(4):
    x0=max(0,int((col/4-.025)*width));y0=max(0,int((row/4-.025)*height))
    x1=min(width,int(((col+1)/4+.025)*width));y1=min(height,int(((row+1)/4+.025)*height))
    crop=ImageEnhance.Contrast(ImageOps.autocontrast(im.crop((x0,y0,x1,y1))).resize(((x1-x0)*2,(y1-y0)*2))).enhance(1.6)
    for psm in (6,11):
     data=pytesseract.image_to_data(crop,config=f'--psm {psm}',output_type=Output.DICT)
     words=[]
     for i,raw in enumerate(data['text']):
      t=raw.strip().upper()
      try:conf=float(data['conf'][i])/100
      except (TypeError,ValueError):continue
      if conf<.35 or not t:continue
      words.append((t,conf,(x0+data['left'][i]/2)/width,(y0+data['top'][i]/2)/height,data['width'][i]/2/width,data['height'][i]/2/height))
     for i,w in enumerate(words):
      tokens=[w]
      if i+1<len(words):tokens.append(words[i+1])
      if i+2<len(words):tokens.append(words[i+2])
      text=''.join(t[0] for t in tokens).replace('/','').replace('.','').replace('-','')
      if text in ('AB','ABCONT') and min(t[1] for t in tokens)>=.35:
       x=min(t[2] for t in tokens);y=min(t[3] for t in tokens)
       found.append(dict(label='A/B CONT' if text=='ABCONT' else 'A/B',x=x,y=y,w=max(t[2]+t[4] for t in tokens)-x,h=max(t[3]+t[5] for t in tokens)-y,confidence=round(min(t[1] for t in tokens),3),reason='localized tile OCR; visual verification required'))
 dedup=[]
 for c in sorted(found,key=lambda x:-x['confidence']):
  if not any(abs(c['x']-z['x'])<.018 and abs(c['y']-z['y'])<.018 for z in dedup):dedup.append(c)
 return dedup
def build(dbpath,diagram_id,image_path):
 rows=scan(image_path);rid=uuid.uuid4().hex
 with sqlite3.connect(dbpath) as db:
  db.executescript(SCHEMA)
  summary=dict(ocr_suggestions=len(rows),electrically_verified_connections=0,warning='Tile OCR suggestions only, NOT auto-associated to wires.')
  db.execute('INSERT INTO localized_ocr_runs_v0312(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO localized_ocr_items_v0312(id,run_id,label,x,y,w,h,confidence,reason) VALUES(?,?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,x['label'],x['x'],x['y'],x['w'],x['h'],x['confidence'],x['reason']) for x in rows])
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM localized_ocr_runs_v0312 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,items=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),items=[dict(x) for x in db.execute('SELECT * FROM localized_ocr_items_v0312 WHERE run_id=?',(r['id'],))])

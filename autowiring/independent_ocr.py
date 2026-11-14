"""Independent circle OCR audit. Does not assert circuit or connector continuity."""
import sqlite3,json,uuid,math
from autowiring.circle_detection import detect,read_inside
SCHEMA="""
CREATE TABLE IF NOT EXISTS independent_runs_v039(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS independent_circles_v039(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,r REAL NOT NULL,ocr_text TEXT,ocr_confidence REAL NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL);
"""
def scan_circles(circles,image,reader=read_inside):
 rows=[]
 for c in circles:
  number,conf,reason=reader(image,c)
  status='ocr_read_unassociated' if number else 'ocr_unread'
  rows.append(dict(x=c['x'],y=c['y'],r=c['r'],ocr_text=number,ocr_confidence=conf,status=status,reason=reason))
 return rows
def build(dbpath,diagram_id,image_path):
 circles,image=detect(image_path)
 rows=scan_circles(circles,image)
 summary=dict(detected_circles=len(rows),ocr_read=sum(bool(r['ocr_text']) for r in rows),ocr_unread=sum(not r['ocr_text'] for r in rows),electrically_verified_connections=0,warning='Independent OCR reads are NOT fuse-terminal associations or verified electrical connections.')
 rid=uuid.uuid4().hex
 with sqlite3.connect(dbpath) as db:
  db.executescript(SCHEMA)
  db.execute('INSERT INTO independent_runs_v039(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO independent_circles_v039(id,run_id,x,y,r,ocr_text,ocr_confidence,status,reason) VALUES(?,?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,r['x'],r['y'],r['r'],r['ocr_text'],r['ocr_confidence'],r['status'],r['reason']) for r in rows])
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM independent_runs_v039 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,circles=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),circles=[dict(x) for x in db.execute('SELECT * FROM independent_circles_v039 WHERE run_id=? ORDER BY y,x',(r['id'],))])

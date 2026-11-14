"""v0.3.8 audit trail for every detected circle and each fuse endpoint.
All classifications are geometric hypotheses, never verified wiring.
"""
import sqlite3,json,uuid,math
from autowiring.circle_detection import detect,read_inside
SCHEMA="""
CREATE TABLE IF NOT EXISTS evidence_runs_v038(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,circle_run_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence_circles_v038(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,r REAL NOT NULL,ocr_text TEXT,ocr_confidence REAL NOT NULL,nearest_fuse TEXT,endpoint_distance REAL,status TEXT NOT NULL,reason TEXT NOT NULL);
"""
def rank_circle(circle,endpoints,threshold=.026,tie=.007):
 distances=sorted(((math.hypot(circle['x']-e['endpoint_x'],circle['y']-e['endpoint_y']),e) for e in endpoints),key=lambda z:z[0])
 if not distances:return None,None,'no_candidate_endpoints'
 if distances[0][0]>threshold:return None,round(distances[0][0],5),'too_far_from_endpoint'
 if len(distances)>1 and distances[1][0]-distances[0][0]<tie:return None,round(distances[0][0],5),'ambiguous_nearest_endpoint'
 return distances[0][1]['fuse_label'],round(distances[0][0],5),'nearest_endpoint_only'
def build(dbpath,diagram_id,image_path):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  cr=db.execute('SELECT * FROM circle_runs_v037 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not cr:raise ValueError('Run Detect terminal circles & OCR first')
  tr=db.execute('SELECT * FROM terminal_runs_v036 WHERE id=?',(cr['terminal_run_id'],)).fetchone()
  if not tr:raise ValueError('Terminal run not found')
  endpoints=[dict(r) for r in db.execute('SELECT * FROM terminal_candidates_v036 WHERE run_id=?',(tr['id'],))]
  circles,im=detect(image_path);rid=uuid.uuid4().hex;rows=[];status_counts={}
  for c in circles:
   label,distance,reason=rank_circle(c,endpoints)
   # OCR only circles near a unique fuse endpoint; avoids expensive OCR of all 93.
   number,conf,note=read_inside(im,c) if label else (None,0.,'not OCR tested')
   status='ocr_match_unverified' if number else ('near_endpoint_no_ocr' if label else reason)
   status_counts[status]=status_counts.get(status,0)+1
   rows.append((uuid.uuid4().hex,rid,c['x'],c['y'],c['r'],number,conf,label,distance,status,reason+'; '+note))
  summary=dict(detected_circles=len(circles),status_counts=status_counts,ocr_matches=status_counts.get('ocr_match_unverified',0),electrically_verified_connections=0,warning='OCR and nearest-endpoint matches are unverified visual evidence; no reconstructed electrical continuity.')
  db.execute('INSERT INTO evidence_runs_v038(id,diagram_id,circle_run_id,summary_json) VALUES(?,?,?,?)',(rid,diagram_id,cr['id'],json.dumps(summary)))
  db.executemany('INSERT INTO evidence_circles_v038(id,run_id,x,y,r,ocr_text,ocr_confidence,nearest_fuse,endpoint_distance,status,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM evidence_runs_v038 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,circles=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),circles=[dict(x) for x in db.execute('SELECT * FROM evidence_circles_v038 WHERE run_id=? ORDER BY status,x,y',(r['id'],))])

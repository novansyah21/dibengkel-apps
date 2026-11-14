"""v0.3.7 strict circle-first OCR evidence. No electrical connectivity inferred."""
import sqlite3,json,uuid,math,re
SCHEMA="""
CREATE TABLE IF NOT EXISTS circle_runs_v037(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,terminal_run_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS circle_candidates_v037(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,fuse_label TEXT NOT NULL,association_id TEXT NOT NULL,terminal_text TEXT,circle_x REAL NOT NULL,circle_y REAL NOT NULL,circle_r REAL NOT NULL,endpoint_distance REAL NOT NULL,ocr_confidence REAL NOT NULL,verification TEXT NOT NULL DEFAULT 'circle_ocr_candidate_unverified',reason TEXT NOT NULL);
"""
def match_circles(circles,endpoint_x,endpoint_y,max_distance=.026):
 """Return closest uniquely matched circle to segment endpoint, or None."""
 ranked=sorted(((math.hypot(c['x']-endpoint_x,c['y']-endpoint_y),c) for c in circles),key=lambda v:v[0])
 if not ranked or ranked[0][0]>max_distance:return None
 if len(ranked)>1 and ranked[1][0]-ranked[0][0]<.007:return None
 return ranked[0]
def detect(image_path):
 try:
  import cv2,numpy as np
 except ImportError:raise ValueError('OpenCV/numpy required for circle detection')
 im=cv2.imread(str(image_path),cv2.IMREAD_GRAYSCALE)
 if im is None:raise ValueError('Cannot read local diagram image')
 h,w=im.shape
 blur=cv2.medianBlur(im,5)
 # Typical small terminal circle radii ~6–15 px on the source diagram.
 circles=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,dp=1.2,minDist=12,param1=120,param2=19,minRadius=5,maxRadius=19)
 if circles is None:return [],im
 result=[]
 for x,y,r in np.round(circles[0]).astype(int):
  if 0<x<w and 0<y<h:result.append(dict(x=x/w,y=y/h,r=r/max(w,h),px=int(x),py=int(y),pr=int(r)))
 return result,im
def read_inside(im,circle):
 try:
  import pytesseract,cv2
  from pytesseract import Output
 except ImportError:return None,0.,'pytesseract unavailable'
 x,y,r=circle['px'],circle['py'],circle['pr']
 # Restrict crop to INSIDE circle; remove border pixels.
 pad=max(2,int(r*.72));h,w=im.shape
 x1=max(0,x-pad);x2=min(w,x+pad);y1=max(0,y-pad);y2=min(h,y+pad)
 if x2-x1<4 or y2-y1<4:return None,0.,'circle crop too small'
 crop=im[y1:y2,x1:x2]
 crop=cv2.resize(crop,None,fx=6,fy=6,interpolation=cv2.INTER_CUBIC)
 crop=cv2.threshold(crop,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
 best=None
 for psm in (10,8):
  try:
   data=pytesseract.image_to_data(crop,config=f'--psm {psm} -c tessedit_char_whitelist=0123456789',output_type=Output.DICT)
   for t,conf in zip(data['text'],data['conf']):
    if not re.fullmatch(r'(?:[1-9]|[1-3][0-9])',t.strip()):continue
    score=float(conf)/100
    if score>=.60 and (best is None or score>best[1]):best=(t.strip(),score)
  except Exception:return None,0.,'Tesseract unavailable'
 return (best[0],round(best[1],3),'OCR strictly inside detected circle') if best else (None,0.,'no confident OCR inside circle')
def build(dbpath,diagram_id,image_path):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  tr=db.execute('SELECT * FROM terminal_runs_v036 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not tr:raise ValueError('Run v0.3.6 terminal detection first')
  candidates=[dict(x) for x in db.execute('SELECT * FROM terminal_candidates_v036 WHERE run_id=?',(tr['id'],))]
  circles,im=detect(image_path);rid=uuid.uuid4().hex;rows=[]
  for c in candidates:
   hit=match_circles(circles,c['endpoint_x'],c['endpoint_y'])
   if not hit:continue
   distance,circle=hit
   number,conf,note=read_inside(im,circle)
   if not number:continue
   rows.append((uuid.uuid4().hex,rid,c['fuse_label'],c['association_id'],number,circle['x'],circle['y'],circle['r'],distance,conf,'Detected circle + endpoint proximity; '+note+'; no connector ownership or electrical continuity inferred'))
  summary=dict(detected_circles=len(circles),matched_terminal_candidates=len(rows),rejected_or_unmatched=len(candidates)-len(rows),electrically_verified_connections=0,warning='Circle and OCR are visual evidence only; not validated connector pinout.')
  db.execute('INSERT INTO circle_runs_v037(id,diagram_id,terminal_run_id,summary_json) VALUES(?,?,?,?)',(rid,diagram_id,tr['id'],json.dumps(summary)))
  db.executemany('INSERT INTO circle_candidates_v037(id,run_id,fuse_label,association_id,terminal_text,circle_x,circle_y,circle_r,endpoint_distance,ocr_confidence,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM circle_runs_v037 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,candidates=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),candidates=[dict(x) for x in db.execute('SELECT * FROM circle_candidates_v037 WHERE run_id=?',(r['id'],))])

"""Conservative, local-first CV/OCR proposals. NEVER infers verified electrical continuity."""
import json,sqlite3,uuid,re,hashlib
from pathlib import Path

SCHEMA="""
CREATE TABLE IF NOT EXISTS auto_runs_v032(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,image_sha256 TEXT NOT NULL,ocr_available INTEGER NOT NULL,cv_available INTEGER NOT NULL,ocr_count INTEGER NOT NULL,line_count INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,notes TEXT);
CREATE TABLE IF NOT EXISTS auto_candidates_v032(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,diagram_id TEXT NOT NULL,kind TEXT NOT NULL,label TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,w REAL NOT NULL,h REAL NOT NULL,confidence REAL NOT NULL,source TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'machine_candidate_unverified',extra_json TEXT NOT NULL DEFAULT '{}',FOREIGN KEY(run_id) REFERENCES auto_runs_v032(id));
CREATE INDEX IF NOT EXISTS idx_auto_candidates_diagram ON auto_candidates_v032(diagram_id);
"""
CONNECTOR=re.compile(r'\b(?:E|G|L)\s?\d{3}\b',re.I)
FUSE=re.compile(r'\b(?:\d{1,2}\s?A|IG\s?COIL|ABS|BACK|MTR|IG1\s?SIG)\b',re.I)

def classify(text):
 text=' '.join(text.split()).strip()
 if not text:return 'text'
 if CONNECTOR.fullmatch(text):return 'connector'
 if FUSE.search(text):return 'fuse_label'
 if re.fullmatch(r'\d{1,2}',text):return 'terminal_number_candidate'
 return 'text'

def extract(image_path,diagram_id,dbpath,ocr=True,lines=True,max_candidates=450):
 from PIL import Image
 image_path=Path(image_path)
 with Image.open(image_path) as im:
  im.verify()
 with Image.open(image_path) as im:
  im=im.convert('RGB');width,height=im.size
 digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
 candidates=[];notes=[];ocr_ok=False;cv_ok=False
 if ocr:
  try:
   import pytesseract
   from pytesseract import Output
   data=pytesseract.image_to_data(im,config='--psm 11',output_type=Output.DICT)
   ocr_ok=True
   for i,t in enumerate(data['text']):
    t=' '.join(t.split()).strip()
    try:conf=float(data['conf'][i])/100
    except (ValueError,TypeError):continue
    if not t or conf<0.35:continue
    x,y,w,h=(int(data[k][i]) for k in ('left','top','width','height'))
    if w<=0 or h<=0:continue
    candidates.append(('ocr_'+classify(t),t,x/width,y/height,w/width,h/height,round(conf,3),'tesseract',{}))
  except (ImportError,FileNotFoundError) as e:notes.append('OCR unavailable: install pytesseract and Tesseract executable ('+type(e).__name__+')')
  except Exception as e:notes.append('OCR failed: '+type(e).__name__+': '+str(e)[:180])
 if lines:
  try:
   import cv2,numpy as np
   gray=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2GRAY)
   binary=cv2.threshold(gray,180,255,cv2.THRESH_BINARY_INV)[1]
   hor=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(18,width//45),1)))
   ver=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(18,height//45))))
   segments=[]
   for axis,mask in [('horizontal',hor),('vertical',ver)]:
    n,lab,stats,centroids=cv2.connectedComponentsWithStats(mask,8)
    for x,y,w,h,area in stats[1:]:
     if (axis=='horizontal' and w<max(24,width//40)) or (axis=='vertical' and h<max(24,height//40)):continue
     if area<15:continue
     segments.append((axis,int(x),int(y),int(w),int(h),int(area)))
   segments.sort(key=lambda s:-s[5]);cv_ok=True
   for axis,x,y,w,h,area in segments[:max_candidates//2]:
    candidates.append(('line_segment_candidate',axis,x/width,y/height,w/width,h/height,0.45,'opencv_morphology',{'orientation':axis,'pixel_area':area,'connectivity':'unknown'}))
  except ImportError:notes.append('CV unavailable: install opencv-python and numpy')
  except Exception as e:notes.append('CV failed: '+type(e).__name__+': '+str(e)[:180])
 # Store proposals separately: NEVER populate verified connectors, terminals, paths, or circuit links.
 with sqlite3.connect(dbpath) as db:
  db.executescript(SCHEMA)
  run=uuid.uuid4().hex
  db.execute('INSERT INTO auto_runs_v032(id,diagram_id,image_sha256,ocr_available,cv_available,ocr_count,line_count,notes) VALUES(?,?,?,?,?,?,?,?)',(run,diagram_id,digest,int(ocr_ok),int(cv_ok),sum(x[0].startswith('ocr_') for x in candidates),sum(x[0]=='line_segment_candidate' for x in candidates),' | '.join(notes)))
  for kind,label,x,y,w,h,conf,source,extra in candidates[:max_candidates]:
   db.execute('INSERT INTO auto_candidates_v032(id,run_id,diagram_id,kind,label,x,y,w,h,confidence,source,extra_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,run,diagram_id,kind,label,x,y,w,h,conf,source,json.dumps(extra)))
  db.commit()
 return {'run_id':run,'diagram_id':diagram_id,'ocr_available':ocr_ok,'cv_available':cv_ok,'candidates':min(len(candidates),max_candidates),'notes':notes,'status':'proposals_only_not_verified_connections'}

"""Audit missing fuse labels and segment association without inventing connections."""
import sqlite3,json,uuid,re,math
SCHEMA="""
CREATE TABLE IF NOT EXISTS fuse_audit_runs_v0311(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fuse_audit_items_v0311(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,label TEXT NOT NULL,source_text TEXT NOT NULL,x REAL,y REAL,status TEXT NOT NULL,reason TEXT NOT NULL,edge_ids_json TEXT NOT NULL);
"""
PATTERNS={'IG COIL':re.compile(r'IG\s*COIL',re.I),'A/B':re.compile(r'A\s*[/\\]?\s*B(?:\s*CONT)?',re.I),'MTR':re.compile(r'\bMTR\b',re.I),'ABS':re.compile(r'\bABS\b',re.I),'BACK':re.compile(r'\bBACK\b',re.I)}
def canonical(text):
 t=re.sub(r'[^A-Z0-9/]','',text.upper())
 for label,pattern in [('IG COIL',r'IGCOIL'),('A/B',r'AB(?:CONT)?'),('MTR',r'MTR'),('ABS',r'ABS'),('BACK',r'BACK')]:
  if re.fullmatch(pattern,t):return label
 return None
def audit(labels,edges,associations):
 """Report direct OCR and adjacent token combinations, with conservative segment candidates."""
 found=[]
 for c in labels:
  if not c['kind'].startswith('ocr_'):continue
  name=canonical(c['label'])
  if name:found.append((name,c['label'],c['x'],c['y'],c['w'],c['h'],'direct_ocr'))
 # OCR can split IG / COIL and A/B / CONT into adjacent boxes.
 words=[c for c in labels if c['kind'].startswith('ocr_')]
 for a in words:
  for z in words:
   if a['id']==z['id']:continue
   ay=a['y']+a['h']/2;zy=z['y']+z['h']/2
   if abs(ay-zy)>.012 or not (a['x']<z['x']<=a['x']+a['w']+.035):continue
   name=canonical(a['label']+' '+z['label'])
   if name and name in ('IG COIL','A/B'):
    found.append((name,a['label']+' '+z['label'],a['x'],min(a['y'],z['y']),z['x']+z['w']-a['x'],max(a['h'],z['h']),'adjacent_ocr_tokens'))
 seen=set();results=[]
 for name,raw,x,y,w,h,source in found:
  key=(name,round(x,3),round(y,3))
  if key in seen:continue
  seen.add(key)
  cx=x+w/2;cy=y+h/2
  nearby=[]
  for e in edges:
   if e['classification']!='candidate_wire' or abs(e['x2']-e['x1'])<abs(e['y2']-e['y1']):continue
   left=min(e['x1'],e['x2']);right=max(e['x1'],e['x2'])
   dx=max(left-cx,0,cx-right);dy=abs((e['y1']+e['y2'])/2-cy)
   dist=math.hypot(dx,dy)
   if dist<=.035:nearby.append((dist,e))
  nearby.sort(key=lambda p:p[0])
  close=[e['source_edge_id'] for d,e in nearby if d<=min(.035,(nearby[0][0]+.009 if nearby else 0))]
  associated=any(canonical(a['label'])==name for a in associations)
  status='already_associated' if associated else ('missing_association_candidate' if close else 'no_nearby_wire')
  results.append(dict(label=name,source_text=raw,x=x,y=y,status=status,reason=source+'; '+str(len(close))+' nearby horizontal segments; no electrical continuity implied',edge_ids=close))
 return results
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  sr=db.execute('SELECT * FROM segment_runs_v034 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not sr:raise ValueError('Run Segment & group paths first')
  gr=db.execute('SELECT source_run_id FROM graph_runs_v033 WHERE id=?',(sr['graph_run_id'],)).fetchone()
  labels=[dict(x) for x in db.execute('SELECT * FROM auto_candidates_v032 WHERE run_id=?',(gr['source_run_id'],))]
  edges=[dict(x) for x in db.execute('SELECT * FROM segment_edges_v034 WHERE run_id=?',(sr['id'],))]
  ar=db.execute('SELECT id FROM association_runs_v035 WHERE segment_run_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(sr['id'],)).fetchone()
  associations=[dict(x) for x in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=?',(ar['id'],))] if ar else []
  rows=audit(labels,edges,associations);rid=uuid.uuid4().hex
  summary=dict(labels_audited=len(rows),missing_association_candidates=sum(x['status']=='missing_association_candidate' for x in rows),without_nearby_wire=sum(x['status']=='no_nearby_wire' for x in rows),electrically_verified_connections=0,warning='Audit only. No paths are added or treated as verified.')
  db.execute('INSERT INTO fuse_audit_runs_v0311(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO fuse_audit_items_v0311(id,run_id,label,source_text,x,y,status,reason,edge_ids_json) VALUES(?,?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,x['label'],x['source_text'],x['x'],x['y'],x['status'],x['reason'],json.dumps(x['edge_ids'])) for x in rows])
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM fuse_audit_runs_v0311 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,items=[])
  items=[dict(x) for x in db.execute('SELECT * FROM fuse_audit_items_v0311 WHERE run_id=?',(r['id'],))]
  for x in items:x['edge_ids']=json.loads(x.pop('edge_ids_json'))
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),items=items)

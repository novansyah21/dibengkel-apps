"""v0.3.5: evidence-linked candidate circuits. Never infer verified connectivity."""
import json,math,re,sqlite3,uuid
SCHEMA="""
CREATE TABLE IF NOT EXISTS association_runs_v035(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,segment_run_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS association_candidates_v035(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,diagram_id TEXT NOT NULL,label_id TEXT NOT NULL,label TEXT NOT NULL,kind TEXT NOT NULL,edge_ids_json TEXT NOT NULL,terminal_text TEXT,terminal_candidate_id TEXT,terminal_distance REAL,score REAL NOT NULL,reason TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'visual_proximity_unverified');
CREATE INDEX IF NOT EXISTS idx_association_run ON association_candidates_v035(run_id);
"""
FUSE_RE=re.compile(r'^(IG\s*COIL|MTR|A/B|IG1\s*SIG|ABS|BACK)(?:\s*\d{1,2}A)?$',re.I)
TERMINAL_RE=re.compile(r'^\(?([1-9]|[1-3][0-9])\)?$')
def _dist(x,y,e):
 if abs(e['y2']-e['y1'])<=abs(e['x2']-e['x1']):
  return math.hypot(max(e['x1']-x,0,x-e['x2']),y-(e['y1']+e['y2'])/2)
 return math.hypot(x-(e['x1']+e['x2'])/2,max(e['y1']-y,0,y-e['y2']))
def _axis(e):
 return 'horizontal' if abs(e['x2']-e['x1'])>=abs(e['y2']-e['y1']) else 'vertical'
def candidates(labels,edges):
 """A label is associated with nearest horizontal candidate ONLY. Terminal OCR is optional."""
 wires=[e for e in edges if e['classification']=='candidate_wire' and _axis(e)=='horizontal']
 terminals=[c for c in labels if c['kind'] in ('ocr_text','ocr_terminal_number_candidate') and TERMINAL_RE.fullmatch(str(c['label']).strip())]
 results=[]
 for c in labels:
  if c['kind']!='ocr_fuse_label' or not FUSE_RE.match(str(c['label']).strip()):continue
  x=c['x']+c['w']/2;y=c['y']+c['h']/2
  ranked=sorted(((_dist(x,y,e),e) for e in wires),key=lambda z:z[0])
  if not ranked or ranked[0][0]>.035:continue
  distance,e=ranked[0]
  # Same-row geometric grouping is a candidate, not an electrically joined circuit.
  group=e['group_id'];same=[v for v in wires if group and v['group_id']==group]
  if not same:same=[e]
  same=sorted(same,key=lambda z:z['x1'])
  right=max(z['x2'] for z in same)
  yline=(e['y1']+e['y2'])/2
  possible=[]
  for t in terminals:
   tx=t['x']+t['w']/2;ty=t['y']+t['h']/2
   if tx<=x or tx<right-.035:continue
   dy=abs(ty-yline)
   if dy<=.018 and tx<=right+.045:possible.append((math.hypot(max(tx-right,0),dy),t))
  possible.sort(key=lambda z:z[0])
  term=possible[0] if possible and (len(possible)==1 or possible[1][0]-possible[0][0]>.007) else None
  score=round(max(.05,min(.85,.65-distance*8)),3)
  results.append(dict(label_id=c['id'],label=c['label'],kind=c['kind'],edge_ids=[v['source_edge_id'] for v in same],terminal_text=term[1]['label'] if term else None,terminal_candidate_id=term[1]['id'] if term else None,terminal_distance=round(term[0],5) if term else None,score=score,reason='Fuse OCR near horizontal geometry; same-row segments grouped by proximity. Terminal text is optional OCR proximity, NOT connector-pin identification.'))
 return results
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  run=db.execute('SELECT * FROM segment_runs_v034 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not run:raise ValueError('Run Segment & group paths first')
  edges=[dict(e) for e in db.execute('SELECT * FROM segment_edges_v034 WHERE run_id=?',(run['id'],))]
  gr=db.execute('SELECT source_run_id FROM graph_runs_v033 WHERE id=?',(run['graph_run_id'],)).fetchone()
  if not gr:raise ValueError('Source graph run missing')
  labels=[dict(c) for c in db.execute('SELECT * FROM auto_candidates_v032 WHERE run_id=?',(gr['source_run_id'],))]
  found=candidates(labels,edges);rid=uuid.uuid4().hex
  summary=dict(candidate_circuits=len(found),terminal_text_candidates=sum(bool(c['terminal_text']) for c in found),electrically_verified_connections=0,note='No electrical continuity, terminal pin, or vehicle applicability verified.')
  db.execute('INSERT INTO association_runs_v035(id,diagram_id,segment_run_id,summary_json) VALUES(?,?,?,?)',(rid,diagram_id,run['id'],json.dumps(summary)))
  db.executemany('INSERT INTO association_candidates_v035(id,run_id,diagram_id,label_id,label,kind,edge_ids_json,terminal_text,terminal_candidate_id,terminal_distance,score,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,diagram_id,c['label_id'],c['label'],c['kind'],json.dumps(c['edge_ids']),c['terminal_text'],c['terminal_candidate_id'],c['terminal_distance'],c['score'],c['reason']) for c in found])
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM association_runs_v035 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,candidates=[])
  rows=[dict(x) for x in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=? ORDER BY label',(r['id'],))]
  for x in rows:x['edge_ids']=json.loads(x.pop('edge_ids_json'))
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),candidates=rows)

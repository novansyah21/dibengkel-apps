"""v0.3.4 heuristic segmentation: all results are UNVERIFIED geometry."""
import sqlite3,json,uuid
SCHEMA="""CREATE TABLE IF NOT EXISTS segment_runs_v034(id TEXT PRIMARY KEY,diagram_id TEXT,graph_run_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT);
CREATE TABLE IF NOT EXISTS segment_edges_v034(id TEXT PRIMARY KEY,run_id TEXT,source_edge_id TEXT,region TEXT,classification TEXT,reason TEXT,x1 REAL,y1 REAL,x2 REAL,y2 REAL,group_id TEXT,verification TEXT DEFAULT 'geometric_candidate_unverified');"""
def classify(diagram_id,e):
 x1,y1,x2,y2=[e[k] for k in ('x1','y1','x2','y2')]
 if diagram_id!='junction_block':return 'full_diagram','candidate_wire','generic: no region rule'
 if (y1+y2)/2>=.865:return 'connector_layout','excluded_structural','bottom connector-layout region'
 if e['axis']=='vertical' and .46<=(x1+x2)/2<=.98 and abs(y2-y1)>=.12:return 'connector_columns','excluded_structural','long vertical column line; may exclude real wires'
 return 'main_wiring','candidate_wire','within main wiring region'
def _group(edges):
 groups=[]
 for e in sorted(edges,key=lambda a:(a['axis'],a['y1'],a['x1'])):
  fixed=e['y1'] if e['axis']=='horizontal' else e['x1'];start=e['x1'] if e['axis']=='horizontal' else e['y1'];end=e['x2'] if e['axis']=='horizontal' else e['y2']
  g=next((g for g in groups if g['axis']==e['axis'] and abs(g['fixed']-fixed)<.003 and start<=g['end']+.008 and end>=g['start']-.008),None)
  if g is None:g=dict(id=uuid.uuid4().hex,axis=e['axis'],fixed=fixed,start=start,end=end);groups.append(g)
  else:g['start']=min(g['start'],start);g['end']=max(g['end'],end)
  e['group_id']=g['id']
 return groups
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT id FROM graph_runs_v033 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:raise ValueError('Build geometry graph first')
  raw=[dict(x) for x in db.execute('SELECT * FROM graph_edges_v033 WHERE graph_run_id=?',(r['id'],))]
  kept=[]
  for e in raw:
   e['region'],e['classification'],e['reason']=classify(diagram_id,e);e['group_id']=None
   if e['classification']=='candidate_wire':kept.append(e)
  groups=_group(kept);crossings=0
  for i,a in enumerate(kept):
   for b in kept[i+1:]:
    if a['axis']==b['axis']:continue
    h,v=(a,b) if a['axis']=='horizontal' else (b,a)
    if h['x1']<=v['x1']<=h['x2'] and v['y1']<=h['y1']<=v['y2']:crossings+=1
  summary=dict(raw_segments=len(raw),candidate_wire_segments=len(kept),excluded_structural_segments=len(raw)-len(kept),candidate_groups=len(groups),remaining_ambiguous_crossings=crossings,electrically_verified_connections=0,warning='Heuristic filtering can discard real wires. Groups mean collinearity, not electrical continuity.')
  rid=uuid.uuid4().hex
  db.execute('INSERT INTO segment_runs_v034(id,diagram_id,graph_run_id,summary_json) VALUES(?,?,?,?)',(rid,diagram_id,r['id'],json.dumps(summary)))
  db.executemany('INSERT INTO segment_edges_v034(id,run_id,source_edge_id,region,classification,reason,x1,y1,x2,y2,group_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',[(uuid.uuid4().hex,rid,e['id'],e['region'],e['classification'],e['reason'],e['x1'],e['y1'],e['x2'],e['y2'],e['group_id']) for e in raw])
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM segment_runs_v034 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,edges=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),edges=[dict(e) for e in db.execute('SELECT * FROM segment_edges_v034 WHERE run_id=?',(r['id'],))])

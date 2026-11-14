"""Conservative same-row segment gap audit; NO electrical joins are created."""
import sqlite3,json,uuid,math
SCHEMA="""
CREATE TABLE IF NOT EXISTS continuity_runs_v0314(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS continuity_items_v0314(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,association_id TEXT NOT NULL,fuse_label TEXT NOT NULL,source_edge_id TEXT NOT NULL,neighbor_edge_id TEXT NOT NULL,endpoint_x REAL NOT NULL,endpoint_y REAL NOT NULL,neighbor_x REAL NOT NULL,neighbor_y REAL NOT NULL,gap REAL NOT NULL,vertical_offset REAL NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL);
"""
def right_endpoint(e):
 if e['x1']>=e['x2']:return float(e['x1']),float(e['y1'])
 return float(e['x2']),float(e['y2'])
def left_endpoint(e):
 if e['x1']<=e['x2']:return float(e['x1']),float(e['y1'])
 return float(e['x2']),float(e['y2'])
def candidates(source,edges,vertical_tolerance=.003,max_gap=.08,min_gap=.0005):
 x,y=right_endpoint(source);out=[]
 for e in edges:
  if e['source_edge_id']==source['source_edge_id']:continue
  a,b=left_endpoint(e);gap=a-x;dy=abs(b-y)
  if gap<min_gap or gap>max_gap or dy>vertical_tolerance:continue
  # Only nearly horizontal segments; never cross a vertical junction.
  if abs(e['y2']-e['y1'])>.003 or abs(source['y2']-source['y1'])>.003:continue
  out.append(dict(source_edge_id=source['source_edge_id'],neighbor_edge_id=e['source_edge_id'],endpoint_x=x,endpoint_y=y,neighbor_x=a,neighbor_y=b,gap=round(gap,6),vertical_offset=round(dy,6),status='visual_gap_requires_review',reason='collinear_nearby_segments_not_proven_connected'))
 return sorted(out,key=lambda a:(a['gap'],a['vertical_offset']))
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  ar=db.execute('SELECT * FROM association_runs_v035 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not ar:raise ValueError('Run Find candidate circuits first')
  edges=[dict(e) for e in db.execute("SELECT * FROM segment_edges_v034 WHERE run_id=? AND classification='candidate_wire'",(ar['segment_run_id'],))]
  by_id={e['source_edge_id']:e for e in edges}
  associations=[dict(a) for a in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=?',(ar['id'],))]
  rid=uuid.uuid4().hex;rows=[]
  for a in associations:
   for edge_id in json.loads(a['edge_ids_json']):
    if edge_id not in by_id:continue
    for c in candidates(by_id[edge_id],edges):
     rows.append((uuid.uuid4().hex,rid,a['id'],a['label'],c['source_edge_id'],c['neighbor_edge_id'],c['endpoint_x'],c['endpoint_y'],c['neighbor_x'],c['neighbor_y'],c['gap'],c['vertical_offset'],c['status'],c['reason']))
  summary=dict(fuse_paths=len(associations),visual_gap_suggestions=len(rows),electrically_verified_connections=0,warning='Collinear gaps are NOT bridged; inspect diagram before any connection.')
  db.execute('INSERT INTO continuity_runs_v0314(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO continuity_items_v0314 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows);db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM continuity_runs_v0314 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,items=[])
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),items=[dict(x) for x in db.execute('SELECT * FROM continuity_items_v0314 WHERE run_id=?',(r['id'],))])

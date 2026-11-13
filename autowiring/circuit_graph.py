"""Conservative geometry-only candidate graph. Crossings are NEVER assumed connected."""
import json, sqlite3, uuid, math
SCHEMA="""
CREATE TABLE IF NOT EXISTS graph_runs_v033(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,source_run_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS graph_edges_v033(id TEXT PRIMARY KEY,graph_run_id TEXT NOT NULL,diagram_id TEXT NOT NULL,axis TEXT NOT NULL,x1 REAL NOT NULL,y1 REAL NOT NULL,x2 REAL NOT NULL,y2 REAL NOT NULL,source_candidate_id TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'geometry_candidate_unverified');
CREATE TABLE IF NOT EXISTS graph_events_v033(id TEXT PRIMARY KEY,graph_run_id TEXT NOT NULL,kind TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,edge_a TEXT NOT NULL,edge_b TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'ambiguous_not_electrically_verified');
CREATE TABLE IF NOT EXISTS graph_label_links_v033(id TEXT PRIMARY KEY,graph_run_id TEXT NOT NULL,edge_id TEXT NOT NULL,label_candidate_id TEXT NOT NULL,distance REAL NOT NULL,verification TEXT NOT NULL DEFAULT 'proximity_only_unverified');
CREATE INDEX IF NOT EXISTS idx_graph_edges_run ON graph_edges_v033(graph_run_id);
"""
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  run=db.execute('SELECT id FROM auto_runs_v032 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not run:raise ValueError('Run automatic diagram analysis first')
  candidates=[dict(r) for r in db.execute('SELECT * FROM auto_candidates_v032 WHERE run_id=?',(run['id'],))]
  edges=[]
  for c in candidates:
   if c['kind']!='line_segment_candidate':continue
   axis=c['label'];x,y,w,h=[c[k] for k in ('x','y','w','h')]
   if axis=='horizontal':e=(x,y+h/2,x+w,y+h/2)
   elif axis=='vertical':e=(x+w/2,y,x+w/2,y+h)
   else:continue
   edges.append(dict(id=uuid.uuid4().hex,axis=axis,coords=e,source=c['id']))
  graph_id=uuid.uuid4().hex;events=[];links=[]
  # Geometry-only: crossing or near-endpoint are flagged ambiguous, not joined.
  for i,a in enumerate(edges):
   for b in edges[i+1:]:
    if a['axis']==b['axis']:continue
    h,v=(a,b) if a['axis']=='horizontal' else (b,a)
    hx1,hy,hx2,_=h['coords'];vx,vy1,_,vy2=v['coords']
    if hx1<=vx<=hx2 and vy1<=hy<=vy2:
     events.append((uuid.uuid4().hex,graph_id,'crossing_unknown',vx,hy,a['id'],b['id']))
  labels=[c for c in candidates if c['kind'] in ('ocr_connector','ocr_fuse_label')]
  for c in labels:
   cx=c['x']+c['w']/2;cy=c['y']+c['h']/2
   best=None
   for e in edges:
    x1,y1,x2,y2=e['coords']
    if e['axis']=='horizontal':dist=math.hypot(max(x1-cx,0,cx-x2),cy-y1)
    else:dist=math.hypot(cx-x1,max(y1-cy,0,cy-y2))
    if best is None or dist<best[0]:best=(dist,e)
   if best and best[0]<0.045:links.append((uuid.uuid4().hex,graph_id,best[1]['id'],c['id'],round(best[0],5)))
  summary={'edges':len(edges),'ambiguous_crossings':len(events),'nearby_labels':len(links),'electrically_verified_connections':0,'note':'All crossings are ambiguous; proximity is not electrical connectivity.'}
  db.execute('INSERT INTO graph_runs_v033(id,diagram_id,source_run_id,summary_json) VALUES(?,?,?,?)',(graph_id,diagram_id,run['id'],json.dumps(summary)))
  db.executemany('INSERT INTO graph_edges_v033(id,graph_run_id,diagram_id,axis,x1,y1,x2,y2,source_candidate_id) VALUES(?,?,?,?,?,?,?,?,?)',[(e['id'],graph_id,diagram_id,e['axis'],*e['coords'],e['source']) for e in edges])
  db.executemany('INSERT INTO graph_events_v033(id,graph_run_id,kind,x,y,edge_a,edge_b) VALUES(?,?,?,?,?,?,?)',events)
  db.executemany('INSERT INTO graph_label_links_v033(id,graph_run_id,edge_id,label_candidate_id,distance) VALUES(?,?,?,?,?)',links)
  db.commit()
 return {'graph_run_id':graph_id,**summary}
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  row=db.execute('SELECT * FROM graph_runs_v033 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not row:return {'run':None,'edges':[],'events':[],'label_links':[]}
  gid=row['id'];edges=[dict(x) for x in db.execute('SELECT * FROM graph_edges_v033 WHERE graph_run_id=?',(gid,))];events=[dict(x) for x in db.execute('SELECT * FROM graph_events_v033 WHERE graph_run_id=? LIMIT 1000',(gid,))]
  links=[dict(x) for x in db.execute('SELECT l.*,c.label,c.kind FROM graph_label_links_v033 l JOIN auto_candidates_v032 c ON c.id=l.label_candidate_id WHERE l.graph_run_id=?',(gid,))]
  return {'run':{'id':gid,**json.loads(row['summary_json'])},'edges':edges,'events':events,'label_links':links}

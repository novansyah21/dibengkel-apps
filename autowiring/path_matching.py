"""v0.3.10 conservative geometric fuse-to-circle hypotheses.
No junction or electrical connectivity inference.
"""
import sqlite3,json,uuid,math
SCHEMA="""
CREATE TABLE IF NOT EXISTS path_match_runs_v0310(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS path_matches_v0310(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,association_id TEXT NOT NULL,fuse_label TEXT NOT NULL,circle_id TEXT,terminal_text TEXT,ocr_confidence REAL,geometric_distance REAL,status TEXT NOT NULL,reason TEXT NOT NULL,edge_ids_json TEXT NOT NULL);
"""
def match_one(segments,circles,row_tolerance=.017,max_gap=.065,ambiguity=.008):
 """Match rightward OCR circle to rightmost end of horizontal segment group."""
 horizontal=[e for e in segments if abs(e['y2']-e['y1'])<=abs(e['x2']-e['x1'])]
 if not horizontal:return None,'no_horizontal_segment'
 right=max(max(e['x1'],e['x2']) for e in horizontal)
 ends=[e for e in horizontal if abs(max(e['x1'],e['x2'])-right)<.015]
 y=sum((e['y1']+e['y2'])/2 for e in ends)/len(ends)
 ranked=[]
 for c in circles:
  if not c.get('ocr_text'):continue
  if abs(c['y']-y)>row_tolerance:continue
  gap=c['x']-right
  if gap < -.012 or gap>max_gap:continue
  ranked.append((math.hypot(max(0,gap),c['y']-y),c))
 ranked.sort(key=lambda z:z[0])
 if not ranked:return None,'no_readable_circle_on_segment_row'
 if len(ranked)>1 and ranked[1][0]-ranked[0][0]<ambiguity:return None,'ambiguous_circle_candidates'
 return dict(circle=ranked[0][1],distance=round(ranked[0][0],5),endpoint=[round(right,5),round(y,5)]),'geometric_row_candidate_only'
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  ir=db.execute('SELECT id FROM independent_runs_v039 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  ar=db.execute('SELECT * FROM association_runs_v035 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not ir:raise ValueError('Run OCR all detected circles first')
  if not ar:raise ValueError('Run Find candidate circuits first')
  sr=db.execute('SELECT * FROM segment_runs_v034 WHERE id=?',(ar['segment_run_id'],)).fetchone()
  edges={e['source_edge_id']:dict(e) for e in db.execute("SELECT * FROM segment_edges_v034 WHERE run_id=? AND classification='candidate_wire'",(sr['id'],))}
  circles=[dict(c) for c in db.execute('SELECT * FROM independent_circles_v039 WHERE run_id=?',(ir['id'],))]
  associations=[dict(a) for a in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=?',(ar['id'],))]
  rid=uuid.uuid4().hex;rows=[];matched=0
  for a in associations:
   ids=json.loads(a['edge_ids_json']);segments=[edges[i] for i in ids if i in edges]
   result,reason=match_one(segments,circles)
   c=result['circle'] if result else None
   matched+=bool(c)
   rows.append((uuid.uuid4().hex,rid,a['id'],a['label'],c['id'] if c else None,c['ocr_text'] if c else None,c['ocr_confidence'] if c else None,result['distance'] if result else None,'geometric_candidate_unverified' if c else 'unmatched',reason,json.dumps(ids)))
  summary=dict(fuse_candidates=len(rows),geometric_matches=matched,unmatched=len(rows)-matched,electrically_verified_connections=0,warning='Matches rely on same-row proximity of OCR circles to horizontal segments; NO continuity or connector mapping.')
  db.execute('INSERT INTO path_match_runs_v0310(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO path_matches_v0310(id,run_id,association_id,fuse_label,circle_id,terminal_text,ocr_confidence,geometric_distance,status,reason,edge_ids_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM path_match_runs_v0310 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,matches=[])
  rows=[dict(x) for x in db.execute('SELECT * FROM path_matches_v0310 WHERE run_id=?',(r['id'],))]
  for row in rows:row['edge_ids']=json.loads(row.pop('edge_ids_json'))
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),matches=rows)

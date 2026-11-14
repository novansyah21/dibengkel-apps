"""Explain every geometric candidate rejection without altering connectivity."""
import sqlite3,json,uuid,math
SCHEMA="""
CREATE TABLE IF NOT EXISTS match_diagnostic_runs_v0313(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS match_diagnostic_items_v0313(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,association_id TEXT NOT NULL,fuse_label TEXT NOT NULL,edge_ids_json TEXT NOT NULL,endpoint_x REAL,endpoint_y REAL,candidates_json TEXT NOT NULL,reason TEXT NOT NULL);
"""
def diagnose(segments,circles,row_tolerance=.017,max_gap=.065,ambiguity=.008):
 h=[e for e in segments if abs(e['y2']-e['y1'])<=abs(e['x2']-e['x1'])]
 if not h:return None,None,[],'no_horizontal_segment'
 right=max(max(e['x1'],e['x2']) for e in h)
 ends=[e for e in h if abs(max(e['x1'],e['x2'])-right)<.015]
 y=sum((e['y1']+e['y2'])/2 for e in ends)/len(ends)
 options=[]
 for c in circles:
  if not c.get('ocr_text'):continue
  dy=abs(c['y']-y);gap=c['x']-right
  distance=math.hypot(max(0,gap),dy)
  reasons=[]
  if dy>row_tolerance:reasons.append('vertical_offset_exceeds_tolerance')
  if gap<-.012:reasons.append('circle_left_of_endpoint')
  if gap>max_gap:reasons.append('horizontal_gap_exceeds_tolerance')
  options.append(dict(circle_id=c['id'],terminal_text=c['ocr_text'],ocr_confidence=c['ocr_confidence'],x=c['x'],y=c['y'],vertical_offset=round(dy,5),horizontal_gap=round(gap,5),distance=round(distance,5),eligible=not reasons,rejection_reasons=reasons))
 options.sort(key=lambda x:(not x['eligible'],x['distance']))
 eligible=[o for o in options if o['eligible']]
 if not eligible:reason='no_readable_circle_on_segment_row'
 elif len(eligible)>1 and eligible[1]['distance']-eligible[0]['distance']<ambiguity:reason='ambiguous_circle_candidates'
 else:reason='geometric_row_candidate_only'
 return round(right,5),round(y,5),options[:8],reason
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  ir=db.execute('SELECT id FROM independent_runs_v039 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  ar=db.execute('SELECT * FROM association_runs_v035 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not ir or not ar:raise ValueError('Run independent OCR and Find candidate circuits first')
  edges={e['source_edge_id']:dict(e) for e in db.execute("SELECT * FROM segment_edges_v034 WHERE run_id=? AND classification='candidate_wire'",(ar['segment_run_id'],))}
  circles=[dict(c) for c in db.execute('SELECT * FROM independent_circles_v039 WHERE run_id=?',(ir['id'],))]
  associations=[dict(a) for a in db.execute('SELECT * FROM association_candidates_v035 WHERE run_id=?',(ar['id'],))]
  rid=uuid.uuid4().hex;rows=[];matched=0
  for a in associations:
   ids=json.loads(a['edge_ids_json']);x,y,options,reason=diagnose([edges[i] for i in ids if i in edges],circles)
   matched+=reason=='geometric_row_candidate_only'
   rows.append((uuid.uuid4().hex,rid,a['id'],a['label'],json.dumps(ids),x,y,json.dumps(options),reason))
  summary=dict(fuse_candidates=len(rows),geometric_candidates=matched,rejected_or_ambiguous=len(rows)-matched,electrically_verified_connections=0,warning='Diagnostics show nearest OCR alternatives and rejection reasons; not proof of connectivity.')
  db.execute('INSERT INTO match_diagnostic_runs_v0313(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO match_diagnostic_items_v0313(id,run_id,association_id,fuse_label,edge_ids_json,endpoint_x,endpoint_y,candidates_json,reason) VALUES(?,?,?,?,?,?,?,?,?)',rows)
  db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  r=db.execute('SELECT * FROM match_diagnostic_runs_v0313 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not r:return dict(run=None,items=[])
  rows=[dict(x) for x in db.execute('SELECT * FROM match_diagnostic_items_v0313 WHERE run_id=?',(r['id'],))]
  for x in rows:x['edge_ids']=json.loads(x.pop('edge_ids_json'));x['candidates']=json.loads(x.pop('candidates_json'))
  return dict(run=dict(id=r['id'],**json.loads(r['summary_json'])),items=rows)

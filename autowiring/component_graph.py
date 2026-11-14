"""Fuse-symbol hypotheses and component-aware graph proposals, never electrical verification."""
import sqlite3,json,uuid,re
SCHEMA="""
CREATE TABLE IF NOT EXISTS component_runs_v0316(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS component_items_v0316(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,source_gap_id TEXT NOT NULL,fuse_label TEXT NOT NULL,component_type TEXT NOT NULL,rating_text TEXT,status TEXT NOT NULL,source_edge_id TEXT NOT NULL,target_edge_id TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,evidence_json TEXT NOT NULL);
"""
def classify(gap,visual):
 """Conservative hypothesis: fuse-label association + ink + known gap geometry.
 Never classify electrical conductivity, never claim machine-confirmed fuse."""
 ink=float(visual['ink_fraction']);center=float(visual['centerline_ink_fraction'])
 gap_width=float(gap['gap'])
 plausible=(.025<=gap_width<=.075 and .10<=ink<=.55 and .05<=center<=.65)
 label=str(gap['fuse_label'])
 return dict(component_type='fuse_symbol_candidate' if plausible else 'unknown_component_candidate',status='visual_hypothesis_requires_review',rating_text=None,evidence={'fuse_label_association':label,'gap_width':gap_width,'ink_fraction':ink,'centerline_ink_fraction':center,'rule':'fuse-associated wavy-symbol candidate; needs human confirmation','component_graph':'source_wire -> component_candidate -> target_wire; no direct wire join'})
def build(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  gr=db.execute('SELECT id FROM gap_visual_runs_v0315 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not gr:raise ValueError('Run Inspect gap image crops first')
  vr=[dict(x) for x in db.execute('SELECT * FROM gap_visual_items_v0315 WHERE run_id=?',(gr['id'],))]
  gaps={x['id']:dict(x) for x in db.execute('SELECT * FROM continuity_items_v0314')}
  rid=uuid.uuid4().hex;rows=[];fuse=0
  for v in vr:
   g=gaps.get(v['source_gap_id'])
   if not g:continue
   result=classify(g,v);fuse+=result['component_type']=='fuse_symbol_candidate'
   rows.append((uuid.uuid4().hex,rid,g['id'],g['fuse_label'],result['component_type'],result['rating_text'],result['status'],g['source_edge_id'],g['neighbor_edge_id'],(g['endpoint_x']+g['neighbor_x'])/2,(g['endpoint_y']+g['neighbor_y'])/2,json.dumps(result['evidence'])))
  summary=dict(component_hypotheses=len(rows),fuse_symbol_candidates=fuse,confirmed_components=0,electrically_verified_connections=0,warning='Candidate nodes preserve source/target wires separately. Fuse rating not OCR-confirmed.')
  db.execute('INSERT INTO component_runs_v0316(id,diagram_id,summary_json) VALUES(?,?,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO component_items_v0316 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',rows);db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  run=db.execute('SELECT * FROM component_runs_v0316 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not run:return dict(run=None,items=[])
  items=[dict(x) for x in db.execute('SELECT * FROM component_items_v0316 WHERE run_id=?',(run['id'],))]
  for item in items:
   item['evidence']=json.loads(item.pop('evidence_json'))
   item['graph_preview']={'nodes':[{'id':item['source_edge_id'],'type':'wire_segment'},{'id':item['id'],'type':item['component_type']},{'id':item['target_edge_id'],'type':'wire_segment'}],'edges':[{'from':item['source_edge_id'],'to':item['id'],'status':'schematic_hypothesis'},{'from':item['id'],'to':item['target_edge_id'],'status':'schematic_hypothesis'}],'electrical_verification':False}
  return dict(run=dict(id=run['id'],**json.loads(run['summary_json'])),items=items)

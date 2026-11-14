"""Visual gap inspection with actual image crops; never infer electrical continuity."""
import base64,io,json,sqlite3,uuid
SCHEMA="""
CREATE TABLE IF NOT EXISTS gap_visual_runs_v0315(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,summary_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gap_visual_items_v0315(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,source_gap_id TEXT NOT NULL,fuse_label TEXT NOT NULL,classification TEXT NOT NULL,ink_fraction REAL NOT NULL,centerline_ink_fraction REAL NOT NULL,crop_base64 TEXT NOT NULL,reason TEXT NOT NULL);
"""
def inspect(image_path, gap, pad_x=24,pad_y=20):
 from PIL import Image,ImageOps,ImageDraw
 with Image.open(image_path) as src:
  im=src.convert('L');w,h=im.size
  x0=int(gap['endpoint_x']*w);x1=int(gap['neighbor_x']*w);y=int((gap['endpoint_y']+gap['neighbor_y'])*.5*h)
  left=max(0,min(x0,x1)-pad_x);right=min(w,max(x0,x1)+pad_x)
  top=max(0,y-pad_y);bottom=min(h,y+pad_y+1)
  crop=im.crop((left,top,right,bottom))
  # Calculate ink in central region, excluding segment endpoints.
  a=max(0,min(w,x0+3));b=min(w,max(0,x1-3))
  pixels=im.load()
  dark=sum(pixels[x,yy]<150 for x in range(a,b) for yy in range(max(0,y-5),min(h,y+6)))
  area=max(1,(b-a)*(min(h,y+6)-max(0,y-5)))
  center=sum(pixels[x,y]<150 for x in range(a,b)) if 0<=y<h else 0
  width=max(1,b-a)
  ink=round(dark/area,4);center_ratio=round(center/width,4)
  # This is image appearance only, NOT a topology/continuity classifier.
  cls='dark_content_in_gap_review_symbol_or_wire' if ink>.16 else 'light_gap_review_missing_or_symbol'
  annotated=ImageOps.colorize(crop,black='#20252a',white='#ffffff').convert('RGB')
  draw=ImageDraw.Draw(annotated)
  for xx,color in ((x0,'#ff9900'),(x1,'#ff9900')):
   draw.line((xx-left,0,xx-left,annotated.height),fill=color,width=2)
  draw.line((0,y-top,annotated.width,y-top),fill='#00aadd',width=1)
  stream=io.BytesIO();annotated.save(stream,format='PNG')
  return cls,ink,center_ratio,base64.b64encode(stream.getvalue()).decode('ascii')
def build(dbpath,diagram_id,image_path):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  cr=db.execute('SELECT id FROM continuity_runs_v0314 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not cr:raise ValueError('Run Audit collinear segment gaps first')
  gaps=[dict(x) for x in db.execute('SELECT * FROM continuity_items_v0314 WHERE run_id=?',(cr['id'],))]
  rid=uuid.uuid4().hex;rows=[]
  for g in gaps:
   cls,ink,center,png=inspect(image_path,g)
   rows.append((uuid.uuid4().hex,rid,g['id'],g['fuse_label'],cls,ink,center,png,'Visual ink only. Crop must be reviewed for fuse/component/border/junction; no auto-merge.'))
  summary=dict(gaps_inspected=len(rows),electrically_verified_connections=0,warning='Crops are raw visual evidence, classification is not electrical continuity.')
  db.execute('INSERT INTO gap_visual_runs_v0315 VALUES(?,?,CURRENT_TIMESTAMP,?)',(rid,diagram_id,json.dumps(summary)))
  db.executemany('INSERT INTO gap_visual_items_v0315 VALUES(?,?,?,?,?,?,?,?,?)',rows);db.commit()
 return dict(run_id=rid,**summary)
def latest(dbpath,diagram_id):
 with sqlite3.connect(dbpath) as db:
  db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
  run=db.execute('SELECT * FROM gap_visual_runs_v0315 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(diagram_id,)).fetchone()
  if not run:return dict(run=None,items=[])
  return dict(run=dict(id=run['id'],**json.loads(run['summary_json'])),items=[dict(x) for x in db.execute('SELECT * FROM gap_visual_items_v0315 WHERE run_id=?',(run['id'],))])

"""AutoWiring v0.3.7 local-only interactive diagram review server (stdlib)."""
import argparse,json,mimetypes,sqlite3,shutil,uuid
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from autowiring.auto_mapping import SCHEMA as AUTO_SCHEMA,extract as auto_extract
from autowiring.circuit_graph import SCHEMA as GRAPH_SCHEMA,build as build_graph,latest as latest_graph
from autowiring.segmentation import SCHEMA as SEG_SCHEMA,build as build_segments,latest as latest_segments
from autowiring.association import SCHEMA as ASSOC_SCHEMA,build as build_associations,latest as latest_associations
from autowiring.terminal_detection import SCHEMA as TERMINAL_SCHEMA,build as build_terminals,latest as latest_terminal_candidates
from autowiring.circle_detection import SCHEMA as CIRCLE_SCHEMA,build as build_circles,latest as latest_circles

ROOT=Path(__file__).resolve().parent
SCHEMA="""
CREATE TABLE IF NOT EXISTS viewer_diagrams(id TEXT PRIMARY KEY,title TEXT NOT NULL,image_file TEXT NOT NULL,width INTEGER,height INTEGER,source_url TEXT,vehicle TEXT,verification TEXT DEFAULT 'visual_content_confirmed_applicability_unverified');
CREATE TABLE IF NOT EXISTS viewer_annotations(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,kind TEXT NOT NULL,label TEXT NOT NULL,x REAL NOT NULL,y REAL NOT NULL,w REAL NOT NULL DEFAULT 0.04,h REAL NOT NULL DEFAULT 0.04,notes TEXT DEFAULT '',verification TEXT NOT NULL DEFAULT 'needs_review',FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id));
CREATE TABLE IF NOT EXISTS viewer_paths(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,label TEXT NOT NULL,points TEXT NOT NULL,notes TEXT DEFAULT '',verification TEXT NOT NULL DEFAULT 'needs_review',FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id));
CREATE TABLE IF NOT EXISTS viewer_terminals(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,connector_annotation_id TEXT NOT NULL,terminal_number TEXT NOT NULL,signal_name TEXT DEFAULT '',notes TEXT DEFAULT '',verification TEXT NOT NULL DEFAULT 'needs_review',FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id),FOREIGN KEY(connector_annotation_id) REFERENCES viewer_annotations(id),UNIQUE(connector_annotation_id,terminal_number));
CREATE TABLE IF NOT EXISTS viewer_circuit_links(id TEXT PRIMARY KEY,diagram_id TEXT NOT NULL,path_id TEXT NOT NULL,annotation_id TEXT NOT NULL,terminal_id TEXT,notes TEXT DEFAULT '',verification TEXT NOT NULL DEFAULT 'needs_review',FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id),FOREIGN KEY(path_id) REFERENCES viewer_paths(id),FOREIGN KEY(annotation_id) REFERENCES viewer_annotations(id),FOREIGN KEY(terminal_id) REFERENCES viewer_terminals(id),UNIQUE(path_id,annotation_id,terminal_id));
"""
SEEDS=[('junction_block','Junction Block — fuse and terminal map','c9954639ad0fb133cedb.png',1136,1598),('abbreviations','Abbreviation reference','17ba65f18296c7320c58.png',640,316),('bcm_wiring','BCM internal wiring / harness','a6c3c83161c162401c88.png',1248,1512)]

def setup(db):
 db.executescript(SCHEMA + AUTO_SCHEMA + GRAPH_SCHEMA + SEG_SCHEMA + ASSOC_SCHEMA + TERMINAL_SCHEMA + CIRCLE_SCHEMA)
 for id,title,file,w,h in SEEDS:
  db.execute('INSERT OR IGNORE INTO viewer_diagrams(id,title,image_file,width,height,source_url,vehicle) VALUES(?,?,?,?,?,?,?)',(id,title,file,w,h,'https://charm.li/','Suzuki SX4 2007 2WD L4-2.0L (source context, unverified)'))
 db.commit()

def validate_point(x):
 x=float(x)
 if not 0<=x<=1:raise ValueError('normalized coordinates must be between 0 and 1')
 return x

def run(port,dbpath):
 dbpath.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(dbpath) as db:setup(db)
 class Handler(BaseHTTPRequestHandler):
  def send(self,status,obj):
   data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def query(self,sql,args=()):
   with sqlite3.connect(dbpath) as db:
    db.row_factory=sqlite3.Row
    return [dict(x) for x in db.execute(sql,args)]
  def do_GET(self):
   url=urlparse(self.path);p=url.path
   if p=='/api/circle-candidates':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_circles(dbpath,d))
   if p=='/api/terminal-candidates':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_terminal_candidates(dbpath,d))
   if p=='/api/associations':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_associations(dbpath,d))
   if p=='/api/segmentation':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_segments(dbpath,d))
   if p=='/api/graph':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_graph(dbpath,d))
   if p=='/api/graph-export':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,latest_graph(dbpath,d))
   if p=='/api/auto-candidates':
    d=parse_qs(url.query).get('diagram',[''])[0]
    rows=self.query('SELECT c.* FROM auto_candidates_v032 c JOIN auto_runs_v032 r ON r.id=c.run_id WHERE c.diagram_id=? AND r.id=(SELECT id FROM auto_runs_v032 WHERE diagram_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1) ORDER BY c.kind,c.confidence DESC LIMIT 450',(d,d))
    return self.send(200,rows)
   if p=='/api/auto-runs':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,self.query('SELECT * FROM auto_runs_v032 WHERE diagram_id=? ORDER BY created_at DESC LIMIT 10',(d,)))
   if p=='/api/diagrams':return self.send(200,self.query('SELECT * FROM viewer_diagrams ORDER BY id'))
   if p=='/api/annotations':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,self.query('SELECT * FROM viewer_annotations WHERE diagram_id=? ORDER BY label',(d,)))
   if p=='/api/paths':
    d=parse_qs(url.query).get('diagram',[''])[0]
    rows=self.query('SELECT * FROM viewer_paths WHERE diagram_id=? ORDER BY label',(d,))
    for r in rows:r['points']=json.loads(r['points'])
    return self.send(200,rows)
   if p=='/api/terminals':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,self.query('SELECT t.*,a.label AS connector_label FROM viewer_terminals t JOIN viewer_annotations a ON a.id=t.connector_annotation_id WHERE t.diagram_id=? ORDER BY a.label,t.terminal_number',(d,)))
   if p=='/api/circuit-links':
    d=parse_qs(url.query).get('diagram',[''])[0]
    return self.send(200,self.query('SELECT l.*,a.label AS annotation_label,p.label AS path_label,t.terminal_number FROM viewer_circuit_links l JOIN viewer_annotations a ON a.id=l.annotation_id JOIN viewer_paths p ON p.id=l.path_id LEFT JOIN viewer_terminals t ON t.id=l.terminal_id WHERE l.diagram_id=? ORDER BY p.label,a.label',(d,)))
   if p.startswith('/images/'):
    name=p.removeprefix('/images/')
    if name not in {x[2] for x in SEEDS}:return self.send(404,{'error':'not found'})
    file=ROOT/'sample_assets'/name
   elif p in ('/','/index.html'):file=ROOT/'web'/'index.html'
   elif p in ('/app.js','/style.css'):file=ROOT/'web'/p[1:]
   else:return self.send(404,{'error':'not found'})
   if not file.is_file():return self.send(404,{'error':'file missing'})
   data=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(file))[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def body(self):
   n=int(self.headers.get('Content-Length','0'))
   if n<=0 or n>50000:raise ValueError('invalid body size')
   return json.loads(self.rfile.read(n))
  def do_POST(self):
   try:
    p=urlparse(self.path).path;v=self.body();diagram=v.get('diagram_id','')
    if not self.query('SELECT id FROM viewer_diagrams WHERE id=?',(diagram,)):raise ValueError('unknown diagram')
    if p=='/api/circle-detect':
     info=self.query('SELECT image_file FROM viewer_diagrams WHERE id=?',(diagram,))[0]
     image=ROOT/'sample_assets'/info['image_file']
     if not image.is_file():raise ValueError('Local diagram image missing')
     return self.send(201,build_circles(dbpath,diagram,image))
    if p=='/api/terminal-detect':
     info=self.query('SELECT image_file FROM viewer_diagrams WHERE id=?',(diagram,))[0]
     image=ROOT/'sample_assets'/info['image_file']
     if not image.is_file():raise ValueError('Local diagram image missing; restore sample_assets image')
     return self.send(201,build_terminals(dbpath,diagram,image))
    if p=='/api/association-build':
     return self.send(201,build_associations(dbpath,diagram))
    if p=='/api/segment-build':
     return self.send(201,build_segments(dbpath,diagram))
    if p=='/api/graph-build':
     return self.send(201,build_graph(dbpath,diagram))
    if p=='/api/auto-analyze':
     info=self.query('SELECT image_file FROM viewer_diagrams WHERE id=?',(diagram,))[0]
     result=auto_extract(ROOT/'sample_assets'/info['image_file'],diagram,dbpath,ocr=bool(v.get('ocr',True)),lines=bool(v.get('lines',True)))
     return self.send(201,result)
    if p=='/api/annotations':
     kind=str(v.get('kind','component'))
     if kind not in ('component','connector','fuse','terminal','note'):raise ValueError('invalid kind')
     label=str(v.get('label','')).strip()[:150]
     if not label:raise ValueError('label required')
     row=(uuid.uuid4().hex,diagram,kind,label,*[validate_point(v.get(k,default)) for k,default in [('x',0),('y',0),('w',0.04),('h',0.04)]],str(v.get('notes',''))[:1000],'needs_review')
     sql='INSERT INTO viewer_annotations(id,diagram_id,kind,label,x,y,w,h,notes,verification) VALUES(?,?,?,?,?,?,?,?,?,?)'
    elif p=='/api/paths':
     pts=v.get('points',[])
     if not isinstance(pts,list) or not 2<=len(pts)<=100:raise ValueError('path requires 2–100 points')
     pts=[[validate_point(a),validate_point(b)] for a,b in pts]
     label=str(v.get('label','')).strip()[:150]
     if not label:raise ValueError('label required')
     row=(uuid.uuid4().hex,diagram,label,json.dumps(pts),str(v.get('notes',''))[:1000],'needs_review')
     sql='INSERT INTO viewer_paths(id,diagram_id,label,points,notes,verification) VALUES(?,?,?,?,?,?)'
    elif p=='/api/terminals':
     aid=str(v.get('connector_annotation_id',''))
     if not self.query("SELECT id FROM viewer_annotations WHERE id=? AND diagram_id=? AND kind='connector'",(aid,diagram)):raise ValueError('connector annotation not found in diagram')
     number=str(v.get('terminal_number','')).strip()[:30]
     if not number:raise ValueError('terminal number required')
     row=(uuid.uuid4().hex,diagram,aid,number,str(v.get('signal_name',''))[:150],str(v.get('notes',''))[:1000],'needs_review')
     sql='INSERT INTO viewer_terminals(id,diagram_id,connector_annotation_id,terminal_number,signal_name,notes,verification) VALUES(?,?,?,?,?,?,?)'
    elif p=='/api/circuit-links':
     aid=str(v.get('annotation_id',''));pid=str(v.get('path_id',''));tid=v.get('terminal_id') or None
     if not self.query('SELECT id FROM viewer_annotations WHERE id=? AND diagram_id=?',(aid,diagram)):raise ValueError('annotation not found in diagram')
     if not self.query('SELECT id FROM viewer_paths WHERE id=? AND diagram_id=?',(pid,diagram)):raise ValueError('path not found in diagram')
     if tid and not self.query('SELECT id FROM viewer_terminals WHERE id=? AND diagram_id=? AND connector_annotation_id=?',(tid,diagram,aid)):raise ValueError('terminal must belong to selected connector')
     row=(uuid.uuid4().hex,diagram,pid,aid,tid,str(v.get('notes',''))[:1000],'needs_review')
     sql='INSERT INTO viewer_circuit_links(id,diagram_id,path_id,annotation_id,terminal_id,notes,verification) VALUES(?,?,?,?,?,?,?)'
    else:return self.send(404,{'error':'not found'})
    with sqlite3.connect(dbpath) as db:db.execute(sql,row);db.commit()
    return self.send(201,{'id':row[0]})
   except (ValueError,TypeError,KeyError,sqlite3.Error,json.JSONDecodeError) as e:return self.send(400,{'error':str(e)})
  def do_DELETE(self):
   p=urlparse(self.path).path.split('/')
   if len(p)!=4 or p[1]!='api' or p[2] not in ('annotations','paths','terminals','circuit-links') or not p[3].isalnum():return self.send(404,{'error':'not found'})
   table={'annotations':'viewer_annotations','paths':'viewer_paths','terminals':'viewer_terminals','circuit-links':'viewer_circuit_links'}[p[2]]
   with sqlite3.connect(dbpath) as db:
    db.execute('PRAGMA foreign_keys=ON')
    try:cursor=db.execute(f'DELETE FROM {table} WHERE id=?',(p[3],));db.commit()
    except sqlite3.IntegrityError:return self.send(409,{'error':'Item is referenced by terminals or circuit links; delete references first'})
   return self.send(200,{'deleted':cursor.rowcount})
 print(f'AutoWiring v0.3.7 at http://127.0.0.1:{port} | DB: {dbpath}')
 ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--db',type=Path,default=ROOT/'output'/'autowiring.db');a=p.parse_args();run(a.port,a.db)

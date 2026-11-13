import hashlib, json, re, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'AutoWiringResearch/0.2 (local, bounded discovery; contact: configure-yourself)'
SOURCES = {
 'bmwteka': {'url':'https://bmwteka.com/en/bmw/e36','brand':'BMW','model':'E36','type':'wiring'},
 'wds': {'url':'https://wds.psjr.org/en/e46/','brand':'BMW','model':'E46','type':'wiring'},
 'charm': {'url':'https://charm.li/Suzuki/','brand':'Suzuki','model':None,'type':'repair'},
 'etm': {'url':'https://shark.armchair.mb.ca/~dave/BMW/e30/e30_84.pdf','brand':'BMW','model':'E30','type':'pdf'},
}

def utc(): return datetime.now(timezone.utc).isoformat()
def same_origin(a,b):
 x,y=urlparse(a),urlparse(b)
 return (x.scheme,x.netloc)==(y.scheme,y.netloc)

def robots_check(session,url):
 p=urlparse(url); robots=f'{p.scheme}://{p.netloc}/robots.txt'
 try:
  r=session.get(robots,timeout=12,allow_redirects=True)
  if r.status_code in (401,403): return False,f'robots HTTP {r.status_code}'
  if r.status_code==404: return None,'robots missing; manual authorization needed'
  if r.status_code!=200: return None,f'robots HTTP {r.status_code}; unknown'
  parser=RobotFileParser(); parser.parse(r.text.splitlines())
  return parser.can_fetch(USER_AGENT,url),'robots evaluated'
 except requests.RequestException as e: return None,f'robots unavailable: {type(e).__name__}'

def schema(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, base_url TEXT, last_status TEXT, robots_status TEXT, checked_at TEXT);
 CREATE TABLE IF NOT EXISTS manufacturers(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
 CREATE TABLE IF NOT EXISTS vehicle_models(id INTEGER PRIMARY KEY, manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id), code TEXT NOT NULL, UNIQUE(manufacturer_id,code));
 CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id), model_id INTEGER REFERENCES vehicle_models(id), url TEXT NOT NULL, title TEXT, kind TEXT, content_type TEXT, sha256 TEXT, discovered_at TEXT, UNIQUE(source_id,url));
 CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES documents(id), url TEXT NOT NULL, kind TEXT, UNIQUE(document_id,url));
 CREATE TABLE IF NOT EXISTS electrical_systems(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
 CREATE TABLE IF NOT EXISTS components(id INTEGER PRIMARY KEY, name TEXT, system_id INTEGER REFERENCES electrical_systems(id));
 CREATE TABLE IF NOT EXISTS connectors(id INTEGER PRIMARY KEY, component_id INTEGER REFERENCES components(id), connector_code TEXT);
 CREATE TABLE IF NOT EXISTS connector_pins(id INTEGER PRIMARY KEY, connector_id INTEGER REFERENCES connectors(id), pin_number TEXT, function TEXT);
 CREATE TABLE IF NOT EXISTS wires(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES vehicle_models(id), from_pin_id INTEGER REFERENCES connector_pins(id), to_pin_id INTEGER REFERENCES connector_pins(id), color TEXT, validated INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS diagrams(id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES documents(id), system_id INTEGER REFERENCES electrical_systems(id), asset_url TEXT, validated INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS annotations(id INTEGER PRIMARY KEY, diagram_id INTEGER REFERENCES diagrams(id), component_id INTEGER REFERENCES components(id), geometry_json TEXT, validated INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS component_locations(id INTEGER PRIMARY KEY, component_id INTEGER REFERENCES components(id), model_id INTEGER REFERENCES vehicle_models(id), description TEXT, photo_url TEXT, validated INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS diagnostic_procedures(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES vehicle_models(id), system_id INTEGER REFERENCES electrical_systems(id), title TEXT, document_id INTEGER REFERENCES documents(id), validated INTEGER DEFAULT 0);
 ''')
 db.commit()

def upsert_source(db,slug,url,status,robots):
 db.execute('INSERT INTO sources(slug,base_url,last_status,robots_status,checked_at) VALUES(?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET last_status=excluded.last_status,robots_status=excluded.robots_status,checked_at=excluded.checked_at',(slug,url,status,robots,utc()))
 return db.execute('SELECT id FROM sources WHERE slug=?',(slug,)).fetchone()[0]

def model_id(db,brand,model):
 if not model: return None
 db.execute('INSERT OR IGNORE INTO manufacturers(name) VALUES(?)',(brand,))
 mid=db.execute('SELECT id FROM manufacturers WHERE name=?',(brand,)).fetchone()[0]
 db.execute('INSERT OR IGNORE INTO vehicle_models(manufacturer_id,code) VALUES(?,?)',(mid,model))
 return db.execute('SELECT id FROM vehicle_models WHERE manufacturer_id=? AND code=?',(mid,model)).fetchone()[0]

def parse_html(html,url,limit=200):
 soup=BeautifulSoup(html,'html.parser')
 title=soup.title.get_text(' ',strip=True) if soup.title else ''
 links=[]; seen=set()
 for tag,attr,kind in [('a','href','page'),('img','src','image'),('script','src','script'),('link','href','stylesheet'),('iframe','src','iframe')]:
  for node in soup.find_all(tag):
   value=node.get(attr)
   if not value: continue
   target=urljoin(url,value).split('#')[0]
   if urlparse(target).scheme not in ('http','https') or target in seen: continue
   seen.add(target)
   links.append({'url':target,'kind':kind,'label':node.get_text(' ',strip=True)[:180]})
   if len(links)>=limit: break
  if len(links)>=limit: break
 return {'title':title,'links':links,'embedded_json_scripts':len(soup.select('script[type="application/json"],script[type="application/ld+json"]')),'next_data':bool(soup.select_one('script#__NEXT_DATA__')),'text_excerpt':soup.get_text(' ',strip=True)[:500]}

def inspect_one(session,db,slug,cfg,allow_unknown=False,download_pdf=False,max_bytes=25_000_000):
 url=cfg['url']; allowed,reason=robots_check(session,url)
 result={'source':slug,'url':url,'robots_allowed':allowed,'robots_reason':reason,'timestamp':utc()}
 if allowed is False or (allowed is None and not allow_unknown):
  result['status']='skipped_robots_disallowed' if allowed is False else 'skipped_robots_unknown'
  upsert_source(db,slug,url,result['status'],reason);db.commit();return result
 if allowed is None: result['warning']='Robots status unknown. Explicit override used; ensure authorization before fetching.'
 try:
  with session.get(url,timeout=25,stream=True) as r:
   result['http_status']=r.status_code;result['final_url']=r.url;result['content_type']=r.headers.get('Content-Type','')
   if r.status_code!=200:
    result['status']='http_error';upsert_source(db,slug,url,result['status'],reason);db.commit();return result
   content=b''
   for chunk in r.iter_content(65536):
    content+=chunk
    if len(content)>max_bytes: raise ValueError('max_bytes exceeded')
  result['bytes']=len(content);result['sha256']=hashlib.sha256(content).hexdigest()
  is_pdf='pdf' in result['content_type'].lower() or content[:4]==b'%PDF'
  source_id=upsert_source(db,slug,url,'inspected',reason)
  mid=model_id(db,cfg['brand'],cfg.get('model'))
  info={'title':'','links':[]}
  if is_pdf:
   result['kind']='pdf';result['pdf_header_valid']=content.startswith(b'%PDF')
   if download_pdf:
    folder=Path('downloads/pdf');folder.mkdir(parents=True,exist_ok=True)
    path=folder/(slug+'-'+result['sha256'][:12]+'.pdf');path.write_bytes(content);result['saved_pdf']=str(path)
    try:
     import fitz
     pdf=fitz.open(stream=content,filetype='pdf');result['pdf_pages']=len(pdf)
     result['sample_text_chars']=sum(len(pdf[i].get_text()) for i in range(min(3,len(pdf))))
     result['sample_images']=sum(len(pdf[i].get_images()) for i in range(min(3,len(pdf))))
    except ImportError: result['pdf_analysis']='PyMuPDF not installed'
  else:
   result['kind']='html';info=parse_html(content.decode('utf-8','replace'),r.url)
   result.update({'title':info['title'],'asset_count':len(info['links']),'embedded_json_scripts':info['embedded_json_scripts'],'next_data':info['next_data'],'text_excerpt':info['text_excerpt']})
  db.execute('INSERT INTO documents(source_id,model_id,url,title,kind,content_type,sha256,discovered_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,url) DO UPDATE SET title=excluded.title,content_type=excluded.content_type,sha256=excluded.sha256',(source_id,mid,url,info['title'],result['kind'],result['content_type'],result['sha256'],utc()))
  did=db.execute('SELECT id FROM documents WHERE source_id=? AND url=?',(source_id,url)).fetchone()[0]
  for item in info['links']:
   db.execute('INSERT OR IGNORE INTO assets(document_id,url,kind) VALUES(?,?,?)',(did,item['url'],item['kind']))
  result['links']=info['links'];result['status']='inspected';db.commit()
 except (requests.RequestException,ValueError) as e:
  result['status']='error';result['error']=str(e)[:250];upsert_source(db,slug,url,result['status'],reason);db.commit()
 return result

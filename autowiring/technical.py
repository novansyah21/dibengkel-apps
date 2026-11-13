"""Conservative technical discovery: inspect HTML hierarchy and image references, never infer wire connectivity."""
import re, json
from urllib.parse import urlparse,unquote
from bs4 import BeautifulSoup
from .discovery import now

TERMS=('wiring diagram','wiring diagrams','electrical diagram','electrical diagrams','circuit diagram','schematic','instrument cluster','speedometer','electrical','engine control','engine management','connector','component location','fuse','relay')

def install(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS technical_pages_v3(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,url TEXT NOT NULL,parent_url TEXT,depth INTEGER,title TEXT,content_excerpt TEXT,body_terms_json TEXT,discovery_context TEXT,applicability_status TEXT NOT NULL DEFAULT 'unverified',fetched_at TEXT NOT NULL,UNIQUE(source_id,url));
 CREATE TABLE IF NOT EXISTS technical_assets_v3(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,page_url TEXT NOT NULL,asset_url TEXT NOT NULL,asset_kind TEXT NOT NULL,alt_text TEXT,verification_status TEXT NOT NULL DEFAULT 'unverified',UNIQUE(source_id,page_url,asset_url));
 CREATE TABLE IF NOT EXISTS technical_candidates_v3(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,url TEXT NOT NULL,parent_url TEXT,title TEXT,category TEXT NOT NULL,evidence_kind TEXT NOT NULL DEFAULT 'link_label',applicability_status TEXT NOT NULL DEFAULT 'unverified',verification_status TEXT NOT NULL DEFAULT 'candidate',UNIQUE(source_id,url,parent_url));
 CREATE TABLE IF NOT EXISTS technical_checks_v3(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,url TEXT NOT NULL,outcome TEXT NOT NULL,checked_at TEXT NOT NULL);
 ''');db.commit()

def classify(text):
 t=unquote(text).lower()
 if re.search(r'wiring\s+diagrams?|electrical\s+diagrams?|circuit\s+diagrams?|schematics?',t):return 'wiring_diagram_candidate'
 if re.search(r'connector|pinout|terminal|plug connection',t):return 'connector_candidate'
 if re.search(r'component locations?|location of components',t):return 'component_location_candidate'
 if any(x in t for x in ('electrical','instrument cluster','speedometer','engine control','engine management','fuse','relay')):return 'electrical_category_candidate'
 return 'navigation_candidate'

def rank(url,label,slug):
 t=(unquote(urlparse(url).path)+' '+label).lower()
 pts=0
 for term in TERMS:
  if term in t:pts+=12
 if slug=='charm':
  if 'repair and diagnosis' in t:pts+=120
  if 'diagrams' in t:pts+=70
  if 'electrical' in t:pts+=60
  if 'parts and labor' in t:pts-=90
  if '/suzuki/2007/sx4' in t:pts+=30
 if slug=='bmwteka':
  if '/wds/' in t:pts+=90
  if '/tis/e36' in t:pts+=30
  if '/tis/documents/' in t:pts+=5
  if '/login' in t or '/register' in t:pts-=100
 return pts

def record_html(db,sid,url,parent,depth,html):
 soup=BeautifulSoup(html,'html.parser');title=soup.title.get_text(' ',strip=True) if soup.title else ''
 body=soup.get_text(' ',strip=True);terms=sorted({x for x in TERMS if x in body.lower()})
 db.execute('''INSERT INTO technical_pages_v3(source_id,url,parent_url,depth,title,content_excerpt,body_terms_json,discovery_context,fetched_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,url) DO UPDATE SET title=excluded.title,content_excerpt=excluded.content_excerpt,body_terms_json=excluded.body_terms_json,fetched_at=excluded.fetched_at''',(sid,url,parent,depth,title,body[:700],json.dumps(terms),'observed_html',now()))
 for tag,attr,kind in [('img','src','image'),('object','data','object'),('embed','src','embed'),('iframe','src','iframe'),('source','src','media')]:
  from urllib.parse import urljoin
  for element in soup.find_all(tag):
   src=element.get(attr)
   if not src:continue
   asset=urljoin(url,src)
   if urlparse(asset).scheme not in ('http','https'):continue
   db.execute('INSERT OR IGNORE INTO technical_assets_v3(source_id,page_url,asset_url,asset_kind,alt_text) VALUES(?,?,?,?,?)',(sid,url,asset,kind,element.get('alt','')[:200]))
 db.commit()
 return {'title':title,'body_terms':terms}

def record_candidate(db,sid,url,parent,label):
 category=classify(label+' '+urlparse(url).path)
 db.execute('''INSERT OR IGNORE INTO technical_candidates_v3(source_id,url,parent_url,title,category,evidence_kind) VALUES(?,?,?,?,?,?)''',(sid,url,parent,label,category,'observed_html_link'))
 db.commit();return category

def export(db):
 candidates=[dict(zip(('source','url','parent_url','title','category','applicability_status','verification_status'),row)) for row in db.execute('''SELECT s.slug,c.url,c.parent_url,c.title,c.category,c.applicability_status,c.verification_status FROM technical_candidates_v3 c JOIN sources s ON s.id=c.source_id ORDER BY s.slug,c.category,c.url''')]
 assets=[dict(zip(('source','page_url','asset_url','asset_kind','verification_status'),row)) for row in db.execute('''SELECT s.slug,a.page_url,a.asset_url,a.asset_kind,a.verification_status FROM technical_assets_v3 a JOIN sources s ON s.id=a.source_id ORDER BY s.slug,a.page_url''')]
 return candidates,assets

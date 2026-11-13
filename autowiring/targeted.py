"""Targeted, bounded discovery with explicit candidate/verified separation."""
import json,re,time
from urllib.parse import urlparse,unquote
from .core import robots_check,parse_html,same_origin
from .discovery import classify_link,manufacturer_id,record_link,now
from .technical import record_html,record_candidate,rank

TARGETS={
 'charm': {'brand':'Suzuki','year':2007,'model':'SX4','system':'Engine Management','seed':'https://charm.li/Suzuki/2007/'},
 'bmwteka': {'brand':'BMW','model':'E36','system':'Instrument Cluster','seed':'https://bmwteka.com/en/tis/E36'},
}
KEYWORDS=('wiring','electrical','circuit','diagram','instrument','cluster','speedometer','connector','pinout','location','engine control','engine management','powertrain','fuse')

def migrate(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS vehicle_variants_v2(id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES vehicle_models(id), model_year INTEGER NOT NULL, engine TEXT NOT NULL DEFAULT '', drivetrain TEXT NOT NULL DEFAULT '', raw_label TEXT NOT NULL, source_id INTEGER REFERENCES sources(id), evidence_url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', UNIQUE(model_id,model_year,engine,drivetrain,source_id,evidence_url));
 CREATE TABLE IF NOT EXISTS target_documents_v2(id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id), url TEXT NOT NULL, parent_url TEXT NOT NULL, title TEXT, classification TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', evidence TEXT, discovered_at TEXT NOT NULL, UNIQUE(source_id,url,parent_url));
 CREATE TABLE IF NOT EXISTS targeted_pages_v2(id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id), url TEXT NOT NULL, parent_url TEXT, depth INTEGER, robots_allowed INTEGER, http_status INTEGER, outcome TEXT NOT NULL, checked_at TEXT NOT NULL, UNIQUE(source_id,url));
 CREATE TABLE IF NOT EXISTS node_edges_v2(id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id), parent_url TEXT NOT NULL, child_url TEXT NOT NULL, UNIQUE(source_id,parent_url,child_url));
 ''');db.commit()

def split_charm_variant(raw):
 """Conservative parse: preserve raw label; never infer unprovided year/engine."""
 raw=unquote(raw).strip()
 m=re.match(r'^(.*?)(?:\s+(2WD|4WD|AWD|FWD|RWD))?(?:\s+((?:L\d|V\d|H\d|I\d)[- ](?:\d+(?:cc)?\s+)?\d+(?:\.\d+)?L.*))?$',raw,re.I)
 if not m:return raw,'',''
 model=m.group(1).strip();drive=(m.group(2) or '').upper();engine=(m.group(3) or '').strip()
 return model,drive,engine

def promote_candidates(db,source='charm'):
 """Only promote directly observed manufacturer/year/model URLs; status stays candidate."""
 rows=db.execute('''SELECT n.url,n.label,n.model_year,s.id FROM catalogue_nodes n JOIN sources s ON s.id=n.source_id WHERE s.slug=? AND n.node_type='model_candidate' AND n.model_year IS NOT NULL''',(source,)).fetchall()
 count=0
 for url,label,year,sid in rows:
  p=[unquote(x) for x in urlparse(url).path.strip('/').split('/')]
  if len(p)!=3 or p[0].lower()!='suzuki' or not p[1].isdigit():continue
  model,drive,engine=split_charm_variant(p[2]);
  if not model:continue
  mid=manufacturer_id(db,'Suzuki')
  db.execute('INSERT OR IGNORE INTO vehicle_models(manufacturer_id,code) VALUES(?,?)',(mid,model))
  model_id=db.execute('SELECT id FROM vehicle_models WHERE manufacturer_id=? AND code=?',(mid,model)).fetchone()[0]
  db.execute('''INSERT OR IGNORE INTO vehicle_variants_v2(model_id,model_year,engine,drivetrain,raw_label,source_id,evidence_url,status) VALUES(?,?,?,?,?,?,?,?)''',(model_id,year,engine,drive,p[2],sid,url,'candidate'))
  db.execute('UPDATE catalogue_nodes SET model_id=? WHERE source_id=? AND url=?',(model_id,sid,url))
  count+=1
 db.commit();return count

def classify_document(url,label):
 txt=(label+' '+unquote(urlparse(url).path)).lower()
 if re.search(r'\b(wiring diagram|circuit diagram|electrical schematic|wiring schematic)\b',txt):return 'wiring_diagram_candidate'
 if re.search(r'\b(connector|pinout|terminal|plug connection)\b',txt):return 'connector_reference_candidate'
 if re.search(r'\b(component location|component locations|location of components)\b',txt):return 'component_location_candidate'
 if re.search(r'\b(instrument cluster|speedometer|electrical system|engine control|engine management|fuse|relay)\b',txt):return 'electrical_reference_candidate'
 return 'other_document_candidate'

def score(url,label,slug,target):
 text=(label+' '+unquote(urlparse(url).path)).lower();points=0
 for k in KEYWORDS:
  if k in text:points+=5
 if target['model'].lower() in text:points+=8
 if str(target.get('year','')) and str(target['year']) in text:points+=4
 if slug=='charm' and '/Suzuki/2007/' in url:points+=20
 if slug=='bmwteka' and ('/wds/' in url.lower() or '/tis/E36' in url):points+=20
 if 'login' in text or 'register' in text or '/search' in text:points-=100
 return points

def ingest_page_links(db,sid,slug,parent,links,depth):
 result=[]
 for item in links:
  url=item['url'];label=item.get('label','')
  if item.get('kind')!='page' or not same_origin(parent,url):continue
  db.execute('INSERT OR IGNORE INTO node_edges_v2(source_id,parent_url,child_url) VALUES(?,?,?)',(sid,parent,url))
  record_candidate(db,sid,url,parent,label)
  found=record_link(db,sid,slug,parent,item)
  if found:result.append(found)
  path=urlparse(url).path.lower()
  if ('/tis/documents/' in path or slug=='charm' and len([p for p in urlparse(url).path.split('/') if p])>=4):
   category=classify_document(url,label)
   db.execute('''INSERT OR IGNORE INTO target_documents_v2(source_id,url,parent_url,title,classification,evidence,discovered_at) VALUES(?,?,?,?,?,?,?)''',(sid,url,parent,label,category,'link_text_and_url_only',now()))
 db.commit();return result

def inspect_target(session,db,sid,slug,url,parent=None,depth=0,max_bytes=1_500_000,delay=1.5):
 allowed,reason=robots_check(session,url);status=None;links=[];outcome='skipped_robots_unknown' if allowed is None else 'skipped_robots_disallowed' if not allowed else 'error'
 if allowed:
  try:
   with session.get(url,timeout=20,allow_redirects=False,stream=True) as r:
    status=r.status_code
    if status==200 and 'html' in r.headers.get('Content-Type','').lower():
     data=bytearray()
     for chunk in r.iter_content(32768):
      data.extend(chunk)
      if len(data)>max_bytes:raise ValueError('HTML exceeds max bytes')
     html=data.decode('utf-8','replace')
     record_html(db,sid,url,parent,depth,html)
     links=parse_html(html,url,limit=500)['links']
     outcome='inspected'
    else:outcome='http_or_non_html'
  except Exception as exc:outcome='error_'+type(exc).__name__
 db.execute('''INSERT INTO targeted_pages_v2(source_id,url,parent_url,depth,robots_allowed,http_status,outcome,checked_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,url) DO UPDATE SET outcome=excluded.outcome,http_status=excluded.http_status,checked_at=excluded.checked_at''',(sid,url,parent,depth,allowed,status,outcome,now()))
 db.execute('''INSERT INTO source_access_log(source_id,url,robots_allowed,robots_reason,http_status,outcome,checked_at) VALUES(?,?,?,?,?,?,?)''',(sid,url,allowed,reason,status,outcome,now()))
 db.execute('UPDATE catalogue_nodes SET inspected=1 WHERE source_id=? AND url=? AND ?="inspected"',(sid,url,outcome))
 found=ingest_page_links(db,sid,slug,url,links,depth) if outcome=='inspected' else []
 db.commit()
 if delay:time.sleep(delay)
 return {'source':slug,'url':url,'depth':depth,'status':outcome,'http_status':status,'robots_allowed':allowed,'robots_reason':reason,'links_found':len(links),'classified':len(found)}

def run_targeted(session,db,slugs,max_pages=8,max_depth=5,delay=1.5):
 """Priority-first navigation within explicit target scopes. No general-purpose crawling."""
 output=[]
 for slug in slugs:
  if slug not in TARGETS:continue
  target=TARGETS[slug]
  row=db.execute('SELECT id FROM sources WHERE slug=?',(slug,)).fetchone()
  if not row:continue
  sid=row[0];seed=target['seed'];queue=[(seed,None,0,9999)];seen=set();processed=0
  while queue and processed<max_pages:
   queue.sort(key=lambda x:(-x[3],x[2],x[0]))
   url,parent,depth,_=queue.pop(0)
   if url in seen or depth>max_depth:continue
   seen.add(url)
   if not same_origin(seed,url):continue
   if slug=='charm' and not url.startswith('https://charm.li/Suzuki/2007/'):continue
   if slug=='bmwteka' and not (url.startswith('https://bmwteka.com/en/tis/E36') or url.startswith('https://bmwteka.com/en/wds/') or url.startswith('https://bmwteka.com/en/tis/documents/')):continue
   entry=inspect_target(session,db,sid,slug,url,parent,depth,delay=delay)
   output.append(entry);processed+=1
   if entry['status']!='inspected' or depth>=max_depth:continue
   # labels are retained in technical_candidates_v3; prioritize semantics over alphabetical URL ordering.
   candidates=db.execute('SELECT url,title FROM technical_candidates_v3 WHERE source_id=? AND parent_url=?',(sid,url)).fetchall()
   for candidate,label in candidates:
    if candidate not in seen:queue.append((candidate,url,depth+1,rank(candidate,label or '',slug)))
 return output

def export_targeted(db):
 models=[{'brand':b,'model':m,'year':y,'engine':e,'drivetrain':d,'status':s,'evidence_url':u} for b,m,y,e,d,s,u in db.execute('''SELECT mf.name,vm.code,v.model_year,v.engine,v.drivetrain,v.status,v.evidence_url FROM vehicle_variants_v2 v JOIN vehicle_models vm ON vm.id=v.model_id JOIN manufacturers mf ON mf.id=vm.manufacturer_id ORDER BY mf.name,vm.code,v.model_year''')]
 docs=[{'source':s,'url':u,'parent_url':p,'title':t,'classification':c,'status':st} for s,u,p,t,c,st in db.execute('''SELECT src.slug,d.url,d.parent_url,d.title,d.classification,d.status FROM target_documents_v2 d JOIN sources src ON src.id=d.source_id ORDER BY src.slug,d.classification,d.url''')]
 return models,docs

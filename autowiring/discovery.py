"""Bounded, source-agnostic catalogue discovery. No technical wiring inference."""
import json, re, sqlite3, time
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
from .core import model_id, parse_html, robots_check, same_origin, USER_AGENT

YEAR_RE = re.compile(r'^(19\d{2}|20\d{2})$')
BMW_RE = re.compile(r'^[EFGUiM]\d{2}$', re.I)


def extend_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS catalogue_nodes(
      id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
      parent_id INTEGER REFERENCES catalogue_nodes(id), url TEXT NOT NULL,
      node_type TEXT NOT NULL, label TEXT, manufacturer_id INTEGER REFERENCES manufacturers(id),
      model_id INTEGER REFERENCES vehicle_models(id), model_year INTEGER,
      inspected INTEGER NOT NULL DEFAULT 0, discovered_at TEXT NOT NULL,
      UNIQUE(source_id,url));
    CREATE TABLE IF NOT EXISTS discovery_evidence(
      id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
      url TEXT NOT NULL, category TEXT NOT NULL, label TEXT NOT NULL,
      evidence_url TEXT NOT NULL, confidence TEXT NOT NULL DEFAULT 'catalogue_link',
      created_at TEXT NOT NULL, UNIQUE(source_id,url,category,label));
    CREATE TABLE IF NOT EXISTS source_access_log(
      id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id), url TEXT NOT NULL,
      robots_allowed INTEGER, robots_reason TEXT, http_status INTEGER,
      outcome TEXT NOT NULL, checked_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_catalogue_brand ON catalogue_nodes(manufacturer_id,model_year);
    ''')
    db.commit()


def now(): return datetime.now(timezone.utc).isoformat()


def manufacturer_id(db, name):
    db.execute('INSERT OR IGNORE INTO manufacturers(name) VALUES(?)',(name,))
    return db.execute('SELECT id FROM manufacturers WHERE name=?',(name,)).fetchone()[0]


def classify_link(slug, target, label):
    """Return (node_type, brand, model, year). Never invent missing model."""
    path = [unquote(x) for x in urlparse(target).path.strip('/').split('/') if x]
    if slug == 'charm':
        if len(path) == 1 and path[0].lower() not in ('about.html',):
            return 'manufacturer',path[0],None,None
        if len(path) >= 2 and YEAR_RE.fullmatch(path[1]):
            brand = path[0]; year=int(path[1])
            if len(path)==2: return 'year',brand,None,year
            # Model name is visible in link label, but not always a normalized model.
            if len(path)==3: return 'model_candidate',brand,path[2],year
            return 'document_candidate',brand,path[2],year
    if slug == 'bmwteka':
        if len(path)>=3 and path[:2]==['en','bmw'] and BMW_RE.fullmatch(path[2]):
            return 'model','BMW',path[2].upper(),None
        if len(path)>=3 and path[:2]==['en','tis']:
            if path[2].lower()=='documents': return 'repair_document_candidate','BMW',None,None
            if BMW_RE.fullmatch(path[2]): return 'repair_catalogue','BMW',path[2].upper(),None
        if len(path)>=3 and path[:2]==['en','wds']:
            return 'wiring_candidate','BMW',None,None
    if slug == 'wds':
        if len(path)>=2 and path[0]=='en' and re.fullmatch(r'e\d{2}(old|new)?|e\d{2}e\d{2}',path[1],re.I):
            return 'model_candidate','BMW',path[1].upper(),None
    return None,None,None,None


def record_link(db, source_id, slug, parent_url, item):
    if item['kind']!='page': return None
    target=item['url']; label=item.get('label','')
    typ,brand,model,year=classify_link(slug,target,label)
    if not typ: return None
    brand_id=manufacturer_id(db,brand) if brand else None
    # Do not normalize ambiguous candidate models as verified vehicles.
    mid=model_id(db,brand,model) if model and typ in ('model','repair_catalogue') else None
    db.execute('''INSERT INTO catalogue_nodes(source_id,url,node_type,label,manufacturer_id,model_id,model_year,discovered_at)
       VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,url) DO UPDATE SET label=excluded.label''',
       (source_id,target,typ,label,brand_id,mid,year,now()))
    db.execute('''INSERT OR IGNORE INTO discovery_evidence(source_id,url,category,label,evidence_url,created_at)
       VALUES(?,?,?,?,?,?)''',(source_id,target,typ,label,parent_url,now()))
    return {'url':target,'type':typ,'brand':brand,'model':model,'year':year,'label':label}


def import_report(db, report):
    """Offline reprocess of v0.2/v0.2.1 JSON, without network access."""
    out=[]
    for r in report.get('sources',[]):
        slug=r['source']; src=db.execute('SELECT id FROM sources WHERE slug=?',(slug,)).fetchone()
        if not src:
            db.execute('INSERT INTO sources(slug,base_url,last_status,robots_status,checked_at) VALUES(?,?,?,?,?)',
                       (slug,r['url'],r.get('status'),r.get('robots_reason'),now()))
            src=db.execute('SELECT id FROM sources WHERE slug=?',(slug,)).fetchone()
        source_id=src[0]
        cfg_brand={'charm':'Suzuki','bmwteka':'BMW','wds':'BMW','etm':'BMW'}.get(slug)
        if cfg_brand: manufacturer_id(db,cfg_brand)
        for item in r.get('links',[]):
            found=record_link(db,source_id,slug,r['url'],item)
            if found: out.append({'source':slug,**found})
    db.commit()
    return out


def fetch_bounded(session,db,source_id,slug,url,delay=1.0,max_bytes=1_500_000):
    allowed,reason=robots_check(session,url)
    outcome='skipped_robots_unknown' if allowed is None else 'skipped_robots_disallowed' if not allowed else 'error'
    status=None; found=[]
    if allowed:
        try:
            # No redirects: cross-origin redirect must not be followed automatically.
            with session.get(url,timeout=18,stream=True,allow_redirects=False) as response:
                status=response.status_code
                if status==200 and 'html' in response.headers.get('Content-Type','').lower():
                    data=bytearray()
                    for chunk in response.iter_content(32768):
                        data.extend(chunk)
                        if len(data)>max_bytes: raise ValueError('page too large')
                    info=parse_html(data.decode('utf-8','replace'),url)
                    for item in info['links']:
                        if same_origin(url,item['url']):
                            row=record_link(db,source_id,slug,url,item)
                            if row: found.append(row)
                    outcome='inspected'
                else: outcome='non_html_or_http_error'
        except (Exception) as e:
            # Failure isolated to one page, captured for audit.
            outcome='error:'+type(e).__name__
    db.execute('INSERT INTO source_access_log(source_id,url,robots_allowed,robots_reason,http_status,outcome,checked_at) VALUES(?,?,?,?,?,?,?)',
               (source_id,url,allowed,reason,status,outcome,now()))
    db.execute('UPDATE catalogue_nodes SET inspected=? WHERE source_id=? AND url=?',(int(outcome=='inspected'),source_id,url))
    db.commit()
    if delay: time.sleep(delay)
    return {'url':url,'source':slug,'status':outcome,'http_status':status,'robots_allowed':allowed,'discovered':found}


def next_targets(db,slug,limit):
    """Whitelisted small next-hop samples; never bulk crawl."""
    patterns={
      'charm':('year','model_candidate'),
      'bmwteka':('repair_catalogue','model'),
      'wds':('model_candidate',)
    }.get(slug,())
    if not patterns:return []
    placeholders=','.join('?' for _ in patterns)
    sql=f'''SELECT n.url,n.node_type FROM catalogue_nodes n JOIN sources s ON s.id=n.source_id
        WHERE s.slug=? AND n.node_type IN ({placeholders}) AND n.inspected=0 ORDER BY
        CASE WHEN n.model_year=2007 THEN 0 WHEN n.label LIKE '%E36%' THEN 1 ELSE 2 END,n.url LIMIT ?'''
    return db.execute(sql,(slug,*patterns,limit)).fetchall()


def summary(db):
    counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
            ('manufacturers','vehicle_models','catalogue_nodes','discovery_evidence','source_access_log','diagrams','connectors')}
    brands=[x[0] for x in db.execute('SELECT name FROM manufacturers ORDER BY name')]
    nodes=[dict(source=s,category=t,count=n) for s,t,n in db.execute('''SELECT s.slug,n.node_type,COUNT(*)
       FROM catalogue_nodes n JOIN sources s ON s.id=n.source_id GROUP BY s.slug,n.node_type ORDER BY s.slug,n.node_type''')]
    return {'counts':counts,'manufacturers':brands,'node_breakdown':nodes,
            'warning':'Catalogue candidates are not verified wiring diagrams, pinouts, or component locations.'}

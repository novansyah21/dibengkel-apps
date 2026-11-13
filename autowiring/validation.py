"""Bounded image validation. Format verification != wiring diagram verification."""
import hashlib,json,time,re,ipaddress,socket
from pathlib import Path
from urllib.parse import urlparse
from io import BytesIO
from .core import robots_check
from .discovery import now

MAX_BYTES=3_000_000

def install(db):
 db.executescript("""
 CREATE TABLE IF NOT EXISTS asset_checks_v4 (
  id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,page_url TEXT NOT NULL,
  asset_url TEXT NOT NULL,fetch_status TEXT NOT NULL,robots_allowed INTEGER,
  http_status INTEGER,content_type TEXT,format TEXT,width INTEGER,height INTEGER,
  byte_size INTEGER,sha256 TEXT,local_path TEXT,error TEXT,checked_at TEXT NOT NULL,
  diagram_review_status TEXT NOT NULL DEFAULT 'unreviewed',
  applicability_status TEXT NOT NULL DEFAULT 'unverified',
  UNIQUE(source_id,page_url,asset_url));
 """);db.commit()

def safe_public_host(url):
 p=urlparse(url)
 if p.scheme!='https' or not p.hostname or p.username or p.password:return False
 try:
  infos=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
  return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
 except (OSError,ValueError):return False

def magic(data):
 if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
 if data.startswith(b'\xff\xd8\xff'):return 'jpeg'
 if data.startswith((b'GIF87a',b'GIF89a')):return 'gif'
 if data[:4]==b'RIFF' and data[8:12]==b'WEBP':return 'webp'
 if data.startswith(b'%PDF-'):return 'pdf'
 return None

def eligible(url):
 p=urlparse(url)
 return p.scheme=='https' and bool(re.search(r'/images/|\.(?:png|jpg|jpeg|webp|gif|pdf)(?:$|\?)',p.path,re.I)) and not re.search(r'/icons/|/logo|/sprite|/tracking',p.path,re.I)

def candidates(db,source=None,limit=10):
 q="""SELECT a.source_id,s.slug,a.page_url,a.asset_url FROM technical_assets_v3 a JOIN sources s ON s.id=a.source_id WHERE a.asset_kind='image'"""
 args=[]
 if source:q+=' AND s.slug=?';args.append(source)
 q+=" ORDER BY CASE WHEN a.asset_url LIKE '%/images/%' THEN 0 ELSE 1 END,a.asset_url"
 rows=[r for r in db.execute(q,args) if eligible(r[3])]
 return rows[:limit]

def run(session,db,out,source=None,limit=10,fetch=False,rights=False,delay=1.5):
 install(db);out=Path(out);assets_dir=out/'review_assets';results=[]
 for sid,slug,page,url in candidates(db,source,limit):
  result=dict(source=slug,page_url=page,asset_url=url,fetch_status='not_fetched',robots_allowed=None,http_status=None,content_type=None,format=None,width=None,height=None,byte_size=None,sha256=None,local_path=None,error=None,diagram_review_status='unreviewed',applicability_status='unverified')
  if fetch:
   if not rights:raise ValueError('Fetching requires --rights-confirmed (permission to retrieve for local review).')
   if not safe_public_host(url):result['fetch_status']='blocked_nonpublic_or_unresolved_host'
   else:
    allowed,reason=robots_check(session,url);result['robots_allowed']=allowed
    if allowed is not True:result.update(fetch_status='skipped_robots',error=reason)
    else:
     try:
      with session.get(url,stream=True,timeout=20,allow_redirects=False) as resp:
       result['http_status']=resp.status_code;result['content_type']=resp.headers.get('Content-Type','')[:120]
       if resp.status_code!=200:result['fetch_status']='http_error'
       elif 'image/' not in result['content_type'].lower() and 'application/pdf' not in result['content_type'].lower():result['fetch_status']='not_image_or_pdf'
       else:
        data=bytearray()
        for chunk in resp.iter_content(32768):
         data.extend(chunk)
         if len(data)>MAX_BYTES:raise ValueError('max asset size exceeded')
        fmt=magic(data);result['format']=fmt;result['byte_size']=len(data)
        if not fmt:result['fetch_status']='unknown_signature'
        else:
         result['sha256']=hashlib.sha256(data).hexdigest()
         if fmt!='pdf':
          try:
           from PIL import Image
           with Image.open(BytesIO(data)) as img:
            img.verify()
           with Image.open(BytesIO(data)) as img:result['width'],result['height']=img.size
          except Exception as exc:raise ValueError('image_decode_failed:'+type(exc).__name__)
         assets_dir.mkdir(parents=True,exist_ok=True)
         name=result['sha256'][:20]+'.'+fmt;local=assets_dir/name
         local.write_bytes(data);result['local_path']=str(local.relative_to(out));result['fetch_status']='format_verified'
     except Exception as exc:result.update(fetch_status='fetch_error',error=str(exc)[:200])
   if delay:time.sleep(delay)
  db.execute("""INSERT INTO asset_checks_v4(source_id,page_url,asset_url,fetch_status,robots_allowed,http_status,content_type,format,width,height,byte_size,sha256,local_path,error,checked_at)
  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,page_url,asset_url) DO UPDATE SET fetch_status=excluded.fetch_status,robots_allowed=excluded.robots_allowed,http_status=excluded.http_status,content_type=excluded.content_type,format=excluded.format,width=excluded.width,height=excluded.height,byte_size=excluded.byte_size,sha256=excluded.sha256,local_path=excluded.local_path,error=excluded.error,checked_at=excluded.checked_at""",
  (sid,page,url,result['fetch_status'],result['robots_allowed'],result['http_status'],result['content_type'],result['format'],result['width'],result['height'],result['byte_size'],result['sha256'],result['local_path'],result['error'],now()))
  results.append(result)
 db.commit()
 (out/'asset_validation.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
 import csv
 with (out/'manual_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['source','page_url','asset_url','local_path','format','width','height','fetch_status','is_wiring_diagram','vehicle_confirmed','electrical_system','reviewer_notes'])
  for r in results:w.writerow([r[k] for k in ('source','page_url','asset_url','local_path','format','width','height','fetch_status')]+['','','',''])
 return results

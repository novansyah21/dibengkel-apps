"""Source-aware PDF library: conservative discovery, authorized import, no bypass.

No login/session/cookie automation, robots bypass, or copyright assertion.
Network actions must be explicitly invoked by user. Default discovery is
dry-run. Only direct PDF responses are imported, with SHA256 dedup.
"""
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import sqlite3
import time
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
import uuid

USER_AGENT="AutoWiringSourceLibrary/0.4.1 (+manual authorized archival; no bypass)"
MAX_PDF=30*1024*1024
MAX_DISCOVERY_PAGES=3
MAX_PDF_LINKS=40
SCHEMA="""
CREATE TABLE IF NOT EXISTS pdf_source_catalog_v041(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,homepage TEXT NOT NULL,
 source_kind TEXT NOT NULL,notes TEXT NOT NULL,
 license_status TEXT NOT NULL DEFAULT 'unknown',
 enabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pdf_library_v041(
 id TEXT PRIMARY KEY,sha256 TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL,vehicle TEXT NOT NULL DEFAULT '',
 source_id TEXT NOT NULL DEFAULT 'manual',
 source_url TEXT NOT NULL,license_basis TEXT NOT NULL,
 file_name TEXT NOT NULL,bytes INTEGER NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
SOURCES=(
 ("charm","Operation CHARM","https://charm.li/","online_workshop_manual",
  "HTML/images workshop pages; not assumed to provide downloadable PDFs. Check terms and rights.", "unknown"),
 ("bmw_etm","BMW ETM Archive","https://shark.armchair.mb.ca/~dave/BMW/",
  "historical_pdf_archive","Some links lead to ETM PDFs; permission and robots must be checked per source.","unknown"),
 ("bmw_wds","BMW WDS","https://wds.psjr.org/en/",
  "interactive_diagrams","Wiring web app; not automatically a PDF source.","unknown"),
 ("bmwteka","BMWTeka","https://bmwteka.com/en",
  "service_catalog","Catalog/search pages, not assumed downloadable PDFs.","unknown"),
 ("carmanualsonline","CarManualsOnline","https://www.carmanualsonline.info/",
  "manual_catalog","Copyright/licensing varies. Do not bulk-copy without permission.","unknown"),
)
def init(dbpath):
    with sqlite3.connect(dbpath) as db:
        db.executescript(SCHEMA)
        for id,name,url,kind,notes,license_status in SOURCES:
            db.execute("""INSERT OR IGNORE INTO pdf_source_catalog_v041
             (id,name,homepage,source_kind,notes,license_status)
             VALUES(?,?,?,?,?,?)""",(id,name,url,kind,notes,license_status))
        db.commit()

def sources(dbpath):
    init(dbpath)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        return [dict(x) for x in db.execute(
            "SELECT * FROM pdf_source_catalog_v041 ORDER BY name")]

def documents(dbpath):
    init(dbpath)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        return [dict(x) for x in db.execute(
            "SELECT * FROM pdf_library_v041 ORDER BY imported_at DESC,rowid DESC")]

def _safe_host(host):
    if not host or host.lower()=="localhost" or host.endswith(".local"):
        raise ValueError("Local/private host not allowed")
    # Fail closed if any DNS resolution resolves to local/private/reserved.
    try:ips={x[4][0] for x in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)}
    except OSError as e:raise ValueError("Cannot resolve remote host") from e
    if not ips:raise ValueError("Unresolvable host")
    for ip in ips:
        obj=ipaddress.ip_address(ip)
        if not obj.is_global:raise ValueError("Non-public address blocked")

def _validate_url(url,allowed_host=None):
    if not isinstance(url,str) or len(url)>2048:raise ValueError("Invalid URL")
    parsed=urlparse(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTPS URLs without credentials are allowed")
    if parsed.port not in (None,443):raise ValueError("Nonstandard port blocked")
    if allowed_host and parsed.hostname.lower()!=allowed_host.lower():
        raise ValueError("Cross-domain URL blocked")
    _safe_host(parsed.hostname)
    return parsed

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError("Redirect not followed automatically; inspect destination first")

def _request(url,method="GET",timeout=15):
    _validate_url(url)
    return build_opener(_NoRedirect()).open(
        Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/pdf,text/html;q=0.8"},
                method=method),timeout=timeout)

def _robots(url):
    p=_validate_url(url)
    robots_url=p.scheme+"://"+p.netloc+"/robots.txt"
    # Never assume permission when robots.txt is unreachable or malformed.
    try:
        with _request(robots_url,timeout=10) as r:
            if r.status!=200:return False
            content=r.read(512_000).decode("utf-8","replace")
        parser=RobotFileParser()
        parser.parse(content.splitlines())
        return parser.can_fetch(USER_AGENT,url)
    except Exception:return False

class _Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag!="a":return
        href=dict(attrs).get("href","")
        if href:self.links.append(href)

def discover(url,max_pages=1):
    """One or few public index pages, PDF links only. No downloads or recursion."""
    p=_validate_url(url)
    if not 1<=max_pages<=MAX_DISCOVERY_PAGES:raise ValueError("Max 3 pages")
    if not _robots(url):raise PermissionError("robots.txt unavailable or disallows this page")
    # Explicit pages only, no recursive crawling or bulk pagination.
    with _request(url) as r:
        if "text/html" not in r.headers.get("Content-Type","").lower():
            raise ValueError("Discovery URL is not HTML")
        html=r.read(1_000_000).decode("utf-8","replace")
    parser=_Links();parser.feed(html)
    links=[];seen=set()
    for href in parser.links:
        link=urljoin(url,href)
        target=urlparse(link)
        if target.scheme!="https" or target.hostname!=p.hostname:continue
        if not re.search(r"\.pdf(?:$|[?#])",link,re.I):continue
        if link in seen:continue
        seen.add(link);links.append(link)
        if len(links)>=MAX_PDF_LINKS:break
    return {"source":url,"dry_run":True,"discovered_pdf_links":links,
            "downloaded":0,"note":"Discovery is not permission to download or redistribute. Check licensing and use import-pdf explicitly."}

def _clean(s,maxlen):
    s=" ".join(str(s or "").split())
    if not s or len(s)>maxlen or any(ord(c)<32 for c in s):
        raise ValueError("Missing or invalid metadata")
    return s

def import_pdf(dbpath,storage,url,title,vehicle,license_basis,source_id="manual",
               permission_confirmed=False):
    if permission_confirmed is not True:
        raise PermissionError("Explicit permission confirmation required")
    title=_clean(title,150)
    vehicle=_clean(vehicle,120)
    license_basis=_clean(license_basis,300)
    if license_basis.lower() in ("unknown","unsure","none","n/a"):
        raise PermissionError("Specify lawful personal-use/license basis")
    _validate_url(url)
    if not _robots(url):
        raise PermissionError("robots.txt unavailable or disallows this URL")
    init(dbpath)
    with sqlite3.connect(dbpath) as db:
        if source_id!="manual" and not db.execute(
            "SELECT 1 FROM pdf_source_catalog_v041 WHERE id=?",(source_id,)).fetchone():
            raise ValueError("Unknown source ID")
    # No redirects, auth, anti-bot bypass, browser scraping, or HTML-to-PDF copying.
    with _request(url,timeout=25) as r:
        size=r.headers.get("Content-Length")
        if size and int(size)>MAX_PDF:raise ValueError("PDF too large")
        chunks=[];length=0
        while True:
            chunk=r.read(min(256*1024,MAX_PDF+1-length))
            if not chunk:break
            length+=len(chunk)
            if length>MAX_PDF:raise ValueError("PDF exceeds 30 MB")
            chunks.append(chunk)
    raw=b"".join(chunks)
    if not raw.startswith(b"%PDF-"):
        raise ValueError("URL did not return PDF bytes")
    digest=hashlib.sha256(raw).hexdigest()
    folder=Path(storage);folder.mkdir(parents=True,exist_ok=True)
    file_name=digest+".pdf"
    target=folder/file_name
    if not target.exists():
        temp=folder/(uuid.uuid4().hex+".tmp")
        try:temp.write_bytes(raw);temp.replace(target)
        finally:temp.unlink(missing_ok=True)
    with sqlite3.connect(dbpath) as db:
        db.execute("""INSERT OR IGNORE INTO pdf_library_v041
          (id,sha256,title,vehicle,source_id,source_url,license_basis,file_name,bytes)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (uuid.uuid4().hex,digest,title,vehicle,source_id,url,
           license_basis,file_name,len(raw)))
        db.commit()
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT * FROM pdf_library_v041 WHERE sha256=?",
                       (digest,)).fetchone()
    return dict(row)

def add_local_pdf(dbpath,storage,local_file,title,vehicle,license_basis):
    """Import a PDF the user already lawfully possesses; no network or scraping."""
    title=_clean(title,150);vehicle=_clean(vehicle,120)
    license_basis=_clean(license_basis,300)
    p=Path(local_file)
    if not p.is_file() or p.stat().st_size>MAX_PDF:raise ValueError("PDF missing or too large")
    raw=p.read_bytes()
    if not raw.startswith(b"%PDF-"):raise ValueError("Not a PDF")
    digest=hashlib.sha256(raw).hexdigest()
    folder=Path(storage);folder.mkdir(parents=True,exist_ok=True)
    target=folder/(digest+".pdf")
    if not target.exists():target.write_bytes(raw)
    init(dbpath)
    with sqlite3.connect(dbpath) as db:
        db.execute("""INSERT OR IGNORE INTO pdf_library_v041
          (id,sha256,title,vehicle,source_id,source_url,license_basis,file_name,bytes)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (uuid.uuid4().hex,digest,title,vehicle,"local",
           "local_file:"+p.name,license_basis,target.name,len(raw)))
        db.commit()
        db.row_factory=sqlite3.Row
        return dict(db.execute("SELECT * FROM pdf_library_v041 WHERE sha256=?",
                               (digest,)).fetchone())

import argparse,json,sqlite3,shutil
from pathlib import Path
import requests
from autowiring.core import SOURCES,USER_AGENT,schema,inspect_one
from autowiring.discovery import extend_schema,import_report,summary
from autowiring.targeted import migrate,promote_candidates,run_targeted,export_targeted
from autowiring.technical import install,export
from autowiring.validation import install as install_validation,run as run_validation

def main():
 p=argparse.ArgumentParser(description='AutoWiring v0.2.4 technical multi-brand discovery')
 p.add_argument('--fetch-assets',action='store_true',help='Fetch a few permitted assets for local review');p.add_argument('--rights-confirmed',action='store_true',help='Confirm you have permission to retrieve assets for local review');p.add_argument('--asset-limit',type=int,default=10);p.add_argument('--asset-source',choices=['charm','bmwteka']);p.add_argument('--out',default='output');p.add_argument('--import-report');p.add_argument('--existing-db');p.add_argument('--live',action='store_true');p.add_argument('--deep',action='store_true');p.add_argument('--sources',nargs='+',choices=list(SOURCES),default=['charm','bmwteka']);p.add_argument('--max-pages-per-source',type=int,default=10);p.add_argument('--max-depth',type=int,default=5);p.add_argument('--delay',type=float,default=1.5)
 a=p.parse_args()
 if not (a.import_report or a.existing_db or a.live):p.error('Supply --import-report, --existing-db or --live')
 if not 0<=a.max_pages_per_source<=30:p.error('max-pages-per-source must be 0..30')
 if not 0<=a.max_depth<=8:p.error('max-depth must be 0..8')
 if a.delay<0:p.error('delay cannot be negative')
 if not 0<=a.asset_limit<=30:p.error('asset-limit must be 0..30')
 if a.fetch_assets and not a.rights_confirmed:p.error('--fetch-assets requires --rights-confirmed')
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);path=out/'autowiring.db'
 if a.existing_db and not path.exists():shutil.copy2(a.existing_db,path)
 db=sqlite3.connect(path);db.execute('PRAGMA foreign_keys=ON');schema(db);extend_schema(db);migrate(db);install(db);install_validation(db)
 imported=[];checks=[]
 if a.import_report:
  report=json.loads(Path(a.import_report).read_text(encoding='utf-8'))
  if 'sources' in report:imported=import_report(db,report)
  elif 'discovered' in report:
   # Re-import observed links from a v0.2.1 report without treating them as verified facts.
   for item in report['discovered']:
    slug=item['source'];url=item['url'];parent=item.get('parent_url') or item.get('evidence_url') or url
    sid=db.execute('SELECT id FROM sources WHERE slug=?',(slug,)).fetchone()
    if sid:
     from autowiring.discovery import record_link
     rec=record_link(db,sid[0],slug,parent,{'url':url,'kind':'page','label':item.get('label','')})
     if rec:imported.append({'source':slug,**rec})
   db.commit()
 session=requests.Session();session.headers.update({'User-Agent':USER_AGENT})
 if a.live:
  for slug in a.sources:
   result=inspect_one(session,db,slug,SOURCES[slug]);checks.append({'source':slug,'url':result['url'],'status':result['status']});imported.extend(import_report(db,{'sources':[result]}))
 normalized=promote_candidates(db)
 if a.deep:
  checks.extend(run_targeted(session,db,a.sources,a.max_pages_per_source,a.max_depth,a.delay))
  normalized+=promote_candidates(db)
 # Classify existing observed repair-document links, preserving their evidence parent.
 from autowiring.targeted import classify_document
 for sid,url,label,parent in db.execute("""SELECT n.source_id,n.url,n.label,e.evidence_url FROM catalogue_nodes n JOIN discovery_evidence e ON e.source_id=n.source_id AND e.url=n.url WHERE n.node_type IN ('repair_document_candidate','wiring_candidate','document_candidate')""").fetchall():
  db.execute('INSERT OR IGNORE INTO target_documents_v2(source_id,url,parent_url,title,classification,evidence,discovered_at) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)',(sid,url,parent,label,classify_document(url,label),'link_text_and_url_only'))
 db.commit()
 models,docs=export_targeted(db);s=summary(db)
 s['counts']['vehicle_variants']=len(models);s['counts']['target_documents']=len(docs);s['counts']['targeted_pages']=db.execute('SELECT COUNT(*) FROM targeted_pages_v2').fetchone()[0]
 s['normalized_candidates_this_run']=normalized
 candidates,assets=export(db)
 asset_checks=run_validation(session,db,out,source=a.asset_source,limit=a.asset_limit,fetch=a.fetch_assets,rights=a.rights_confirmed,delay=a.delay)
 s['counts']['technical_pages']=db.execute('SELECT COUNT(*) FROM technical_pages_v3').fetchone()[0]
 s['counts']['technical_candidates']=len(candidates)
 s['counts']['technical_assets']=len(assets)
 s['counts']['asset_checks_v4']=len(asset_checks)
 s['counts']['format_verified_assets']=sum(x['fetch_status']=='format_verified' for x in asset_checks)
 s['counts']['wiring_candidates']=sum(c['category']=='wiring_diagram_candidate' for c in candidates)
 (out/'discovery_report.json').write_text(json.dumps({'version':'0.2.4','checks':checks,'imported':len(imported),'summary':s},indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'vehicle_catalog.json').write_text(json.dumps({'variants':models,'note':'All variants are candidates derived from observed catalogue links, not mechanically verified.'},indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'document_candidates.json').write_text(json.dumps(docs,indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'source_capabilities.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'technical_candidates.json').write_text(json.dumps(candidates,indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'technical_assets.json').write_text(json.dumps(assets,indent=2,ensure_ascii=False),encoding='utf-8')
 (out/'diagram_samples.json').write_text('[]\n',encoding='utf-8')
 (out/'summary.md').write_text(f"# AutoWiring v0.2.4\n\n- Manufacturers: {', '.join(s['manufacturers'])}\n- Catalogue nodes: {s['counts']['catalogue_nodes']}\n- Candidate variants: {len(models)}\n- Document candidates: {len(docs)}\n- Targeted pages inspected/attempted (cumulative): {s['counts']['targeted_pages']}\n- Verified wiring diagrams: {s['counts']['diagrams']}\n\nCandidates are **not verified** wiring diagrams or pinouts. Inspect source licenses before reuse.\n",encoding='utf-8')
 print(json.dumps(s,indent=2,ensure_ascii=False));print('Output:',out.resolve());db.close()
if __name__=='__main__':main()

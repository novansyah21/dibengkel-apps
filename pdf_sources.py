"""AutoWiring PDF library CLI: explicit, bounded and rights-aware.

Usage:
  py pdf_sources.py sources
  py pdf_sources.py discover --url https://example.org/public-index/
  py pdf_sources.py add-local --file C:\manuals\my.pdf --title "..." --vehicle "..." --rights "personal licensed copy"
  py pdf_sources.py import-url --url https://example.org/manual.pdf --title "..." --vehicle "..." --rights "permission from rights holder" --confirm-rights
  py pdf_sources.py list
"""
import argparse
import json
from pathlib import Path
from autowiring.pdf_library import sources,documents,discover,import_pdf,add_local_pdf

ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser(description="AutoWiring local PDF source library")
    parser.add_argument("--db",default=str(ROOT/"output"/"autowiring.db"))
    parser.add_argument("--storage",default=str(ROOT/"output"/"pdf_library"))
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("sources",help="Show curated reference sites and license status")
    sub.add_parser("list",help="Show stored PDF documents")
    disc=sub.add_parser("discover",help="Dry-run: list direct PDF links on one public HTML index")
    disc.add_argument("--url",required=True)
    add=sub.add_parser("add-local",help="Add your own lawful PDF")
    add.add_argument("--file",required=True)
    down=sub.add_parser("import-url",help="Download one explicitly authorized public PDF")
    down.add_argument("--url",required=True)
    down.add_argument("--confirm-rights",action="store_true",
                      help="I confirm permission/lawful use and will not redistribute")
    down.add_argument("--source-id",default="manual")
    for p in (add,down):
        p.add_argument("--title",required=True)
        p.add_argument("--vehicle",required=True)
        p.add_argument("--rights",required=True,
                       help="Specific lawful-use basis, e.g. permission or applicable license")
    args=parser.parse_args()
    db=Path(args.db);db.parent.mkdir(parents=True,exist_ok=True)
    try:
        if args.command=="sources":result=sources(db)
        elif args.command=="list":result=documents(db)
        elif args.command=="discover":result=discover(args.url)
        elif args.command=="add-local":
            result=add_local_pdf(db,args.storage,args.file,args.title,args.vehicle,args.rights)
        else:
            result=import_pdf(db,args.storage,args.url,args.title,args.vehicle,
                              args.rights,args.source_id,args.confirm_rights)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except (ValueError,PermissionError,OSError) as exc:
        parser.exit(2,"PDF library: "+str(exc)+"\n")
if __name__=="__main__":main()

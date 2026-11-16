"""v0.4.2 vehicle-first document search and single-page PDF wiring import.

Never infer a vehicle from a PDF filename or a diagram's OCR text. A
*user-confirmed metadata association* is not electrical/variant validation.
Matching is exact on brand, model, year, variant and powertrain. Legacy seeded
demo diagrams are excluded from search even when they had older bindings.
"""
from pathlib import Path
import hashlib
import re
import sqlite3
import uuid

SCHEMA="""
CREATE TABLE IF NOT EXISTS pdf_vehicle_v042(
 pdf_id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,
 system TEXT NOT NULL DEFAULT 'other',
 applicability TEXT NOT NULL DEFAULT 'user_declared_unverified',
 linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(pdf_id) REFERENCES pdf_library_v041(id),
 FOREIGN KEY(profile_id) REFERENCES vehicle_profiles_v0400(id)
);
CREATE TABLE IF NOT EXISTS pdf_page_diagrams_v042(
 diagram_id TEXT PRIMARY KEY,pdf_id TEXT NOT NULL,
 page_number INTEGER NOT NULL,system TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(pdf_id,page_number),
 FOREIGN KEY(pdf_id) REFERENCES pdf_library_v041(id),
 FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id),
 FOREIGN KEY(profile_id) REFERENCES vehicle_profiles_v0400(id)
);
CREATE TABLE IF NOT EXISTS diagram_system_v042(
 diagram_id TEXT PRIMARY KEY,system TEXT NOT NULL,
 FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id)
);
CREATE INDEX IF NOT EXISTS idx_pdf_vehicle_profile_v042 ON pdf_vehicle_v042(profile_id);
CREATE INDEX IF NOT EXISTS idx_pdf_page_profile_v042 ON pdf_page_diagrams_v042(profile_id);
"""
SYSTEMS={
    "other":"Unclassified / perlu review",
    "power_distribution":"Power Distribution / Fuse Box",
    "starting":"Starting System",
    "charging":"Charging System",
    "engine_management":"Engine Management",
    "cooling_fan":"Cooling Fan",
    "lighting":"Lighting",
    "body":"Body Electrical",
    "abs":"ABS",
}
LEGACY_SEEDS={"junction_block","abbreviations","bcm_wiring"}
MAX_PAGES=3000
MAX_PDF_BYTES=100*1024*1024
MAX_EDGE=4000
MAX_PIXELS=12_000_000

def init(dbpath):
    with sqlite3.connect(dbpath) as db:
        db.executescript(SCHEMA)

def _profile(db,profile_id):
    db.row_factory=sqlite3.Row
    p=db.execute("""SELECT p.*,b.name brand_name,m.name model_name
         FROM vehicle_profiles_v0400 p
         JOIN vehicle_brands_v0400 b ON b.id=p.brand_id
         JOIN vehicle_models_v0400 m ON m.id=p.model_id
         WHERE p.id=?""",(profile_id,)).fetchone()
    if p is None:raise ValueError("Vehicle profile not found; save your vehicle first")
    return dict(p)

def _source_pdf(db,pdf_id):
    db.row_factory=sqlite3.Row
    row=db.execute("SELECT * FROM pdf_library_v041 WHERE id=?",(pdf_id,)).fetchone()
    if row is None:raise ValueError("PDF not found in local library")
    if not re.fullmatch(r"[0-9a-f]{64}\.pdf",row["file_name"]):
        raise ValueError("Invalid registered PDF filename")
    return dict(row)

def _system(value):
    if value not in SYSTEMS:raise ValueError("Unknown electrical system")
    return value

def attach_pdf(dbpath,pdf_id,profile_id,system,confirmed=False):
    """Requires deliberate user confirmation and an existing local PDF.

    Prevent relabeling an already-associated PDF as a different vehicle.
    One PDF -> one exact vehicle profile, never arbitrary inferred compatibility.
    """
    if confirmed is not True:
        raise ValueError("You must confirm that this PDF belongs to this exact vehicle/variant")
    system=_system(system)
    with sqlite3.connect(dbpath) as db:
        _profile(db,profile_id);_source_pdf(db,pdf_id)
        existing=db.execute("SELECT profile_id FROM pdf_vehicle_v042 WHERE pdf_id=?",(pdf_id,)).fetchone()
        if existing and existing[0]!=profile_id:
            raise ValueError("PDF already associated with another vehicle; cannot silently reassign")
        db.execute("""INSERT INTO pdf_vehicle_v042(pdf_id,profile_id,system)
           VALUES(?,?,?)
           ON CONFLICT(pdf_id) DO UPDATE SET system=excluded.system""",
           (pdf_id,profile_id,system))
        db.commit()
    return {"pdf_id":pdf_id,"profile_id":profile_id,"system":system,
            "applicability":"user_declared_unverified"}

def attach_diagram(dbpath,diagram_id,profile_id,system,confirmed=False):
    """Classify user-imported PNG/JPEG. Seed examples cannot be relabeled."""
    if confirmed is not True:raise ValueError("Confirm exact vehicle/diagram applicability")
    system=_system(system)
    if diagram_id in LEGACY_SEEDS:raise ValueError("Legacy sample diagrams cannot be reclassified")
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        _profile(db,profile_id)
        diagram=db.execute("SELECT id,source_url FROM viewer_diagrams WHERE id=?",
                           (diagram_id,)).fetchone()
        if diagram is None:raise ValueError("Diagram not found")
        if not diagram_id.startswith("upload_"):
            raise ValueError("Only user-uploaded diagrams can be manually classified")
        current=db.execute("SELECT profile_id FROM diagram_vehicle_v0400 WHERE diagram_id=?",
                           (diagram_id,)).fetchone()
        if current and current[0]!=profile_id:
            raise ValueError("Diagram already linked to another vehicle")
        db.execute("""INSERT INTO diagram_vehicle_v0400(diagram_id,profile_id)
               VALUES(?,?) ON CONFLICT(diagram_id) DO NOTHING""",
               (diagram_id,profile_id))
        db.execute("""INSERT INTO diagram_system_v042(diagram_id,system)
               VALUES(?,?) ON CONFLICT(diagram_id) DO UPDATE SET system=excluded.system""",
               (diagram_id,system))
        db.commit()
    return {"diagram_id":diagram_id,"profile_id":profile_id,"system":system,
            "applicability":"user_declared_unverified"}

def _selection(query):
    """Incomplete selection matches nothing; no implicit year/variant widening."""
    if not isinstance(query,dict):raise ValueError("Invalid vehicle selection")
    brand_id=str(query.get("brand_id") or "").strip()
    model_id=str(query.get("model_id") or "").strip()
    variant=str(query.get("variant") or "").strip()
    powertrain=str(query.get("powertrain") or "").strip()
    raw_year=query.get("year")
    if not brand_id or not model_id or not str(raw_year or "").strip():return None
    try:year=int(raw_year)
    except (ValueError,TypeError):raise ValueError("Invalid vehicle year")
    if not 1950<=year<=2035:raise ValueError("Invalid vehicle year")
    if len(variant)>120:raise ValueError("Variant too long")
    if powertrain not in ("unknown","gasoline","diesel","hybrid","plug_in_hybrid","electric"):
        raise ValueError("Invalid powertrain")
    return (brand_id,model_id,year,variant.casefold(),powertrain)

def search(dbpath,query):
    """Return only diagrams and PDFs linked to EXACT requested vehicle identity.

    Deliberately excludes legacy built-in demos from filtered results. A PDF
    entry is not itself a rendered viewer diagram until an individual page is
    selected and imported.
    """
    wanted=_selection(query)
    out={"diagrams":[],"pdfs":[],"match_policy":"exact_profile",
         "applicability":"user_declared_unverified_not_technical_verification",
         "has_vehicle":bool(wanted)}
    if wanted is None:return out
    init(dbpath)
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        profile_ids=[r[0] for r in db.execute("""SELECT p.id
           FROM vehicle_profiles_v0400 p
           JOIN vehicle_models_v0400 m ON m.id=p.model_id
           WHERE p.brand_id=? AND p.model_id=? AND m.brand_id=p.brand_id
             AND p.year=? AND lower(trim(p.variant))=? AND p.powertrain=?""",wanted)]
        if not profile_ids:return out
        marks=",".join("?" for _ in profile_ids)
        # User-uploaded images or PDF pages only. Do NOT auto-select seed examples.
        diagrams=db.execute(f"""SELECT d.id,d.title,d.image_file,d.width,d.height,
            COALESCE(s.system,'other') system,link.profile_id,
            COALESCE(pd.pdf_id,'') pdf_id,COALESCE(pd.page_number,0) page_number
            FROM viewer_diagrams d
            JOIN diagram_vehicle_v0400 link ON link.diagram_id=d.id
            LEFT JOIN diagram_system_v042 s ON s.diagram_id=d.id
            LEFT JOIN pdf_page_diagrams_v042 pd ON pd.diagram_id=d.id
            WHERE link.profile_id IN ({marks})
              AND (d.id LIKE 'upload_%' OR pd.diagram_id IS NOT NULL)
            ORDER BY d.title""",profile_ids).fetchall()
        out["diagrams"]=[dict(x) for x in diagrams]
        pdfs=db.execute(f"""SELECT doc.id,doc.title,doc.bytes,doc.file_name,doc.license_basis,
             tag.system,tag.profile_id,tag.applicability
             FROM pdf_vehicle_v042 tag JOIN pdf_library_v041 doc ON doc.id=tag.pdf_id
             WHERE tag.profile_id IN ({marks}) ORDER BY doc.title""",profile_ids).fetchall()
        out["pdfs"]=[dict(x) for x in pdfs]
    return out

def _pdf_path(dbpath,storage,pdf_id):
    with sqlite3.connect(dbpath) as db:
        doc=_source_pdf(db,pdf_id)
    path=Path(storage)/doc["file_name"]
    if not path.is_file():raise ValueError("PDF is registered, but its local file is missing")
    if path.stat().st_size>MAX_PDF_BYTES:raise ValueError("PDF exceeds size limit")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=doc["sha256"]:
        raise ValueError("PDF checksum mismatch; refusing to open modified file")
    return doc,path

def pdf_info(dbpath,storage,pdf_id):
    with sqlite3.connect(dbpath) as db:
        _source_pdf(db,pdf_id)
    doc,path=_pdf_path(dbpath,storage,pdf_id)
    try:import fitz
    except ImportError as exc:
        raise RuntimeError("PDF rendering requires PyMuPDF. Install: py -m pip install pymupdf") from exc
    try:
        with fitz.open(str(path)) as pdf:
            if pdf.needs_pass:raise ValueError("Password-protected PDF not supported")
            pages=pdf.page_count
    except ValueError:raise
    except Exception as exc:raise ValueError("PDF cannot be opened: "+str(exc)) from exc
    if not 1<=pages<=MAX_PAGES:raise ValueError("Invalid/excessive PDF page count")
    return {"pdf_id":pdf_id,"title":doc["title"],"page_count":pages,
            "note":"Inspect the PDF pages and select a wiring diagram page; page numbers start at 1."}

def import_page(dbpath,pdf_store,assets_dir,pdf_id,profile_id,page_number,system,
                confirmed=False):
    if confirmed is not True:
        raise ValueError("Explicit PDF-to-vehicle applicability confirmation required")
    system=_system(system)
    try:page_num=int(page_number)
    except (ValueError,TypeError):raise ValueError("Invalid PDF page number")
    if page_num<1:raise ValueError("Page number starts at 1")
    with sqlite3.connect(dbpath) as db:
        profile=_profile(db,profile_id)
        doc=_source_pdf(db,pdf_id)
        tag=db.execute("SELECT profile_id FROM pdf_vehicle_v042 WHERE pdf_id=?",
                       (pdf_id,)).fetchone()
        if tag is None or tag[0]!=profile_id:
            raise ValueError("PDF must be assigned to the exact selected vehicle first")
        existing=db.execute("""SELECT d.id,d.title,d.image_file,d.width,d.height
                    FROM pdf_page_diagrams_v042 p JOIN viewer_diagrams d ON d.id=p.diagram_id
                    WHERE p.pdf_id=? AND p.page_number=?""",(pdf_id,page_num)).fetchone()
        if existing:return {"id":existing[0],"title":existing[1],
                            "image_file":existing[2],"width":existing[3],
                            "height":existing[4],"cache_hit":True}
    _,path=_pdf_path(dbpath,pdf_store,pdf_id)
    try:import fitz
    except ImportError as exc:
        raise RuntimeError("PDF rendering requires PyMuPDF. Install: py -m pip install pymupdf") from exc
    try:
        with fitz.open(str(path)) as pdf:
            if pdf.needs_pass:raise ValueError("Password-protected PDF not supported")
            if not 1<=page_num<=min(pdf.page_count,MAX_PAGES):
                raise ValueError("Requested page is outside allowed PDF page range")
            page=pdf.load_page(page_num-1)
            rect=page.rect
            if rect.width<=0 or rect.height<=0:raise ValueError("Invalid PDF page size")
            # At most 4000 pixels per edge and 12 MP total, regardless of DPI.
            scale=min(2.0,MAX_EDGE/rect.width,MAX_EDGE/rect.height,
                      (MAX_PIXELS/(rect.width*rect.height))**0.5)
            if scale<=0:raise ValueError("Invalid render scale")
            pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False,colorspace=fitz.csRGB)
            if pix.width*pix.height>MAX_PIXELS or pix.width>MAX_EDGE or pix.height>MAX_EDGE:
                raise ValueError("Rendered page exceeds safe dimensions")
            raw=pix.tobytes("png")
            width,height=pix.width,pix.height
    except ValueError:raise
    except Exception as exc:raise ValueError("PDF page rendering failed: "+str(exc)) from exc
    ident="pdf_"+doc["sha256"][:20]+"_p"+str(page_num).zfill(4)
    filename=ident+".png"
    folder=Path(assets_dir);folder.mkdir(parents=True,exist_ok=True)
    target=folder/filename
    temp=folder/(uuid.uuid4().hex+".tmp")
    wrote=False
    try:
        if not target.exists():
            temp.write_bytes(raw);temp.replace(target);wrote=True
        with sqlite3.connect(dbpath) as db:
            db.execute("BEGIN IMMEDIATE")
            # Recheck assignment under lock to avoid an accidental cross-vehicle link.
            tag=db.execute("SELECT profile_id FROM pdf_vehicle_v042 WHERE pdf_id=?",
                           (pdf_id,)).fetchone()
            if not tag or tag[0]!=profile_id:raise ValueError("PDF association changed")
            title=f"{profile['brand_name']} {profile['model_name']} {profile['year']} — {SYSTEMS[system]} (PDF p.{page_num})"
            db.execute("""INSERT OR IGNORE INTO viewer_diagrams
               (id,title,image_file,width,height,source_url,vehicle,verification)
               VALUES(?,?,?,?,?,?,?,?)""",
               (ident,title,filename,width,height,
                "pdf_library_v041:"+pdf_id+"#page="+str(page_num),
                profile["brand_name"]+" "+profile["model_name"]+" "+str(profile["year"]),
                "user_declared_applicability_unverified_electrical"))
            db.execute("""INSERT OR IGNORE INTO pdf_page_diagrams_v042
               (diagram_id,pdf_id,page_number,system,profile_id)
               VALUES(?,?,?,?,?)""",(ident,pdf_id,page_num,system,profile_id))
            db.execute("""INSERT OR IGNORE INTO diagram_vehicle_v0400(diagram_id,profile_id)
               VALUES(?,?)""",(ident,profile_id))
            db.execute("""INSERT INTO diagram_system_v042(diagram_id,system)
               VALUES(?,?) ON CONFLICT(diagram_id) DO UPDATE SET system=excluded.system""",
               (ident,system))
            db.commit()
        return {"id":ident,"title":title,"image_file":filename,
                "width":width,"height":height,"cache_hit":False,
                "verification":"user_declared_applicability_unverified_electrical"}
    except Exception:
        if wrote:target.unlink(missing_ok=True)
        raise
    finally:temp.unlink(missing_ok=True)

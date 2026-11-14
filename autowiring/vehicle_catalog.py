"""Offline, extensible vehicle catalog for AutoWiring.

Brand -> vehicle type (body style) -> vehicle name/model -> variant -> year.
Seed models are BROWSE EXAMPLES, not market-year/trim/engine compatibility data,
not an exhaustive authoritative database. A custom brand/model can be added.
"""
import re
import sqlite3
import uuid

SCHEMA="""
CREATE TABLE IF NOT EXISTS vehicle_brands_v0400(
 id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,
 origin TEXT NOT NULL DEFAULT 'local_example_catalog'
);
CREATE TABLE IF NOT EXISTS vehicle_models_v0400(
 id TEXT PRIMARY KEY,brand_id TEXT NOT NULL,
 name TEXT NOT NULL COLLATE NOCASE,body_type TEXT NOT NULL,
 origin TEXT NOT NULL DEFAULT 'local_example_catalog',
 UNIQUE(brand_id,name),FOREIGN KEY(brand_id) REFERENCES vehicle_brands_v0400(id)
);
CREATE TABLE IF NOT EXISTS vehicle_profiles_v0400(
 id TEXT PRIMARY KEY,brand_id TEXT NOT NULL,model_id TEXT NOT NULL,
 year INTEGER NOT NULL,variant TEXT NOT NULL DEFAULT '',
 powertrain TEXT NOT NULL DEFAULT 'unknown',notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS diagram_vehicle_v0400(
 diagram_id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(diagram_id) REFERENCES viewer_diagrams(id),
 FOREIGN KEY(profile_id) REFERENCES vehicle_profiles_v0400(id)
);
CREATE INDEX IF NOT EXISTS idx_vehicle_models_brand_v0400 ON vehicle_models_v0400(brand_id);
CREATE INDEX IF NOT EXISTS idx_diagram_vehicle_profile_v0400 ON diagram_vehicle_v0400(profile_id);
"""
TYPES=("MPV","SUV","Sedan","Hatchback","City Car","Pickup","Van","Crossover",
       "Commercial","Coupe","Wagon","Off-road","Other")
POWERTRAINS=("unknown","gasoline","diesel","hybrid","plug_in_hybrid","electric")
# No variant/year compatibility claims. This is a compact, editable Indonesia-
# oriented browsing starter list; real manuals must be vehicle-variant specific.
SEED={
 "Toyota":[("Avanza","MPV"),("Veloz","MPV"),("Kijang Innova","MPV"),
    ("Innova Zenix","MPV"),("Calya","MPV"),("Rush","SUV"),("Fortuner","SUV"),
    ("Yaris","Hatchback"),("Agya","City Car"),("Raize","SUV"),
    ("Corolla Altis","Sedan"),("Hilux","Pickup"),("Hiace","Van"),
    ("bZ4X","SUV"),("Camry","Sedan")],
 "Daihatsu":[("Xenia","MPV"),("Sigra","MPV"),("Terios","SUV"),
    ("Ayla","City Car"),("Rocky","SUV"),("Gran Max","Commercial"),
    ("Luxio","Van"),("Sirion","Hatchback")],
 "Honda":[("Brio","City Car"),("Jazz","Hatchback"),("Civic","Sedan"),
    ("City","Sedan"),("Accord","Sedan"),("HR-V","SUV"),("CR-V","SUV"),
    ("BR-V","SUV"),("Mobilio","MPV"),("WR-V","SUV"),("Freed","MPV")],
 "Suzuki":[("Swift","Hatchback"),("SX4","Crossover"),("XL7","SUV"),
    ("Ertiga","MPV"),("Baleno","Hatchback"),("Ignis","City Car"),
    ("Jimny","Off-road"),("Grand Vitara","SUV"),("APV","Van"),
    ("Carry","Pickup"),("S-Presso","City Car"),("Karimun Wagon R","City Car")],
 "Mitsubishi":[("Xpander","MPV"),("Xpander Cross","Crossover"),
    ("Pajero Sport","SUV"),("Triton","Pickup"),("L300","Pickup"),
    ("Outlander Sport","SUV"),("Xforce","SUV"),("Mirage","Hatchback")],
 "Nissan":[("Grand Livina","MPV"),("Livina","MPV"),("Serena","MPV"),
    ("X-Trail","SUV"),("Juke","Crossover"),("March","Hatchback"),
    ("Navara","Pickup"),("Kicks","SUV"),("Terra","SUV")],
 "Wuling":[("Air ev","City Car"),("BinguoEV","Hatchback"),
    ("Cloud EV","Hatchback"),("Alvez","SUV"),("Almaz","SUV"),
    ("Confero","MPV"),("Cortez","MPV"),("Formo Max","Pickup"),
    ("Formo","Van")],
 "Hyundai":[("Stargazer","MPV"),("Creta","SUV"),("Palisade","SUV"),
    ("Santa Fe","SUV"),("Tucson","SUV"),("Ioniq 5","Crossover"),
    ("Ioniq 6","Sedan"),("Kona Electric","SUV"),("i20","Hatchback")],
 "Kia":[("Sonet","SUV"),("Seltos","SUV"),("Carens","MPV"),
    ("Carnival","MPV"),("Picanto","City Car"),("Rio","Hatchback"),
    ("EV6","Crossover"),("EV9","SUV")],
 "Mazda":[("Mazda2","Hatchback"),("Mazda3","Sedan"),
    ("CX-3","SUV"),("CX-5","SUV"),("CX-8","SUV"),("CX-9","SUV"),
    ("CX-30","Crossover"),("MX-5","Coupe")],
 "Ford":[("Ranger","Pickup"),("Everest","SUV"),("Fiesta","Hatchback"),
    ("Focus","Hatchback"),("EcoSport","SUV"),("Escape","SUV")],
 "Chevrolet":[("Captiva","SUV"),("Spin","MPV"),("Aveo","Hatchback"),
    ("Trax","SUV"),("Trailblazer","SUV"),("Colorado","Pickup")],
 "Isuzu":[("D-Max","Pickup"),("MU-X","SUV"),("Traga","Pickup"),
    ("Panther","MPV"),("Elf","Commercial")],
 "BMW":[("3 Series","Sedan"),("5 Series","Sedan"),("7 Series","Sedan"),
    ("X1","SUV"),("X3","SUV"),("X5","SUV"),("iX","SUV"),
    ("i4","Sedan"),("Z4","Coupe")],
 "Mercedes-Benz":[("A-Class","Hatchback"),("C-Class","Sedan"),
    ("E-Class","Sedan"),("S-Class","Sedan"),("GLA","SUV"),
    ("GLC","SUV"),("GLE","SUV"),("EQE","Sedan"),("V-Class","Van")],
 "Volkswagen":[("Polo","Hatchback"),("Golf","Hatchback"),
    ("Tiguan","SUV"),("Touran","MPV"),("Caravelle","Van")],
 "Subaru":[("Forester","SUV"),("XV","Crossover"),("Crosstrek","Crossover"),
    ("Outback","Wagon"),("WRX","Sedan"),("BRZ","Coupe")],
 "Peugeot":[("206","Hatchback"),("208","Hatchback"),
    ("3008","SUV"),("5008","SUV")],
 "BYD":[("Dolphin","Hatchback"),("Atto 3","SUV"),("Seal","Sedan"),
    ("M6","MPV"),("Sealion 7","SUV")],
 "Chery":[("Omoda 5","SUV"),("Omoda E5","SUV"),
    ("Tiggo 7","SUV"),("Tiggo 8","SUV"),("Tiggo 5X","SUV")],
 "MG":[("MG 4 EV","Hatchback"),("ZS","SUV"),
    ("HS","SUV"),("MG 5 GT","Sedan")],
}
def _slug(text):
    return re.sub(r'[^a-z0-9]+','_',text.lower()).strip('_')

def seed(db):
    db.executescript(SCHEMA)
    for brand,models in SEED.items():
        brand_id=_slug(brand)
        db.execute("INSERT OR IGNORE INTO vehicle_brands_v0400(id,name) VALUES(?,?)",
                   (brand_id,brand))
        for model,body in models:
            db.execute("""INSERT OR IGNORE INTO vehicle_models_v0400
                    (id,brand_id,name,body_type) VALUES(?,?,?,?)""",
                (brand_id+":"+_slug(model),brand_id,model,body))
    db.commit()

def catalog(dbpath):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        seed(db)
        return {
            "brands":[dict(r) for r in db.execute(
                "SELECT * FROM vehicle_brands_v0400 ORDER BY name")],
            "models":[dict(r) for r in db.execute(
                "SELECT * FROM vehicle_models_v0400 ORDER BY brand_id,name")],
            "vehicle_types":list(TYPES),
            "powertrains":list(POWERTRAINS),
            "origin_notice":"Illustrative and extensible browse examples; NOT an exhaustive market, engine, variant or year compatibility catalog."
        }

def _name(text,field,limit=90):
    if not isinstance(text,str):raise ValueError(field+" is required")
    s=" ".join(text.strip().split())
    if not 1<=len(s)<=limit or any(ord(c)<32 for c in s):
        raise ValueError("Invalid "+field)
    return s

def add_model(dbpath,data):
    brand=_name(data.get("brand_name"),"brand_name")
    model=_name(data.get("model_name"),"model_name")
    body=data.get("body_type")
    if body not in TYPES:raise ValueError("Unknown body type")
    with sqlite3.connect(dbpath) as db:
        seed(db)
        old=db.execute(
            "SELECT id FROM vehicle_brands_v0400 WHERE name=? COLLATE NOCASE",(brand,)).fetchone()
        if old:brand_id=old[0]
        else:
            brand_id="custom_"+uuid.uuid4().hex[:16]
            db.execute("""INSERT INTO vehicle_brands_v0400(id,name,origin)
                    VALUES(?,?,'user_added')""",(brand_id,brand))
        matched=db.execute("""SELECT id FROM vehicle_models_v0400
                    WHERE brand_id=? AND name=? COLLATE NOCASE""",(brand_id,model)).fetchone()
        if matched:mid=matched[0]
        else:
            mid="custom_"+uuid.uuid4().hex[:16]
            db.execute("""INSERT INTO vehicle_models_v0400
                (id,brand_id,name,body_type,origin)
                VALUES(?,?,?,?,'user_added')""",(mid,brand_id,model,body))
        db.commit()
        return {"brand_id":brand_id,"model_id":mid,"brand_name":brand,
                "model_name":model,"body_type":body}

def save_profile(dbpath,data):
    brand_id=data.get("brand_id")
    model_id=data.get("model_id")
    try:year=int(data.get("year"))
    except (ValueError,TypeError):raise ValueError("Year is required")
    if not 1950<=year<=2035:raise ValueError("Year must be 1950–2035")
    variant=" ".join(str(data.get("variant") or "").split())
    notes=" ".join(str(data.get("notes") or "").split())
    if len(variant)>100 or len(notes)>300:raise ValueError("Variant/notes are too long")
    powertrain=data.get("powertrain") or "unknown"
    if powertrain not in POWERTRAINS:raise ValueError("Invalid powertrain")
    with sqlite3.connect(dbpath) as db:
        seed(db)
        row=db.execute("""SELECT b.name,m.name,m.body_type FROM vehicle_models_v0400 m
             JOIN vehicle_brands_v0400 b ON b.id=m.brand_id
             WHERE b.id=? AND m.id=? AND m.brand_id=?""",
             (brand_id,model_id,brand_id)).fetchone()
        if not row:raise ValueError("Selected vehicle model does not belong to brand")
        profile_id=uuid.uuid4().hex
        db.execute("""INSERT INTO vehicle_profiles_v0400
            (id,brand_id,model_id,year,variant,powertrain,notes)
            VALUES(?,?,?,?,?,?,?)""",
            (profile_id,brand_id,model_id,year,variant,powertrain,notes))
        db.commit()
    return {"id":profile_id,"brand_id":brand_id,"model_id":model_id,
            "brand_name":row[0],"model_name":row[1],"body_type":row[2],
            "year":year,"variant":variant,"powertrain":powertrain,
            "note":"Selected metadata only, not verified wiring or variant compatibility"}

def profiles(dbpath):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row;seed(db)
        return [dict(r) for r in db.execute("""SELECT p.*,
           b.name AS brand_name,m.name AS model_name,m.body_type
           FROM vehicle_profiles_v0400 p
           JOIN vehicle_brands_v0400 b ON b.id=p.brand_id
           JOIN vehicle_models_v0400 m ON m.id=p.model_id
           ORDER BY p.created_at DESC,p.rowid DESC""")]

def bind(dbpath,diagram_id,profile_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM viewer_diagrams WHERE id=?",(diagram_id,)).fetchone():
            raise ValueError("Diagram not found")
        if not db.execute("SELECT 1 FROM vehicle_profiles_v0400 WHERE id=?",(profile_id,)).fetchone():
            raise ValueError("Vehicle profile not found")
        db.execute("""INSERT INTO diagram_vehicle_v0400(diagram_id,profile_id)
           VALUES(?,?)
           ON CONFLICT(diagram_id) DO UPDATE SET
             profile_id=excluded.profile_id,created_at=CURRENT_TIMESTAMP""",
            (diagram_id,profile_id))
        db.commit()
    return binding(dbpath,diagram_id)

def binding(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("""SELECT link.diagram_id,p.*,b.name AS brand_name,
             m.name AS model_name,m.body_type
             FROM diagram_vehicle_v0400 link
             JOIN vehicle_profiles_v0400 p ON p.id=link.profile_id
             JOIN vehicle_models_v0400 m ON m.id=p.model_id
             JOIN vehicle_brands_v0400 b ON b.id=p.brand_id
             WHERE link.diagram_id=?""",(diagram_id,)).fetchone()
        return dict(row) if row else None

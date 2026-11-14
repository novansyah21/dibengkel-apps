"""Rules-based electrical triage assistant (beta), not an automatic fault verdict.

Accepts vehicle metadata, user-observed symptoms and 12V test data.
No image-derived electrical connectivity is assumed; hypotheses are
conditional, measurable and always presented with counterchecks.
High-voltage and SRS systems are blocked from DIY probing guidance.
"""
import hashlib
import json
import math
import sqlite3
import uuid

SCHEMA="""
CREATE TABLE IF NOT EXISTS diagnosis_cases_v0400(
 id TEXT PRIMARY KEY,
 diagram_id TEXT NOT NULL,
 profile_id TEXT NOT NULL DEFAULT '',
 input_fingerprint TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 input_json TEXT NOT NULL,
 result_json TEXT NOT NULL,
 UNIQUE(diagram_id,profile_id,input_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_cases_diagram_v0400 ON diagnosis_cases_v0400(diagram_id,created_at);
"""
SYMPTOMS={
 "no_crank":"Starter tidak berputar",
 "cranks_no_start":"Starter berputar, mesin tidak hidup",
 "lights_dead":"Lampu tidak menyala",
 "accessory_dead":"Aksesori tidak bekerja",
 "fuse_blows":"Sekering sering putus",
 "intermittent":"Gangguan listrik intermiten",
 "charging_issue":"Pengisian aki 12V bermasalah",
 "battery_drain":"Aki 12V cepat habis",
 "other":"Gangguan listrik lain",
}
SYSTEMS={
 "starting":"Starter/ignition 12V",
 "lighting":"Lampu",
 "body":"Body control / aksesori",
 "charging_12v":"Pengisian baterai 12V",
 "general_12v":"Kelistrikan 12V umum",
 "abs":"ABS/braking electronics",
 "srs":"Airbag/SRS (restricted)",
 "high_voltage":"EV/hybrid high-voltage (restricted)",
}
FUSE_TESTS=("unknown","intact","open","not_tested")
READINGS=("battery_voltage_off_v","fuse_input_v","fuse_output_v",
          "load_feed_v","ground_voltage_drop_v")
SAFE_STEPS={
 "no_crank":[
  "Catat apakah dashboard meredup saat tombol start ditekan; jangan memaksa starter berulang.",
  "Periksa kondisi terminal aki 12V secara visual saat kendaraan aman dan tidak dioperasikan.",
  "Bandingkan tegangan aki 12V dalam kondisi engine-off dengan spesifikasi servis kendaraan."
 ],
 "cranks_no_start":[
  "Periksa DTC menggunakan alat diagnosis yang sesuai tanpa menghapus DTC terlebih dahulu.",
  "Jangan menebak sekring/pin ECU dari OCR gambar; gunakan manual servis sesuai mesin dan tahun.",
 ],
 "lights_dead":[
  "Identifikasi apakah semua lampu atau hanya satu sisi yang tidak berfungsi.",
  "Periksa sekering lampu yang benar berdasarkan manual kendaraan (lokasi dan rating harus cocok).",
 ],
 "accessory_dead":[
  "Pastikan masalah hanya satu aksesori atau beberapa aksesori dengan suplai bersama.",
  "Gunakan manual dan label sekering yang tervalidasi untuk menentukan jalur inspeksi.",
 ],
 "fuse_blows":[
  "Jangan memasang sekering ber-rating lebih besar, menjumper sekering, atau terus mengganti sekering.",
  "Minta teknisi memeriksa penyebab arus lebih atau kemungkinan short pada rangkaian terkait.",
 ],
 "intermittent":[
  "Catat kondisi munculnya gangguan (hujan, panas, getaran, beban aktif) untuk reproduksi aman.",
  "Inspeksi konektor dan harness secara visual pada kendaraan dalam keadaan aman.",
 ],
 "charging_issue":[
  "Pastikan sistem yang dibahas adalah 12V; sistem traction high-voltage harus ditangani teknisi bersertifikat.",
  "Catat tegangan aki dalam kondisi mesin mati, dan bandingkan dengan data servis yang benar.",
 ],
 "battery_drain":[
  "Catat kapan aki melemah dan aksesori yang tetap aktif saat kendaraan dimatikan.",
  "Jangan melepas/menghubungkan pengukur arus seri tanpa prosedur servis yang benar.",
 ],
 "other":[
  "Jelaskan gejala yang berulang dan waktu kejadiannya sebelum menentukan pengukuran.",
 ],
}
def _number(data,key,upper=60):
    val=data.get(key)
    if val in (None,""):return None
    try:out=float(val)
    except (ValueError,TypeError):raise ValueError("Invalid voltage value for "+key)
    if not math.isfinite(out) or not 0<=out<=upper:
        raise ValueError("Out of safe allowed range for "+key)
    return round(out,3)

def validate(payload):
    if not isinstance(payload,dict):raise ValueError("Invalid diagnosis input")
    symptom=payload.get("symptom")
    system=payload.get("system")
    if symptom not in SYMPTOMS:raise ValueError("Select a valid symptom")
    if system not in SYSTEMS:raise ValueError("Select a valid electrical system")
    raw=payload.get("measurements") or {}
    if not isinstance(raw,dict):raise ValueError("Measurements must be an object")
    measurements={k:_number(raw,k,20 if k=="ground_voltage_drop_v" else 60)
                  for k in READINGS}
    continuity=raw.get("fuse_continuity") or "unknown"
    if continuity not in FUSE_TESTS:raise ValueError("Invalid fuse continuity")
    measurements["fuse_continuity"]=continuity
    measurements["load_active"]=raw.get("load_active") is True
    desc=" ".join(str(payload.get("notes") or "").split())
    if len(desc)>800:raise ValueError("Notes must be <=800 characters")
    return {"symptom":symptom,"system":system,
            "measurements":measurements,"notes":desc}

def _add(findings,code,title,detail,based_on,checks,priority="review"):
    findings.append({
        "code":code,"title":title,"interpretation":detail,
        "based_on_fields":based_on,
        "priority":priority,
        "evidence_level":"user_reported_test_result_not_independently_verified",
        "suggested_checks":checks,
        "diagnosis_confirmed":False,
        "component_location_verified":False,
    })

def evaluate(payload,vehicle=None,diagram_evidence=None):
    data=validate(payload)
    m=data["measurements"]
    restricted=data["system"] in ("srs","high_voltage")
    if restricted:
        return {
            "status":"safety_restricted",
            "title":"Inspeksi profesional diperlukan — tidak ada diagnosis otomatis",
            "system":data["system"],"symptom":data["symptom"],
            "vehicle":vehicle,"findings":[],
            "suggested_next_checks":[
                "Hentikan pemeriksaan rangkaian tegangan tinggi/airbag dengan alat atau prosedur umum.",
                "Gunakan teknisi tersertifikasi, alat pelindung dan manual prosedur servis yang sesuai.",
                "Jangan menyentuh konektor oranye EV, rangkaian airbag, pretensioner, atau melakukan continuity probing pada SRS."
            ],
            "missing_evidence":["Verified vehicle-specific service diagram and qualified technician"],
            "diagram_evidence":diagram_evidence or {},
            "certainty":"none","automatic_diagnosis_verified":False,
            "electrical_continuity_verified":False,
            "disclaimer":"SRS/high-voltage troubleshooting is outside automated or DIY diagnosis scope."
        }
    findings=[];checks=list(SAFE_STEPS[data["symptom"]]);missing=[]
    battery=m["battery_voltage_off_v"]
    inp=m["fuse_input_v"];out=m["fuse_output_v"]
    load=m["load_feed_v"];drop=m["ground_voltage_drop_v"]
    continuity=m["fuse_continuity"]
    # Apply only when measurements are directly supplied, never inferred from
    # diagram geometry or generic vehicle powertrain labels.
    if battery is not None:
        if battery<11.8:
            _add(findings,"12v_battery_low",
                 "Tegangan baterai 12V saat mesin mati rendah",
                 "Baterai dapat lemah atau terdischarge; angka ini tidak menentukan akar penyebab.",
                 ["battery_voltage_off_v"],
                 ["Validasi kondisi istirahat dan standar baterai kendaraan.",
                  "Periksa kondisi pengisian dan kemungkinan parasitic drain oleh teknisi."],
                 "high")
        elif battery<12.3:
            _add(findings,"12v_battery_marginal",
                 "Tegangan baterai 12V saat mesin mati perlu diverifikasi",
                 "Bisa mencerminkan state of charge/umur baterai; tidak otomatis berarti rusak.",
                 ["battery_voltage_off_v"],[
                  "Ulangi pengukuran sesuai kondisi istirahat dan spesifikasi kendaraan."],
                 "review")
    if continuity=="open":
        _add(findings,"fuse_open_observed",
             "Sekering dilaporkan putus pada pengujian",
             "Sekering terbuka adalah temuan, bukan penjelasan penyebab arus lebih.",
             ["fuse_continuity"],[
              "Konfirmasi nomor serta rating fuse dari manual kendaraan.",
              "Jangan bypass atau menaikkan rating fuse; cek arus lebih/short oleh teknisi."],
             "high")
    if inp is not None and out is not None:
        if inp>=10.0 and out<=2.0:
            _add(findings,"fuse_voltage_drop",
                 "Perbedaan tegangan signifikan di kedua sisi sekering",
                 "Kandidat sekering terbuka atau kontak holder yang buruk; pastikan kondisi beban/test sama.",
                 ["fuse_input_v","fuse_output_v"],[
                  "Cocokkan posisi sekering dan kondisi kendaraan dengan service manual.",
                  "Konfirmasi pengukuran dan kondisi fisik holder oleh teknisi."],
                 "high")
        elif inp<=2.0 and out<=2.0 and battery is not None and battery>=11.8:
            _add(findings,"upstream_supply_candidate",
                 "Suplai masuk sekering belum terlihat saat pengukuran",
                 "Kemungkinan feed upstream, relay, kondisi ignition atau prosedur pengukuran; tidak menunjuk komponen tertentu.",
                 ["battery_voltage_off_v","fuse_input_v","fuse_output_v"],[
                  "Periksa apakah rangkaian seharusnya aktif pada posisi ignition saat diuji.",
                  "Ikuti urutan suplai pada wiring diagram versi kendaraan yang sudah diverifikasi."],
                 "review")
    if out is not None and load is not None and out>=10 and load<=2:
        _add(findings,"load_supply_discrepancy",
             "Tegangan tersedia di output fuse tetapi tidak pada titik beban yang dilaporkan",
             "Perlu cek sambungan/relay atau akurasi titik ukur; jalur antara titik belum dibuktikan.",
             ["fuse_output_v","load_feed_v"],[
              "Verifikasi dulu bahwa kedua titik ukur berada di satu sirkuit yang sama memakai service manual.",
              "Pemeriksaan harness/konektor selanjutnya dilakukan oleh teknisi."],
             "review")
    if drop is not None and m["load_active"] and drop>0.5:
        _add(findings,"ground_voltage_drop_high",
             "Voltage drop ground saat beban aktif relatif tinggi",
             "Dapat mengindikasikan resistansi sambungan ground; batas tergantung spesifikasi dan beban.",
             ["ground_voltage_drop_v","load_active"],[
              "Bandingkan metode pengukuran dan batas drop pada manual kendaraan.",
              "Inspeksi sambungan ground terkait oleh teknisi."],"review")
    elif drop is not None and not m["load_active"]:
        checks.append("Ground drop tanpa beban aktif belum dapat diinterpretasikan; catat beban saat pengukuran.")
    if data["symptom"]=="fuse_blows" and continuity!="open":
        checks.append("Jika sekering sering putus, dokumentasikan fuse dan kapan putus; jangan menaikkan rating.")
    if not any(m.get(k) is not None for k in READINGS) and continuity in ("unknown","not_tested"):
        missing.extend(["Hasil pemeriksaan aki 12V (jika relevan dan aman)",
                        "Nomor fuse dan identifikasi sistem sesuai service manual",
                        "DTC atau bukti inspeksi teknisi bila tersedia"])
    if diagram_evidence and diagram_evidence.get("manual_circuit_links",0):
        checks.append(
            "Ada sambungan manual pada diagram, tetapi status konektivitas listriknya belum diverifikasi secara independen.")
    if diagram_evidence and not diagram_evidence.get("diagram_found",False):
        missing.append("Diagram servis kendaraan yang cocok dengan tahun, mesin, varian, dan sistem")
    if not findings:
        status="insufficient_evidence"
        title="Belum ada data pengukuran cukup untuk menentukan titik gangguan"
    else:
        status="conditional_hypotheses"
        title="Hipotesis awal berdasarkan data uji yang dimasukkan"
    return {
        "status":status,"title":title,"system":data["system"],
        "symptom":data["symptom"],"vehicle":vehicle,
        "findings":findings,"suggested_next_checks":checks,
        "missing_evidence":missing,
        "diagram_evidence":diagram_evidence or {},
        "certainty":"not_calibrated_no_probability",
        "automatic_diagnosis_verified":False,
        "electrical_continuity_verified":False,
        "disclaimer":"Bukan vonis kerusakan. Tidak ada penetapan lokasi komponen tanpa service manual dan konfirmasi teknisi; jangan melakukan pengujian berbahaya pada kendaraan."
    }

def _context(db,diagram_id):
    row=db.execute("SELECT 1 FROM viewer_diagrams WHERE id=?",(diagram_id,)).fetchone()
    if not row:raise ValueError("Unknown diagram")
    paths=db.execute("SELECT count(*) FROM viewer_paths WHERE diagram_id=?",(diagram_id,)).fetchone()[0]
    links=db.execute("SELECT count(*) FROM viewer_circuit_links WHERE diagram_id=?",(diagram_id,)).fetchone()[0]
    return {
        "diagram_found":True,
        "manual_paths":paths,
        "manual_circuit_links":links,
        "connections_electrically_verified":0,
        "warning":"Manual and OCR/CV tracing can be wrong. No link is accepted as electrically verified."
    }

def run(dbpath,diagram_id,payload):
    data=validate(payload)
    from autowiring.vehicle_catalog import binding
    with sqlite3.connect(dbpath) as db:
        db.executescript(SCHEMA)
        evidence=_context(db,diagram_id)
    vehicle=binding(dbpath,diagram_id)
    result=evaluate(data,vehicle,evidence)
    fingerprint=hashlib.sha256(json.dumps(
        {"input":data,"binding":vehicle,"evidence":evidence},
        sort_keys=True,default=str).encode()).hexdigest()
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        existing=db.execute("""SELECT id FROM diagnosis_cases_v0400
          WHERE diagram_id=? AND profile_id=? AND input_fingerprint=?""",
          (diagram_id,vehicle["id"] if vehicle else "",fingerprint)).fetchone()
        if existing:case_id=existing["id"];cached=True
        else:
            case_id=uuid.uuid4().hex;cached=False
            db.execute("""INSERT INTO diagnosis_cases_v0400
             (id,diagram_id,profile_id,input_fingerprint,input_json,result_json)
             VALUES(?,?,?,?,?,?)""",
             (case_id,diagram_id,vehicle["id"] if vehicle else "",
              fingerprint,json.dumps(data,ensure_ascii=False),
              json.dumps(result,ensure_ascii=False)))
            db.commit()
    result["case_id"]=case_id
    result["cache_hit"]=cached
    return result

def history(dbpath,diagram_id):
    with sqlite3.connect(dbpath) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute("""SELECT id,diagram_id,profile_id,created_at,
          result_json FROM diagnosis_cases_v0400 WHERE diagram_id=?
          ORDER BY created_at DESC,rowid DESC LIMIT 20""",(diagram_id,)).fetchall()
        out=[]
        for item in rows:
            result=json.loads(item["result_json"])
            out.append({"id":item["id"],"created_at":item["created_at"],
                        "status":result["status"],"title":result["title"],
                        "findings_count":len(result["findings"]),
                        "electrical_continuity_verified":False})
        return out

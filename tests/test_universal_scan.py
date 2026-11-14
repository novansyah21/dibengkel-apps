"""v0.4.0 generic reader: hash caching and explicit non-electrical provenance."""
import hashlib
import io
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image

from viewer import setup
from autowiring import universal_scan

def make_image(path,bg="white"):
    im=Image.new("RGB",(230,330),bg);im.save(path,format="PNG")

class GenericImageScanTests(unittest.TestCase):
    def test_generic_scan_caches_image_and_never_joins_wires(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath=Path(folder)/"db.sqlite"
            image=Path(folder)/"unseen_car.png"
            with sqlite3.connect(dbpath) as db:setup(db)
            make_image(image)
            call_count=[0]
            def fake_extract(path,diagram_id,database,ocr=True,lines=True,max_candidates=450):
                call_count[0]+=1
                with sqlite3.connect(database) as db:
                    rid=uuid.uuid4().hex
                    sha=hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    db.execute("""INSERT INTO auto_runs_v032
                        (id,diagram_id,image_sha256,ocr_available,cv_available,ocr_count,line_count,notes)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (rid,diagram_id,sha,1,1,1,1,"synthetic OCR/CV"))
                    db.execute("""INSERT INTO auto_candidates_v032
                        (id,run_id,diagram_id,kind,label,x,y,w,h,confidence,source,verification)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex,rid,diagram_id,"ocr_fuse_label","15A",
                         .3,.2,.08,.03,.84,"test OCR","machine_candidate_unverified"))
                    db.commit()
                return {"run_id":rid,"diagram_id":diagram_id,
                        "ocr_available":True,"cv_available":True,
                        "candidates":1,"notes":[]}
            with patch.object(universal_scan,"auto_extract",side_effect=fake_extract):
                first=universal_scan.scan(dbpath,"junction_block",image)
                self.assertFalse(first["cache_hit"])
                self.assertEqual(first["summary"]["older_stages_rerun"],0)
                self.assertEqual(first["summary"]["candidate_count"],1)
                self.assertEqual(first["electrically_verified_connections"],0)
                self.assertEqual(first["candidates"][0]["label"],"15A")
                second=universal_scan.scan(dbpath,"junction_block",image)
                self.assertTrue(second["cache_hit"])
                self.assertEqual(call_count[0],1)
                previous=universal_scan.latest(dbpath,"junction_block")
                self.assertEqual(previous["candidates"][0]["label"],"15A")
                make_image(image,"gray")
                changed=universal_scan.scan(dbpath,"junction_block",image)
                self.assertFalse(changed["cache_hit"])
                self.assertEqual(call_count[0],2)
                with sqlite3.connect(dbpath) as db:
                    self.assertEqual(db.execute(
                        "SELECT count(*) FROM universal_scan_runs_v0400").fetchone()[0],2)
    def test_no_original_image_no_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath=Path(folder)/"d.db"
            with sqlite3.connect(dbpath) as db:setup(db)
            with self.assertRaisesRegex(ValueError,"not found"):
                universal_scan.scan(dbpath,"junction_block",Path(folder)/"none.png")

if __name__=="__main__":unittest.main()

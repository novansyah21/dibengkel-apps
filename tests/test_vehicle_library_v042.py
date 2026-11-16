"""v0.4.2: exact vehicle matching, metadata provenance and PDF page import."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from viewer import setup
from autowiring.vehicle_catalog import catalog,save_profile,bind
from autowiring.pdf_library import add_local_pdf
from autowiring.vehicle_library import (search,attach_pdf,attach_diagram,
                                        pdf_info,import_page)

class MockPix:
    width=1000;height=1500
    def tobytes(self,typ):
        assert typ=="png"
        return b"\x89PNG\r\n\x1a\nFAKE_IMAGE_FOR_UNIT_TEST"
class MockPage:
    rect=types.SimpleNamespace(width=500,height=750)
    def get_pixmap(self,**kw):return MockPix()
class MockDocument:
    page_count=3
    needs_pass=False
    def load_page(self,index):
        assert 0<=index<3
        return MockPage()
    def __enter__(self):return self
    def __exit__(self,*args):pass

def fake_fitz():
    return types.SimpleNamespace(open=lambda p:MockDocument(),
        Matrix=lambda x,y:(x,y),csRGB="RGB")

class VehicleFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"autowiring.db"
        self.assets=self.root/"assets"
        self.store=self.root/"pdf_library"
        with sqlite3.connect(self.db) as db:setup(db)
        entries=catalog(self.db)
        self.suzuki=next(b["id"] for b in entries["brands"] if b["name"]=="Suzuki")
        self.swift=next(m["id"] for m in entries["models"] if m["name"]=="Swift"
            and m["brand_id"]==self.suzuki)
        self.sx4=next(m["id"] for m in entries["models"] if m["name"]=="SX4"
            and m["brand_id"]==self.suzuki)
        self.profile=save_profile(self.db,dict(brand_id=self.suzuki,model_id=self.swift,
            year=2007,variant="GL AT 1.4",powertrain="gasoline"))
        self.query={"brand_id":self.suzuki,"model_id":self.swift,"year":"2007",
                    "variant":"GL AT 1.4","powertrain":"gasoline"}
        self.file=self.root/"lawful.pdf"
        self.file.write_bytes(b"%PDF-1.4\nminimal fixture; real render mocked\n%%EOF")
        self.doc=add_local_pdf(self.db,self.store,self.file,"My workshop manual",
             "Suzuki Swift 2007","authorized personal reference")
    def tearDown(self):self.tmp.cleanup()
    def test_no_fallback_and_no_builtin_samples(self):
        self.assertEqual(search(self.db,self.query)["diagrams"],[])
        self.assertEqual(search(self.db,self.query)["pdfs"],[])
        # v0.4.1 allowed binding an unrelated sample to any vehicle.
        # v0.4.2 explicitly excludes it from matching search.
        bind(self.db,"junction_block",self.profile["id"])
        self.assertEqual(search(self.db,self.query)["diagrams"],[])
        for change in ({"year":"2008"},{"variant":"GL MT 1.4"},
                       {"model_id":self.sx4},{"powertrain":"diesel"}):
            q={**self.query,**change}
            self.assertEqual(search(self.db,q)["diagrams"],[])
            self.assertEqual(search(self.db,q)["pdfs"],[])
        self.assertFalse(search(self.db,{"brand_id":"","model_id":"","year":""})["has_vehicle"])
    def test_authorized_pdf_tagging_is_explicit_and_exact(self):
        with self.assertRaisesRegex(ValueError,"confirm"):
            attach_pdf(self.db,self.doc["id"],self.profile["id"],"starting")
        attach_pdf(self.db,self.doc["id"],self.profile["id"],"starting",True)
        found=search(self.db,self.query)
        self.assertEqual(len(found["pdfs"]),1)
        self.assertEqual(found["pdfs"][0]["applicability"],"user_declared_unverified")
        self.assertEqual(found["diagrams"],[])
        self.assertEqual(search(self.db,{**self.query,"year":2006})["pdfs"],[])
        another=save_profile(self.db,{**self.query,"year":2008})
        with self.assertRaisesRegex(ValueError,"already associated"):
            attach_pdf(self.db,self.doc["id"],another["id"],"starting",True)
    def test_manual_image_classification_excludes_seed(self):
        with sqlite3.connect(self.db) as db:
            db.execute("""INSERT INTO viewer_diagrams
              (id,title,image_file,width,height,vehicle)VALUES(?,?,?,?,?,?)""",
              ("upload_test","Starting image","upload_test.png",1000,1000,"User diagram"))
        with self.assertRaisesRegex(ValueError,"cannot be reclassified"):
            attach_diagram(self.db,"junction_block",self.profile["id"],"starting",True)
        with self.assertRaisesRegex(ValueError,"Confirm"):
            attach_diagram(self.db,"upload_test",self.profile["id"],"starting")
        attach_diagram(self.db,"upload_test",self.profile["id"],"starting",True)
        found=search(self.db,self.query)
        self.assertEqual(len(found["diagrams"]),1)
        self.assertEqual(found["diagrams"][0]["system"],"starting")
        self.assertEqual(search(self.db,{**self.query,"year":2008})["diagrams"],[])
    def test_pdf_page_count_and_render_cache(self):
        attach_pdf(self.db,self.doc["id"],self.profile["id"],"charging",True)
        with patch.dict(sys.modules,{"fitz":fake_fitz()}):
            details=pdf_info(self.db,self.store,self.doc["id"])
            self.assertEqual(details["page_count"],3)
            with self.assertRaisesRegex(ValueError,"outside allowed"):
                import_page(self.db,self.store,self.assets,self.doc["id"],
                            self.profile["id"],4,"charging",True)
            page=import_page(self.db,self.store,self.assets,self.doc["id"],
                             self.profile["id"],2,"charging",True)
            self.assertFalse(page["cache_hit"])
            self.assertTrue((self.assets/page["image_file"]).exists())
            again=import_page(self.db,self.store,self.assets,self.doc["id"],
                              self.profile["id"],2,"charging",True)
            self.assertEqual(page["id"],again["id"])
            self.assertTrue(again["cache_hit"])
        found=search(self.db,self.query)
        self.assertEqual(len(found["diagrams"]),1)
        self.assertEqual(found["diagrams"][0]["page_number"],2)
        self.assertIn("PDF p.2",found["diagrams"][0]["title"])
        self.assertEqual(found["diagrams"][0]["system"],"charging")
    def test_pdf_import_checks_link_and_checksum(self):
        with patch.dict(sys.modules,{"fitz":fake_fitz()}):
            with self.assertRaisesRegex(ValueError,"assigned"):
                import_page(self.db,self.store,self.assets,self.doc["id"],
                            self.profile["id"],1,"starting",True)
            attach_pdf(self.db,self.doc["id"],self.profile["id"],"starting",True)
            (self.store/self.doc["file_name"]).write_bytes(b"%PDF-hijacked content")
            with self.assertRaisesRegex(ValueError,"checksum"):
                pdf_info(self.db,self.store,self.doc["id"])
            with self.assertRaisesRegex(ValueError,"checksum"):
                import_page(self.db,self.store,self.assets,self.doc["id"],
                            self.profile["id"],1,"starting",True)

if __name__=="__main__":unittest.main()

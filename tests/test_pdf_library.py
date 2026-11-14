"""PDF source library regression: provenance, bounded discovery and no unauthorized fetch."""
import hashlib
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch,MagicMock

from viewer import setup
from autowiring import pdf_library as lib

class PdfLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"test.db"
        self.store=Path(self.tmp.name)/"pdf"
        with sqlite3.connect(self.db) as db:setup(db)
    def tearDown(self):self.tmp.cleanup()
    def test_prior_sources_catalog_without_any_download(self):
        entries=lib.sources(self.db)
        self.assertEqual({s["id"] for s in entries},
            {"charm","bmw_etm","bmw_wds","bmwteka","carmanualsonline"})
        self.assertTrue(all(x["license_status"]=="unknown" for x in entries))
        self.assertEqual(lib.documents(self.db),[])
    def test_import_requires_explicit_permission_before_network(self):
        with patch.object(lib,"_request",side_effect=AssertionError("network called")):
            with self.assertRaises(PermissionError):
                lib.import_pdf(self.db,self.store,"https://example.com/manual.pdf",
                               "Manual","Car","permission",permission_confirmed=False)
        self.assertEqual(lib.documents(self.db),[])
    def test_local_pdf_dedup_and_provenance(self):
        p=Path(self.tmp.name)/"manual.pdf"
        p.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF")
        a=lib.add_local_pdf(self.db,self.store,p,"Own manual","Suzuki SX4 2007",
                            "Licensed copy for private reference")
        b=lib.add_local_pdf(self.db,self.store,p,"Own manual","Suzuki SX4 2007",
                            "Licensed copy for private reference")
        self.assertEqual(a["sha256"],hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(len(lib.documents(self.db)),1)
        self.assertEqual((self.store/a["file_name"]).read_bytes(),p.read_bytes())
        self.assertTrue(a["source_url"].startswith("local_file:"))
    def test_rejects_wrong_content_and_large_files(self):
        p=Path(self.tmp.name)/"fake.pdf";p.write_bytes(b"<html>not a pdf</html>")
        with self.assertRaisesRegex(ValueError,"Not a PDF"):
            lib.add_local_pdf(self.db,self.store,p,"Fake","Suzuki","my copy")
        with self.assertRaises(ValueError):
            lib.add_local_pdf(self.db,self.store,p,"","Suzuki","my copy")
    def test_url_rejects_http_credentials_private_ips_and_bad_port(self):
        for url in ("http://example.com/x.pdf","https://127.0.0.1/x.pdf",
                    "https://localhost/x.pdf","https://user:pw@example.com/a.pdf",
                    "https://example.com:8080/a.pdf"):
            with self.assertRaises(ValueError):
                lib._validate_url(url)
    def test_discover_is_dry_run_same_domain_and_pdf_only(self):
        class Response:
            headers={"Content-Type":"text/html; charset=utf-8"}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'<a href="/a.pdf">PDF</a><a href="https://other.com/x.pdf">Other</a><a href="/x.html">HTML</a>'
        with patch.object(lib,"_validate_url",return_value=
                __import__('urllib.parse',fromlist=['urlparse']).urlparse("https://example.com/index")):
            with patch.object(lib,"_robots",return_value=True):
                with patch.object(lib,"_request",return_value=Response()) as fetch:
                    result=lib.discover("https://example.com/index")
        self.assertEqual(result["discovered_pdf_links"],["https://example.com/a.pdf"])
        self.assertEqual(result["downloaded"],0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(fetch.call_count,1)
    def test_robots_fail_closed(self):
        with patch.object(lib,"_validate_url",return_value=
                __import__('urllib.parse',fromlist=['urlparse']).urlparse("https://example.com/index")):
            with patch.object(lib,"_robots",return_value=False):
                with self.assertRaises(PermissionError):
                    lib.discover("https://example.com/index")
    def test_http_source_registry_no_private_pdf_path(self):
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM pdf_source_catalog_v041").fetchone()[0],5)

if __name__=="__main__":unittest.main()

"""MVP user-upload regression, with local HTTP smoke for serving loading.js."""
import base64
import io
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from PIL import Image

from autowiring.diagram_upload import upload
from viewer import setup

def image_bytes(size=(200,280),format="PNG"):
    im=Image.new("RGB",size,"white")
    buf=io.BytesIO();im.save(buf,format=format);return buf.getvalue()

class UploadTests(unittest.TestCase):
    def test_png_jpeg_import_and_registered_manual_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);db=path/"u.db";assets=path/"sample_assets"
            with sqlite3.connect(db) as con:setup(con)
            for fmt in ("PNG","JPEG"):
                raw=image_bytes(format=fmt)
                item=upload(db,assets,{
                    "title":"Other car fuse box","vehicle":"Vehicle B (source unverified)",
                    "image_base64":"data:image/"+("png" if fmt=="PNG" else "jpeg")+
                        ";base64,"+base64.b64encode(raw).decode()})
                self.assertEqual(item["verification"],"manual_visual_review_only")
                self.assertTrue(item["id"].startswith("upload_"))
                self.assertTrue((assets/item["image_file"]).is_file())
                with Image.open(assets/item["image_file"]) as image:
                    self.assertEqual(image.format,"PNG")
                    self.assertEqual(image.size,(200,280))
                with sqlite3.connect(db) as con:
                    meta=con.execute(
                        "SELECT source_url,verification FROM viewer_diagrams WHERE id=?",
                        (item["id"],)).fetchone()
                    self.assertEqual(meta[1],"manual_visual_review_only")
                    self.assertTrue(meta[0].startswith("local_upload_sha256:"))
    def test_rejects_malicious_or_oversized_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);db=path/"u.db"
            with sqlite3.connect(db) as con:setup(con)
            raw=base64.b64encode(image_bytes()).decode()
            for body in (
                {"title":"evil","image_base64":"data:text/html;base64,"+raw},
                {"title":"evil","image_base64":"%%%not base64"},
                {"title":"../name","image_base64":base64.b64encode(b"not image").decode()},
                {"title":"oversized","image_base64":base64.b64encode(
                    image_bytes(size=(6001,120))).decode()},
                {"title":"bad","image_base64":base64.b64encode(
                    image_bytes(size=(90,90))).decode()},
            ):
                with self.assertRaises(ValueError):
                    upload(db,path/"assets",body)
            self.assertEqual(list((path/"assets").glob("*.png")) if
                             (path/"assets").is_dir() else [],[])

    def test_http_loading_script_served_and_upload_image_safe(self):
        """Integration: v0.3.21 loading.js was previously returning 404."""
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"u.db"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            process=subprocess.Popen([sys.executable,"viewer.py","--port",str(port),
                                      "--db",str(db)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            filename=None
            try:
                url="http://127.0.0.1:"+str(port)
                for _ in range(70):
                    if process.poll() is not None:
                        self.fail("viewer server failed to start")
                    try:
                        with urlopen(url+"/loading.js",timeout=1) as response:
                            self.assertEqual(response.status,200)
                            self.assertIn(b"ActionProgress",response.read())
                        break
                    except Exception:
                        time.sleep(.1)
                else:self.fail("viewer did not become ready")
                raw=base64.b64encode(image_bytes()).decode()
                payload=json.dumps({"title":"Manual car diagram",
                      "vehicle":"Other model",
                      "image_base64":"data:image/png;base64,"+raw}).encode()
                request=Request(url+"/api/diagram-upload",payload,
                                headers={"Content-Type":"application/json"},
                                method="POST")
                with urlopen(request,timeout=8) as response:
                    self.assertEqual(response.status,201)
                    item=json.load(response)
                filename=item["image_file"]
                with urlopen(url+"/images/"+filename,timeout=5) as response:
                    self.assertEqual(response.status,200)
                    self.assertEqual(response.headers.get_content_type(),"image/png")
                    self.assertGreater(len(response.read()),100)
                annotation=json.dumps({"diagram_id":item["id"],
                    "kind":"connector","label":"Connector A",
                    "notes":"needs manual review",
                    "x":.55,"y":.45,"w":.03,"h":.04}).encode()
                req=Request(url+"/api/annotations",annotation,
                            headers={"Content-Type":"application/json"},method="POST")
                with urlopen(req,timeout=5) as response:
                    self.assertIn(response.status,(200,201))
                with urlopen(url+"/api/annotations?diagram="+item["id"],timeout=5) as response:
                    result=json.load(response)
                    self.assertEqual(result[0]["label"],"Connector A")
                try:urlopen(url+"/images/../viewer.py",timeout=5)
                except HTTPError as error:self.assertEqual(error.code,404)
                else:self.fail("Unregistered/local script path should be blocked")
            finally:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill()
                if filename:
                    # GitHub Actions test runs in a clean checkout: clean uploaded file.
                    Path("sample_assets",filename).unlink(missing_ok=True)

if __name__=="__main__":
    unittest.main()

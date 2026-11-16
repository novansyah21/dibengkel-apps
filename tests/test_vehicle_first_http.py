"""Vehicle-first API smoke: no wrong-car diagram fallback; explicit metadata tagging."""
import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request,urlopen

def get(url):
    with urlopen(url,timeout=10) as response:return json.load(response)
def post(url,data):
    req=Request(url,data=json.dumps(data).encode(),method="POST",
                headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=10) as response:return json.load(response)

class VehicleFirstHttpTests(unittest.TestCase):
    def test_no_cross_vehicle_fallback_and_explicit_classification(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"app.sqlite"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port=sock.getsockname()[1]
            proc=subprocess.Popen([sys.executable,"viewer.py","--port",str(port),
                                   "--db",str(db)],
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                base=f"http://127.0.0.1:{port}"
                for _ in range(100):
                    if proc.poll() is not None:self.fail("Server died")
                    try:
                        catalog=get(base+"/api/vehicle-catalog")
                        break
                    except Exception:time.sleep(.1)
                else:self.fail("Server startup timed out")
                brand=next(b["id"] for b in catalog["brands"] if b["name"]=="Suzuki")
                swift=next(m["id"] for m in catalog["models"] if m["brand_id"]==brand
                           and m["name"]=="Swift")
                profile=post(base+"/api/vehicle-profile",{
                    "brand_id":brand,"model_id":swift,"year":2007,
                    "variant":"GL AT 1.4","powertrain":"gasoline"})
                query={"brand_id":brand,"model_id":swift,"year":2007,
                       "variant":"GL AT 1.4","powertrain":"gasoline"}
                def lookup(**changes):
                    return get(base+"/api/vehicle-documents?"+
                               urlencode({**query,**changes}))
                self.assertEqual(lookup()["diagrams"],[])
                # Old API may still bind demo to a profile; new search excludes it.
                post(base+"/api/diagram-vehicle-bind",{
                    "diagram_id":"junction_block","profile_id":profile["id"]})
                self.assertEqual(lookup()["diagrams"],[])
                with sqlite3.connect(db) as sql:
                    sql.execute("""INSERT INTO viewer_diagrams
                       (id,title,image_file,width,height,vehicle)
                       VALUES(?,?,?,?,?,?)""",
                        ("upload_safe_fixture","Upload fixture",
                         "upload_safe_fixture.png",1200,1500,"User image"))
                request={"diagram_id":"upload_safe_fixture","profile_id":profile["id"],
                         "system":"starting"}
                with self.assertRaises(HTTPError) as error:
                    post(base+"/api/diagram-classify",request)
                self.assertEqual(error.exception.code,400)
                result=post(base+"/api/diagram-classify",
                            {**request,"confirmed_applicability":True})
                self.assertEqual(result["applicability"],"user_declared_unverified")
                match=lookup()
                self.assertEqual(len(match["diagrams"]),1)
                self.assertEqual(match["diagrams"][0]["id"],"upload_safe_fixture")
                self.assertEqual(match["diagrams"][0]["system"],"starting")
                for mismatch in ({"year":2008},{"variant":"GL MT"},
                                 {"powertrain":"diesel"}):
                    self.assertEqual(lookup(**mismatch)["diagrams"],[])
                self.assertIn("starting",get(base+"/api/electrical-systems"))
            finally:
                proc.terminate()
                try:proc.wait(timeout=4)
                except subprocess.TimeoutExpired:proc.kill()

if __name__=="__main__":unittest.main()

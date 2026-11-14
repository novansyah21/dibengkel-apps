"""Local HTTP end-to-end: choose brand/type/name, bind vehicle, inspect evidence."""
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import Request,urlopen

def get(url):
    with urlopen(url,timeout=8) as response:
        return json.load(response)
def post(url,data):
    req=Request(url,data=json.dumps(data).encode(),
                headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=8) as response:
        return json.load(response)

class VehicleHttpSmokeTests(unittest.TestCase):
    def test_brand_model_profile_and_safe_diagnosis_api(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"runtime.sqlite"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port=sock.getsockname()[1]
            proc=subprocess.Popen([sys.executable,"viewer.py","--port",str(port),
                                   "--db",str(db)],
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                base="http://127.0.0.1:"+str(port)
                for _ in range(80):
                    if proc.poll() is not None:self.fail("Local server terminated")
                    try:
                        c=get(base+"/api/vehicle-catalog")
                        break
                    except Exception:time.sleep(.1)
                else:self.fail("Local server startup timed out")
                self.assertGreaterEqual(len(c["brands"]),20)
                b=next(x for x in c["brands"] if x["name"]=="Suzuki")
                m=next(x for x in c["models"] if x["brand_id"]==b["id"]
                       and x["name"]=="Swift")
                v=post(base+"/api/vehicle-profile",{
                    "brand_id":b["id"],"model_id":m["id"],"year":2007,
                    "variant":"GL AT","powertrain":"gasoline"})
                linked=post(base+"/api/diagram-vehicle-bind",{
                    "diagram_id":"junction_block","profile_id":v["id"]})
                self.assertEqual(linked["model_name"],"Swift")
                fetched=get(base+"/api/vehicle-binding?diagram=junction_block")
                self.assertEqual(fetched["year"],2007)
                info=get(base+"/api/diagnosis-options")
                self.assertIn("lights_dead",info["symptoms"])
                case=post(base+"/api/diagnose",{
                    "diagram_id":"junction_block","symptom":"lights_dead",
                    "system":"lighting",
                    "measurements":{"fuse_input_v":12.4,"fuse_output_v":0.1,
                                    "fuse_continuity":"unknown"}})
                self.assertEqual(case["status"],"conditional_hypotheses")
                self.assertFalse(case["electrical_continuity_verified"])
                self.assertEqual(case["vehicle"]["model_name"],"Swift")
                self.assertIn("fuse_voltage_drop",
                              {x["code"] for x in case["findings"]})
                restricted=post(base+"/api/diagnose",{
                    "diagram_id":"junction_block","symptom":"other",
                    "system":"high_voltage","measurements":{}})
                self.assertEqual(restricted["status"],"safety_restricted")
                self.assertEqual(restricted["findings"],[])
                self.assertEqual(len(get(base+
                   "/api/diagnosis-history?diagram=junction_block")),2)
                self.assertIsNone(get(base+
                   "/api/universal-scan?diagram=junction_block")["summary"])
                new=post(base+"/api/vehicle-model-add",{
                    "brand_name":"Custom Test","model_name":"Roadster Test",
                    "body_type":"Coupe"})
                self.assertTrue(new["model_id"].startswith("custom_"))
            finally:
                proc.terminate()
                try:proc.wait(timeout=4)
                except subprocess.TimeoutExpired:proc.kill()

if __name__=="__main__":unittest.main()

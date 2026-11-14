"""v0.4.0: vehicle cascade/catalog, exact profile binding, diagnosis evidence and safety."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from autowiring.vehicle_catalog import (catalog,save_profile,profiles,add_model,
                                         bind,binding)
from autowiring.diagnosis_rules import (evaluate,run,history,validate)
from viewer import setup

def diag_input(symptom="lights_dead",system="lighting",measurements=None):
    return {"symptom":symptom,"system":system,
            "measurements":measurements or {}}

class VehicleCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"autowiring.db"
        with sqlite3.connect(self.db) as con:setup(con)
    def tearDown(self):self.tmp.cleanup()
    def test_catalog_has_brand_vehicle_type_model_and_does_not_claim_year_validity(self):
        c=catalog(self.db)
        brands={b["name"]:b for b in c["brands"]}
        self.assertGreaterEqual(len(brands),20)
        suzuki=brands["Suzuki"]["id"]
        models=[x for x in c["models"] if x["brand_id"]==suzuki]
        self.assertIn("Swift",{m["name"] for m in models})
        self.assertIn("SX4",{m["name"] for m in models})
        self.assertIn("Hatchback",{m["body_type"] for m in models})
        self.assertIn("SUV",c["vehicle_types"])
        self.assertIn("not an exhaustive",c["origin_notice"].lower())
        wuling=brands["Wuling"]["id"]
        self.assertIn("Air ev",{m["name"] for m in c["models"] if m["brand_id"]==wuling})
    def test_vehicle_model_must_belong_to_selected_brand(self):
        c=catalog(self.db);brand=next(b for b in c["brands"] if b["name"]=="Suzuki")
        model=next(m for m in c["models"] if m["name"]=="Swift" and m["brand_id"]==brand["id"])
        profile=save_profile(self.db,{"brand_id":brand["id"],"model_id":model["id"],
                "year":2007,"variant":"GL AT 1.4","powertrain":"gasoline"})
        self.assertEqual(profile["model_name"],"Swift")
        self.assertEqual(profile["year"],2007)
        self.assertEqual(profile["variant"],"GL AT 1.4")
        matched=bind(self.db,"junction_block",profile["id"])
        self.assertEqual(matched["brand_name"],"Suzuki")
        self.assertEqual(matched["model_name"],"Swift")
        self.assertEqual(binding(self.db,"junction_block")["id"],profile["id"])
        other=next(m for m in c["models"] if m["brand_id"]!=brand["id"])
        with self.assertRaisesRegex(ValueError,"does not belong"):
            save_profile(self.db,{"brand_id":brand["id"],"model_id":other["id"],
                "year":2007})
        with self.assertRaisesRegex(ValueError,"Year must"):
            save_profile(self.db,{"brand_id":brand["id"],"model_id":model["id"],
                "year":2200})
    def test_custom_brand_and_model_extend_catalog_persistently(self):
        record=add_model(self.db,{"brand_name":"Custom Local Brand",
             "model_name":"Hatchback Alpha","body_type":"Hatchback"})
        self.assertTrue(record["brand_id"].startswith("custom_"))
        again=add_model(self.db,{"brand_name":"Custom Local Brand",
             "model_name":"hatchback alpha","body_type":"Hatchback"})
        self.assertEqual(again["model_id"],record["model_id"])
        result=catalog(self.db)
        self.assertIn(record["model_id"],{m["id"] for m in result["models"]})
        with self.assertRaisesRegex(ValueError,"body type"):
            add_model(self.db,{"brand_name":"New","model_name":"A",
                              "body_type":"Tank"})
        with self.assertRaisesRegex(ValueError,"not found"):
            bind(self.db,"missing","fake_profile")
    def test_no_implicit_vehicle_compatibility_claim(self):
        c=catalog(self.db)
        self.assertNotIn("2007",str(c["models"]))
        self.assertNotIn("engine_code",str(c["models"]))

class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"autowiring.db"
        with sqlite3.connect(self.db) as con:setup(con)
    def tearDown(self):self.tmp.cleanup()
    def test_no_measurements_means_no_fault_verdict(self):
        result=evaluate(diag_input())
        self.assertEqual(result["status"],"insufficient_evidence")
        self.assertEqual(result["findings"],[])
        self.assertFalse(result["automatic_diagnosis_verified"])
        self.assertFalse(result["electrical_continuity_verified"])
        self.assertTrue(result["missing_evidence"])
    def test_restricted_airbag_and_high_voltage_never_offer_diy_probing(self):
        for system in ("high_voltage","srs"):
            response=evaluate(diag_input(system=system,
                measurements={"battery_voltage_off_v":0.4,
                              "fuse_continuity":"open"}))
            self.assertEqual(response["status"],"safety_restricted")
            self.assertEqual(response["findings"],[])
            self.assertFalse(response["automatic_diagnosis_verified"])
            self.assertTrue(any("teknisi" in x.lower()
                 for x in response["suggested_next_checks"]))
    def test_evidence_based_12v_findings_are_conditional_not_definitive(self):
        report=evaluate(diag_input("fuse_blows","general_12v",{
            "battery_voltage_off_v":11.6,"fuse_continuity":"open",
            "fuse_input_v":12.1,"fuse_output_v":0.0,
            "load_feed_v":0,"ground_voltage_drop_v":1.0,
            "load_active":True
        }))
        codes={f["code"] for f in report["findings"]}
        self.assertEqual(report["status"],"conditional_hypotheses")
        self.assertTrue({"12v_battery_low","fuse_open_observed",
            "fuse_voltage_drop","ground_voltage_drop_high"}<=codes)
        for finding in report["findings"]:
            self.assertFalse(finding["diagnosis_confirmed"])
            self.assertFalse(finding["component_location_verified"])
            self.assertTrue(finding["based_on_fields"])
        self.assertFalse(report["automatic_diagnosis_verified"])
    def test_measurement_validation_rejects_nonfinite_unsafe_ranges(self):
        for bad in (float("nan"),float("inf"),-1,500,"not a number"):
            with self.assertRaises(ValueError):
                validate(diag_input(measurements={"fuse_input_v":bad}))
        with self.assertRaisesRegex(ValueError,"Invalid fuse"):
            validate(diag_input(measurements={"fuse_continuity":"electrical_magic"}))
    def test_diagram_binding_and_case_history_are_persisted_idempotently(self):
        c=catalog(self.db)
        b=next(x for x in c["brands"] if x["name"]=="Wuling")
        m=next(x for x in c["models"] if x["brand_id"]==b["id"] and x["name"]=="Alvez")
        car=save_profile(self.db,{"brand_id":b["id"],"model_id":m["id"],
                               "year":2024,"variant":"EX","powertrain":"gasoline"})
        bind(self.db,"junction_block",car["id"])
        payload=diag_input("no_crank","starting",{"battery_voltage_off_v":11.1})
        first=run(self.db,"junction_block",payload)
        second=run(self.db,"junction_block",payload)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["case_id"],second["case_id"])
        self.assertEqual(first["vehicle"]["brand_name"],"Wuling")
        self.assertEqual(len(history(self.db,"junction_block")),1)
        self.assertEqual(first["diagram_evidence"]["connections_electrically_verified"],0)
        with self.assertRaisesRegex(ValueError,"Unknown diagram"):
            run(self.db,"fake_id",payload)

if __name__=="__main__":unittest.main()

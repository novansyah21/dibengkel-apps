"""v0.3.21 focused terminal OCR regressions. No legacy stages are rerun."""
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from PIL import Image

from autowiring.terminal_accuracy import (
  SCHEMA,VISUAL_REFERENCE,_image_source,_targets,multi_scale_review,
  build,latest,review
)
from autowiring.branch_tracing import JUNCTION_IMAGE_SHA256
from viewer import setup

class AccuracyTests(unittest.TestCase):
 def test_vision_reference_is_separate_from_ocr(self):
  self.assertEqual(len(VISUAL_REFERENCE),4)
  self.assertEqual(VISUAL_REFERENCE[("IG1 SIG","main")]["number"],"12")
  self.assertEqual(VISUAL_REFERENCE[("IG1 SIG","branch")]["number"],"16")
  self.assertEqual(VISUAL_REFERENCE[("ABS","branch")]["number"],"6")
  self.assertEqual(VISUAL_REFERENCE[("BACK","branch")]["number"],"8")
 def test_ocr_consensus_needs_two_distinct_variants(self):
  gray=Image.new("L",(1136,1598),255)
  circle={"x":.7,"y":.5,"r":.007}
  one=Mock(side_effect=[[("12",.89)],[],[]])
  number,confidence,status,evidence=multi_scale_review(gray,circle,one)
  self.assertIsNone(number);self.assertEqual(status,"single_variant_ocr_not_enough")
  self.assertEqual(len(evidence["attempts"]),3)
  self.assertEqual(one.call_count,3)
  two=Mock(side_effect=[[("12",.83)],[("12",.71)],[]])
  number,confidence,status,evidence=multi_scale_review(gray,circle,two)
  self.assertEqual(number,"12");self.assertEqual(status,"multi_variant_ocr_lead_unverified")
  self.assertAlmostEqual(confidence,.83)
 def test_disagreement_is_not_accepted_as_confident_label(self):
  gray=Image.new("L",(1136,1598),255)
  circle={"x":.7,"y":.5,"r":.007}
  disagree=Mock(side_effect=[[("2",.92)],[("8",.77)],[("8",.74)]])
  number,confidence,status,evidence=multi_scale_review(gray,circle,disagree)
  self.assertIsNone(number)
  self.assertEqual(status,"conflicting_new_ocr_variants")
  self.assertEqual(evidence["numbers"],["2","8"])
 def test_missing_image_is_not_silently_processed(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaisesRegex(ValueError,"Gambar sumber"):
    _image_source(Path(tmp)/"missing.png")
   bad=Path(tmp)/"wrong.png"
   Image.new("L",(1136,1598),255).save(bad)
   with self.assertRaisesRegex(ValueError,"Diagram sumber berbeda"):
    _image_source(bad)
 def _database(self,path):
  with sqlite3.connect(path) as con:
   setup(con)
   con.execute("""INSERT INTO corrected_runs_v0319
     (id,diagram_id,enhanced_run_id,input_fingerprint,summary_json)
     VALUES('c','junction_block','e','c-f','{}')""")
   con.execute("""INSERT INTO branch_runs_v0320
     (id,diagram_id,corrected_run_id,input_fingerprint,summary_json)
     VALUES('b','junction_block','c','b-f','{}')""")
   rows=[
    ("IG1 SIG","main_circle",None,None),
    ("IG1 SIG","branch_circle","ig1_branch","G272"),
    ("ABS","abs_branch","abs_branch_key","L315"),
    ("BACK","back_branch","back_branch_key","G272")
   ]
   for name,circle,branchkey,col in rows:
    if branchkey:
     terminal={"number":"2" if name=="BACK" else None,"ocr_confidence":.82 if name=="BACK" else None,"circle_id":circle}
     br=[{"kind":"orthogonal_branch","branch_key":branchkey,"terminal":terminal}]
     evidence={"primary_terminal":{}}
    else:
     br=[];evidence={"primary_terminal":{"circle_id":circle,"number":None,"ocr_confidence":None}}
    # Only one branch_items_v0320 per fuse.
    if name=="IG1 SIG" and branchkey:
     con.execute("UPDATE branch_items_v0320 SET branches_json=? WHERE run_id='b' AND fuse_label='IG1 SIG'",( __import__('json').dumps(br),))
    else:
     import json
     con.execute("""INSERT INTO branch_items_v0320
       (id,run_id,fuse_label,source_kind,component_id,rating_text,rating_status,
        geometry_json,main_path_json,branches_json,evidence_json)
       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
       ("bi:"+name,"b",name,"reused",None,"10A","cached",
         '{}','{}',json.dumps(br),json.dumps(evidence)))
    con.execute("""INSERT INTO independent_circles_v039
      (id,run_id,x,y,r,ocr_text,ocr_confidence,status,reason)
      VALUES(?,?,?,?,?,?,?,?,?)""",
      (circle,None,.7 if name!="BACK" else .79,.4 if name!="BACK" else .6,
       .007,None,0,"ocr_unread","saved circle from v0.3.20"))
   con.commit()
 def test_only_four_cached_circles_and_immutable_prior_run(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Path(folder)/"saved.db";self._database(db)
   original=Path(folder)/"same_source.png"
   Image.new("L",(1136,1598),255).save(original)
   import json
   def reader_factory():
    tokens=["12","16","6","2"]
    count=[0]
    def read(image,psm):
     i=count[0];count[0]+=1
     return [(tokens[i//3],.84)]
    return read,count
   read,count=reader_factory()
   with patch("autowiring.terminal_accuracy._image_source",
              return_value=(Image.new("L",(1136,1598),255),JUNCTION_IMAGE_SHA256)):
    first=build(db,"junction_block",original,read)
    self.assertEqual(first["targeted_problem_circles"],4)
    self.assertEqual(first["new_ocr_attempts"],12)
    self.assertEqual(first["new_ocr_agreed_with_visual_reference"],3)
    self.assertEqual(first["new_ocr_conflicts_with_reference"],1)
    self.assertEqual(first["older_stages_rerun"],0)
    self.assertEqual(count[0],12)
    second=build(db,"junction_block",original,
                 Mock(side_effect=AssertionError("repeated OCR is forbidden")))
    self.assertTrue(second["cache_hit"]);self.assertEqual(second["new_ocr_attempts"],0)
   data=latest(db,"junction_block")
   self.assertEqual(len(data["items"]),4)
   back=next(i for i in data["items"] if i["fuse_label"]=="BACK")
   self.assertEqual(back["new_ocr_number"],"2")
   self.assertEqual(back["reference_number"],"8")
   self.assertEqual(back["evidence"]["comparison_status"],
                    "new_ocr_conflicts_with_source_visual_reference")
   self.assertEqual(back["reference_origin"],
                    "visual_transcription_exact_source_not_machine_ocr")
   self.assertFalse(back["electrically_verified"])
   review(db,"junction_block",back["path_key"],"visually_confirmed","8")
   saved=latest(db,"junction_block")
   corrected=next(i for i in saved["items"] if i["fuse_label"]=="BACK")
   self.assertEqual(corrected["manual_number"],"8")
   self.assertEqual(corrected["display_number"],"8")
   self.assertFalse(corrected["electrically_verified"])
   with sqlite3.connect(db) as con:
    self.assertEqual(con.execute("SELECT count(*) FROM terminal_accuracy_runs_v0321").fetchone()[0],1)
    self.assertEqual(con.execute("SELECT count(*) FROM branch_items_v0320").fetchone()[0],3)
   with self.assertRaises(ValueError):
    review(db,"junction_block","no_key","visually_confirmed","8")
 def test_old_parent_missing_refuses_without_reanalysis(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Path(folder)/"empty.db"
   with sqlite3.connect(db) as con:setup(con)
   with self.assertRaisesRegex(ValueError,"v0.3.20"):
    build(db,"junction_block",Path(folder)/"missing.png")
if __name__=="__main__":unittest.main()

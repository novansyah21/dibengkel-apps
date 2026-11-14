"""MVP 0.1 regression: exactly six sample fuse candidates, manual review,
honest electrical status, immutable report snapshots and zero old-stage rebuild.
"""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw

from autowiring import mvp_review
from autowiring.terminal_accuracy import review
from viewer import setup

SAMPLE_FUSES=[
    ("IG COIL","15A","5",[("orthogonal_branch","ig-coil-branch","6")]),
    ("MTR","10A","6",[("off_page_continuation","mtr-continuation","1")]),
    ("A/B","15A","1",[]),
    ("IG1 SIG","10A",None,[("orthogonal_branch","ig1-branch",None)]),
    ("ABS","10A","9",[("orthogonal_branch","abs-branch",None)]),
    ("BACK","10A","14",[("orthogonal_branch","back-branch","2")]),
]
ACCURACY_TARGETS=[
    ("IG1 SIG","main","main:IG1 SIG","main_circle","12",None),
    ("IG1 SIG","branch","ig1-branch","ig1_branch_circle","16",None),
    ("ABS","branch","abs-branch","abs_circle","6",None),
    ("BACK","branch","back-branch","back_circle","8","2"),
]

def fixture(path):
    with sqlite3.connect(path) as db:
        setup(db)
        db.execute("""INSERT INTO corrected_runs_v0319
            (id,diagram_id,enhanced_run_id,input_fingerprint,summary_json)
            VALUES('corr','junction_block','enh','corr-f','{}')""")
        db.execute("""INSERT INTO branch_runs_v0320
            (id,diagram_id,corrected_run_id,input_fingerprint,summary_json)
            VALUES('br','junction_block','corr','br-f','{}')""")
        db.execute("""INSERT INTO terminal_accuracy_runs_v0321
            (id,diagram_id,parent_run_id,input_fingerprint,summary_json)
            VALUES('acr','junction_block','br','acrf',?)""",
            (json.dumps({"source_image_sha256":mvp_review.JUNCTION_IMAGE_SHA256}),))
        for i,(label,rating,primary_num,bran) in enumerate(SAMPLE_FUSES):
            branches=[]
            for kind,key,number in bran:
                if kind=="off_page_continuation":
                    dest=None;continuation={"marker_text":number}
                else:
                    dest={"number":number,"circle_id":key+":circle",
                          "ocr_confidence":.85 if number else None}
                    continuation=None
                branches.append({
                    "branch_key":key,"kind":kind,"side":"up",
                    "terminal":dest,"continuation":continuation,
                    "points":[[.33,.2+i*.1],[.44,.2+i*.1]],
                    "horizontal_ink_coverage":.85,
                    "status":"visual_hypothesis"
                })
            primary={
                "number":primary_num,
                "circle_id":"main-circle:"+label,
                "ocr_confidence":.85 if primary_num else None
            }
            db.execute("""INSERT INTO branch_items_v0320
               (id,run_id,fuse_label,source_kind,component_id,rating_text,rating_status,
                geometry_json,main_path_json,branches_json,evidence_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
               ("bi"+str(i),"br",label,"saved_v0319",None,rating,
                "cached_rating",json.dumps({"fuse_y_px":i*120}),
                json.dumps({"status":"unverified","points":[[.1,.2+i*.1],[.65,.2+i*.1]],
                            "horizontal_ink_coverage":.92}),
                json.dumps(branches),json.dumps({"primary_terminal":primary})))
        for i,(fuse,kind,key,circle,reference,old_ocr) in enumerate(ACCURACY_TARGETS):
            db.execute("""INSERT INTO terminal_accuracy_items_v0321
                (id,run_id,fuse_label,path_kind,path_key,circle_id,
                 prior_ocr_number,prior_ocr_confidence,new_ocr_number,
                 new_ocr_confidence,ocr_status,reference_number,
                 reference_origin,evidence_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("acc"+str(i),"acr",fuse,kind,key,circle,old_ocr,
                 .82 if old_ocr else None,None,None,
                 "no_confident_new_ocr",reference,
                 "visual_transcription_exact_source_not_machine_ocr",
                 json.dumps({"circle_center":[.6+i*.05,.3+i*.07]})))
        db.commit()

class MVPReviewTests(unittest.TestCase):
    def test_report_is_assisted_only_and_no_ocr_fabrication(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/"db.sqlite";fixture(db)
            result=mvp_review.assemble(db,"junction_block")
            summary=result["summary"]
            self.assertEqual(summary["fuse_visual_candidates"],6)
            self.assertEqual(summary["rating_visual_candidates"],6)
            self.assertEqual(summary["main_paths"],6)
            self.assertEqual(summary["visual_branch_candidates"],5)
            self.assertEqual(summary["off_page_continuations"],1)
            self.assertEqual(summary["terminal_positions_reviewed_or_proposed"],10)
            self.assertEqual(summary["disputed_terminal_positions"],4)
            self.assertEqual(summary["disputed_terminals_remaining_visual_review"],4)
            self.assertEqual(summary["electrically_verified_connections"],0)
            self.assertEqual(summary["older_stages_rerun"],0)
            self.assertFalse(summary["diagnostic_ready"])
            self.assertFalse(summary["feature_gates"]["automotive_diagnostic_decision_support"])
            back=next(x for x in result["circuits"] if x["fuse_label"]=="BACK")
            dest=back["branches"][0]["destination"]
            self.assertIsNone(dest["number"])  # WRONG historic 2 is not promoted.
            self.assertEqual(dest["previous_machine_ocr_candidate"],"2")
            self.assertEqual(dest["independent_visual_reference_not_ocr"],"8")
            self.assertFalse(dest["electrically_verified"])
            mtr=next(x for x in result["circuits"] if x["fuse_label"]=="MTR")
            self.assertEqual(mtr["branches"][0]["destination"]["kind"],
                             "off_page_continuation")
            self.assertIsNone(result["review_queue"][0]["manual_number"])

    def test_review_audit_snapshot_deduplicates_and_remains_non_electrical(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/"db.sqlite";fixture(db)
            first=mvp_review.snapshot(db,"junction_block")
            self.assertFalse(first["cache_hit"])
            second=mvp_review.snapshot(db,"junction_block")
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["snapshot_id"],second["snapshot_id"])
            review(db,"junction_block","main:IG1 SIG","visually_confirmed","12")
            updated=mvp_review.assemble(db,"junction_block")
            self.assertEqual(updated["summary"]["disputed_terminals_remaining_visual_review"],3)
            ig=next(x for x in updated["circuits"] if x["fuse_label"]=="IG1 SIG")
            self.assertEqual(ig["main"]["destination"]["number"],"12")
            self.assertEqual(ig["main"]["destination"]["status"],"human_visual_review_only")
            self.assertFalse(ig["main"]["destination"]["electrically_verified"])
            third=mvp_review.snapshot(db,"junction_block")
            self.assertFalse(third["cache_hit"])
            self.assertNotEqual(first["snapshot_id"],third["snapshot_id"])
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM mvp_snapshots_v0322").fetchone()[0],2)
                self.assertEqual(conn.execute("SELECT count(*) FROM terminal_accuracy_runs_v0321").fetchone()[0],1)
                self.assertEqual(conn.execute("SELECT count(*) FROM branch_runs_v0320").fetchone()[0],1)

    def test_four_manual_visual_reviews_change_only_visual_maturity(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/"db.sqlite";fixture(db)
            for _,_,key,_,number,_ in ACCURACY_TARGETS:
                review(db,"junction_block",key,"visually_confirmed",number)
            data=mvp_review.assemble(db,"junction_block")
            self.assertEqual(data["summary"]["disputed_terminals_remaining_visual_review"],0)
            self.assertEqual(data["summary"]["mvp_mode"],"assisted_visual_review_ready")
            self.assertEqual(data["summary"]["electrically_verified_connections"],0)
            self.assertFalse(data["summary"]["diagnostic_ready"])
            self.assertFalse(data["summary"]["feature_gates"]["fully_automatic_diagram_interpretation"])

    def test_source_lock_and_glpyh_border_preview_are_honest(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/"db.sqlite";fixture(db)
            fake=Path(root)/"source.png"
            img=Image.new("RGB",(1136,1598), "white")
            ImageDraw.Draw(img).ellipse((680,520,705,545),outline="black",width=2)
            img.save(fake)
            with self.assertRaisesRegex(ValueError,"SHA changed"):
                mvp_review.assemble(db,"junction_block",fake)
            with patch.object(mvp_review,"JUNCTION_IMAGE_SHA256",
                              hashlib.sha256(fake.read_bytes()).hexdigest()):
                # Source-lock in v0.3.21 metadata was created for original
                # image, so changing only the local reference must still fail.
                with self.assertRaisesRegex(ValueError,"source lock mismatch"):
                    mvp_review.assemble(db,"junction_block",fake)
            preview=mvp_review._previews(img,[.603,.328])
            self.assertTrue(preview["original_png_base64"])
            self.assertTrue(preview["experimental_circle_border_suppression_png_base64"])
            self.assertIn("does not yield an OCR result",preview["warning"])

    def test_missing_previous_results_never_triggers_recomputation(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/"empty.db"
            with sqlite3.connect(db) as conn:setup(conn)
            with self.assertRaisesRegex(ValueError,"SAME output/autowiring.db"):
                mvp_review.assemble(db,"junction_block")

if __name__=="__main__":
    unittest.main()

"""v0.3.20 — no-repeat, source-locked, branch-aware VISUAL regression tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from PIL import Image,ImageDraw

from autowiring.branch_tracing import (
    SCHEMA, JUNCTION_IMAGE_SHA256, FUSE_ROW_ANCHORS,
    verify_source_layout,find_row,_row_ink,_circle_near_row,
    inspect_vertical_branch,_continuation_candidate,build,latest,
    save_visual_review
)
from viewer import setup

W,H=1136,1598
LAYOUT=dict(FUSE_ROW_ANCHORS)

def fake_image():
    """Six sample rows, five representative junction branches and non-dot crossings."""
    im=Image.new('L',(W,H),255)
    d=ImageDraw.Draw(im)
    ends={"IG COIL":767,"MTR":863,"A/B":997,
          "IG1 SIG":766,"ABS":767,"BACK":766}
    for label,row in FUSE_ROW_ANCHORS:
        d.line([(211,row),(ends[label],row)],fill=0,width=2)
    for label,x,turn,endpoint in [
        ("IG COIL",426,193,904),("IG1 SIG",426,792,904),
        ("ABS",426,901,1091),("BACK",426,1001,907),
    ]:
        row=LAYOUT[label]
        d.line([(x,row),(x,turn),(endpoint,turn)],fill=0,width=2)
        d.ellipse((x-6,row-6,x+6,row+6),fill=0)
    d.line([(309,LAYOUT["MTR"]),(309,1312)],fill=0,width=3)
    d.ellipse((303,366,315,378),fill=0)
    d.rectangle((299,1306,320,1321),outline=0,width=2)
    return im

def sample_circles():
    raw=[
        ("pin5",767,247,"5"),("pin6",863,371,"6"),("ab1",997,451,"1"),
        ("ig12",766,839,None),("abs9",767,951,None),("back14",766,1049,"14"),
        ("g272_6",904,194,None),("g272_16",904,793,None),
        ("l315_6",1091,901,None),("g272_8",907,1001,None),
        ("continue1",308,1311,"1"),
    ]
    return [dict(id=k,x=x/W,y=y/H,r=11/H,ocr_text=txt,
                 ocr_confidence=.9 if txt else 0.)
            for k,x,y,txt in raw]

def fixture_db(path,im):
    with sqlite3.connect(path) as con:
        setup(con)
        con.execute("""
            INSERT INTO enhanced_runs_v0318
            (id,diagram_id,trace_run_id,source_fingerprint,summary_json)
            VALUES('enh','junction_block','trace','enhf','{}')
        """)
        con.execute("""
            INSERT INTO corrected_runs_v0319
            (id,diagram_id,enhanced_run_id,input_fingerprint,summary_json)
            VALUES('corr','junction_block','enh','corrf','{}')
        """)
        for label,terminal in [("IG COIL","5"),("MTR","6"),("ABS","9"),("BACK","14")]:
            row=LAYOUT[label]
            x=309 if label=="MTR" else 426
            term_coord=next(z for z in sample_circles() if z["ocr_text"]==terminal and (
                label!="ABS" or z["id"]=="abs9")) if label!="ABS" else next(z for z in sample_circles() if z["id"]=="abs9")
            corrected_terminal={"number":terminal,"circle_id":term_coord["id"],
                                "x":term_coord["x"],"y":term_coord["y"],"ocr_confidence":.85}
            dot=[dict(x=x/W,y=row/H,pixel_x=x,pixel_y=row,
                      status="visual_junction_candidate",electrically_verified=False)]
            con.execute("""
                INSERT INTO corrected_items_v0319
                (id,run_id,component_id,fuse_label,rating_text,rating_status,
                 rating_evidence_json,terminal_evidence_json,junction_evidence_json,
                 pixel_evidence_json,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,("item:"+label,"corr","component:"+label,label,
                 "15A" if label=="IG COIL" else "10A","reused_v0318_rating",
                 '{}',json.dumps({"best_geometric_candidate":corrected_terminal}),
                 json.dumps(dot),'{}',"unverified"))
        con.execute("""
           INSERT INTO independent_runs_v039(id,diagram_id,summary_json)
           VALUES('ind','junction_block','{}')
        """)
        for c in sample_circles():
            con.execute("""INSERT INTO independent_circles_v039
                (id,run_id,x,y,r,ocr_text,ocr_confidence,status,reason)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (c["id"],"ind",c["x"],c["y"],c["r"],c["ocr_text"],
                 c["ocr_confidence"],"ocr_unread" if not c["ocr_text"] else "ocr_read_unassociated",
                 "synthetic independent OCR fixture"))
        con.commit()

class BranchTracingTests(unittest.TestCase):
    def test_source_profile_hash_cannot_generalize_to_other_image(self):
        im=fake_image()
        self.assertFalse(verify_source_layout(im,"differenthash"))
        self.assertFalse(verify_source_layout(Image.new('L',(600,800)),JUNCTION_IMAGE_SHA256))
        self.assertTrue(verify_source_layout(im,JUNCTION_IMAGE_SHA256))
    def test_horizontal_row_found_without_running_cv_or_segmentation(self):
        im=fake_image()
        for name,y in FUSE_ROW_ANCHORS:
            row,strength=find_row(im,y)
            self.assertLessEqual(abs(row-y),1)
            self.assertGreater(strength,.85)
    def test_circle_nearest_correct_row(self):
        c=_circle_near_row(sample_circles(),193,W,H,min_x_px=500,start_x=426)
        self.assertEqual(c["id"],"g272_6")
        c=_circle_near_row(sample_circles(),842,W,H,min_x_px=620)
        self.assertEqual(c["id"],"ig12")
    def test_unique_bend_can_be_traced_on_source_pixels(self):
        im=fake_image()
        dot={"x":426/W,"y":248/H}
        branches=inspect_vertical_branch(im,dot,sample_circles(),
            reader=Mock(return_value=[("6",.8)]))
        arm=[b for b in branches if b["kind"]=="orthogonal_branch"]
        self.assertEqual(len(arm),1,branches)
        self.assertEqual(arm[0]["side"],"up")
        self.assertTrue(abs(arm[0]["pixel_points"][1][1]-193)<=5)
        self.assertEqual(arm[0]["terminal"]["number"],"6")
        self.assertFalse(arm[0]["electrically_verified"])
    def test_mtr_crosses_other_rows_without_branch_and_ends_at_continuation(self):
        im=fake_image()
        branch=inspect_vertical_branch(im,{"x":309/W,"y":372/H},sample_circles())
        self.assertEqual(len(branch),1,branch)
        self.assertEqual(branch[0]["kind"],"off_page_continuation")
        self.assertEqual(branch[0]["continuation"]["marker_text"],"1")
        self.assertIsNone(branch[0]["terminal"])
        self.assertFalse(branch[0]["electrically_verified"])
    def test_a_b_has_no_false_branch_when_mtr_wire_crosses_without_dot(self):
        im=fake_image()
        from autowiring.trace_corrected import detect_junction_dots
        row=LAYOUT["A/B"]
        d=detect_junction_dots(im,{"points":[[211/W,row/H],[997/W,row/H]]},"junction_block")
        self.assertEqual(d,[],d)
    def test_incremental_six_fuse_build_idempotent_no_old_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"saved.db"
            image_file=Path(tmp)/"source.png"
            im=fake_image();im.save(image_file)
            fixture_db(p,im)
            reader=Mock(return_value=[("6",.84)])
            def rating_reader(_,psm):return [("15A",.93)]
            with patch("autowiring.branch_tracing.verify_source_layout",return_value=True):
                first=build(p,"junction_block",image_file,reader=reader,
                            rating_reader=rating_reader)
                self.assertFalse(first["cache_hit"])
                self.assertEqual(first["fuse_candidates_total"],6)
                self.assertEqual(first["reused_fuses_from_v0319"],4)
                self.assertEqual(first["new_source_locked_fuse_candidates"],2)
                self.assertEqual(first["older_stages_rerun"],0)
                self.assertEqual(first["electrically_verified_connections"],0)
                self.assertGreaterEqual(first["branch_path_hypotheses"],4)
                calls=reader.call_count
                again=build(p,"junction_block",image_file,reader=reader,
                            rating_reader=Mock(side_effect=AssertionError("NO repeated new rating OCR")))
                self.assertTrue(again["cache_hit"])
                self.assertEqual(reader.call_count,calls)
            data=latest(p,"junction_block")
            self.assertEqual(set(x["fuse_label"] for x in data["items"]),
               {label for label,_ in FUSE_ROW_ANCHORS})
            ig=next(x for x in data["items"] if x["fuse_label"]=="IG COIL")
            self.assertFalse(ig["electrically_verified"])
            self.assertTrue(ig["branches"])
            key=ig["branches"][0]["branch_key"]
            save_visual_review(p,"junction_block",key,"visually_matches_source","6")
            updated=latest(p,"junction_block")
            refreshed=next(x for x in updated["items"] if x["fuse_label"]=="IG COIL")
            self.assertEqual(refreshed["branches"][0]["visual_review"],"visually_matches_source")
            self.assertEqual(refreshed["branches"][0]["visual_terminal_text"],"6")
            self.assertFalse(refreshed["branches"][0]["electrically_verified"])
            with sqlite3.connect(p) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM branch_runs_v0320").fetchone()[0],1)
            with self.assertRaises(ValueError):
                save_visual_review(p,"junction_block","fake_key","visually_matches_source")
    def test_refuses_source_mismatch_before_any_saved_result_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"saved.db";im=fake_image();fixture_db(db,im)
            f=Path(tmp)/"different.png";im.save(f)
            with self.assertRaisesRegex(ValueError,"Source-specific"):
                build(db,"junction_block",f)
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM branch_runs_v0320").fetchone()[0],0)
    def test_no_previously_saved_corrected_result_does_not_rerun_old_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"empty.db"
            with sqlite3.connect(db) as c:setup(c)
            with self.assertRaisesRegex(ValueError,"v0.3.19"):
                build(db,"junction_block",Path(tmp)/"image_missing.png")

if __name__=="__main__":
    unittest.main()

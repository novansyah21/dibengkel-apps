"""Regression tests for v0.3.19: source-backed accuracy, no earlier stage re-execution."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import Image,ImageDraw

from autowiring.trace_corrected import (
    recover_cached_rating,split_prior_fuse_labels,targeted_unread_circle_ocr,
    detect_junction_dots,visually_locate_column,build,latest)
from autowiring.trace_review import build as build_trace
from autowiring.trace_enhanced import build as build_enhanced
from test_trace_review import fixture

class CorrectedTraceTests(unittest.TestCase):
    def test_mtr_cached_raw_10a_with_punctuation_and_no_confidence(self):
        crops=[
            {'roi':'right_compact','attempts':[{'psm':7,'raw_tokens':['10A.']}]},
            {'roi':'right_above','attempts':[{'psm':7,'raw_tokens':['10A']}]},
            {'roi':'right_below','attempts':[{'psm':8,'raw_tokens':[]}]}
        ]
        rating,status,evidence=recover_cached_rating(None,crops)
        self.assertEqual(rating,'10A')
        self.assertEqual(status,'corroborated_cached_raw_ocr_review_required')
        self.assertEqual(evidence['distinct_roi_count'],2)
        self.assertFalse(evidence['confidence_available'])
        self.assertTrue(evidence['human_confirmation_required'])
    def test_unconfirmed_one_crop_is_not_rated(self):
        rating,status,_=recover_cached_rating(None,[
            {'roi':'right_compact','attempts':[{'raw_tokens':['10A.']}]}])
        self.assertIsNone(rating)
        self.assertEqual(status,'cached_raw_insufficient_for_rating')
    def test_cached_rating_conflict_never_auto_selected(self):
        rating,status,_=recover_cached_rating(None,[
            {'roi':'right_compact','attempts':[{'raw_tokens':['10A']}]},
            {'roi':'right_above','attempts':[{'raw_tokens':['15A']}]}
        ])
        self.assertIsNone(rating)
        self.assertEqual(status,'conflicting_cached_raw_ratings')
    def test_fuse_number_21_not_a_terminal_14_conflict(self):
        old=[{'circle_id':'fuse21','terminal_text':'21','geometric_distance':.02962},
             {'circle_id':'pin14','terminal_text':'14','geometric_distance':.00715}]
        circles=[
            {'id':'fuse21','x':.15405,'y':.64268,'ocr_text':'21'},
            {'id':'pin14','x':.67430,'y':.65645,'ocr_text':'14'}
        ]
        valid,excluded=split_prior_fuse_labels(old,circles,
                                              {'x':.15713,'y':.65769})
        self.assertEqual([x['terminal_text'] for x in valid],['14'])
        self.assertEqual(excluded[0]['terminal_text'],'21')
        self.assertEqual(excluded[0]['classification'],
                         'fuse_index_circle_not_terminal_candidate')
    def test_focused_abs_9_uses_cached_unread_circle_only(self):
        image=Image.new('L',(1136,1598),255)
        reader=Mock(return_value=[('9',.68)])
        existing=[{'id':'abs9','x':.675176,'y':.595119,
                   'r':.00688,'ocr_text':None,'ocr_confidence':0}]
        found,report=targeted_unread_circle_ocr(
            image,[.66725,.595119],existing,reader)
        self.assertEqual(found['ocr_text'],'9')
        self.assertAlmostEqual(found['ocr_confidence'],.68)
        self.assertEqual(report['status'],
                         'focused_unread_circle_ocr_candidate_needs_review')
        self.assertEqual(reader.call_count,1)
        self.assertTrue(report['crop_png_base64'])
        self.assertFalse(report['electrically_verified'])
    def test_no_focused_ocr_when_previous_circle_read(self):
        image=Image.new('L',(1136,1598),255)
        reader=Mock(side_effect=AssertionError('unexpected OCR'))
        found,report=targeted_unread_circle_ocr(
            image,[.66725,.595119],
            [{'id':'known','x':.675,'y':.595,'r':.0069,'ocr_text':'9','ocr_confidence':.82}],
            reader)
        self.assertIsNone(found)
        self.assertEqual(reader.call_count,0)
    def test_visual_dot_branch_and_crossing_are_distinguished(self):
        image=Image.new('L',(350,220),'white')
        draw=ImageDraw.Draw(image)
        draw.line((20,110,330,110),fill='black',width=3)
        draw.line((110,40,110,110),fill='black',width=3)
        draw.ellipse((104,104,116,116),fill='black')
        # A separate line crossing, no filled junction dot.
        draw.line((240,50,240,170),fill='black',width=3)
        route={'points':[[20/350,110/220],[330/350,110/220]]}
        found=detect_junction_dots(image,route,'other')
        self.assertGreaterEqual(len(found),1)
        self.assertTrue(any(abs(z['pixel_x']-110)<6 for z in found))
        self.assertFalse(any(abs(z['pixel_x']-240)<7 for z in found))
        self.assertTrue(all(z['electrically_verified'] is False for z in found))
    def test_connector_column_is_visual_hint_not_a_pinout(self):
        col=visually_locate_column('junction_block',{'x':.675176,'y':.595},(1136,1598))
        self.assertEqual(col['label'],'E325')
        self.assertFalse(col['pinout_verified'])
        self.assertIsNone(visually_locate_column('other',{'x':.675,'y':.595},(1136,1598)))
    def test_one_click_reuses_v0318_cache_without_new_ocr(self):
        with tempfile.TemporaryDirectory() as path:
            db=Path(path)/'saved.db'
            fixture(db)
            img=Path(path)/'nonexistent.png'
            build_trace(db,'junction_block',img)
            build_enhanced(db,'junction_block',img)
            reader=Mock(side_effect=AssertionError('must not call old OCR'))
            first=build(db,'junction_block',img,reader)
            self.assertFalse(first['cache_hit'])
            self.assertEqual(first['older_stages_rerun'],0)
            self.assertEqual(first['total_rating_candidates'],1)
            again=build(db,'junction_block',img,reader)
            self.assertTrue(again['cache_hit'])
            self.assertEqual(again['targeted_ocr_repeated'],0)
            self.assertEqual(reader.call_count,0)
            result=latest(db,'junction_block')
            self.assertEqual(result['items'][0]['fuse_label'],'IG COIL')
            self.assertFalse(result['items'][0]['electrically_verified'])
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM corrected_runs_v0319').fetchone()[0],1)
                self.assertEqual(con.execute('SELECT count(*) FROM corrected_items_v0319').fetchone()[0],1)
    def test_missing_parent_does_not_run_old_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'missing.db'
            from autowiring.trace_corrected import SCHEMA
            with sqlite3.connect(db) as con:
                con.executescript(SCHEMA)
            with self.assertRaisesRegex(ValueError,'v0.3.18 result not found'):
                build(db,'junction_block',Path(temp)/'absent.png')

if __name__=='__main__': unittest.main()

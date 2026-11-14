"""v0.3.18: incremental-only tracing, OCR crops, ambiguity, and idempotence."""
import base64
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from autowiring.trace_enhanced import (
    parse_rating_words, crop_rating_evidence, follow_endpoint_graph,
    rank_terminal_evidence, build, latest
)
from autowiring.trace_review import build as build_trace
from test_trace_review import fixture

class EnhancedTraceTests(unittest.TestCase):
    def test_rating_tokens_strict_full_ampere_label(self):
        self.assertEqual(parse_rating_words([('15',.93),('A',.88)])[0]['rating'],'15A')
        self.assertEqual(parse_rating_words([('7,5',.90),('A',.80)])[0]['rating'],'7.5A')
        self.assertEqual(parse_rating_words([('10A',.95)])[0]['rating'],'10A')
        self.assertEqual(parse_rating_words([('15',.95)]),[])
        self.assertEqual(parse_rating_words([('15',.95),('B',.95)]),[])
        self.assertEqual(parse_rating_words([('15A',.20)]),[])
    def test_new_ocr_crops_provide_original_image_evidence(self):
        from PIL import Image
        image=Image.new('L',(1136,1598),255)
        gap={'neighbor_x':.18574,'endpoint_y':.23279,'neighbor_y':.23279}
        reader=Mock(return_value=[('10',.90),('A',.85)])
        rating,status,hits,crops,attempts=crop_rating_evidence(image,gap,reader)
        self.assertEqual(rating,'10A')
        self.assertEqual(status,'new_localized_rating_candidate_unverified')
        self.assertEqual(attempts,6)
        self.assertEqual(len(crops),3)
        self.assertEqual(reader.call_count,6)
        self.assertEqual([e['roi'] for e in crops],
                         ['right_compact','right_above','right_below'])
        for evidence in crops:
            self.assertEqual(len(evidence['attempts']),2)
            self.assertEqual(
                Image.open(io.BytesIO(base64.b64decode(evidence['crop_png_base64']))).mode,
                'L')
    def test_conflicting_rating_is_not_selected(self):
        from PIL import Image
        image=Image.new('L',(1136,1598),255)
        reader=Mock(side_effect=[[('10A',.8)],[('15A',.9)]]*3)
        rating,status,_,_,_=crop_rating_evidence(image,{
            'neighbor_x':.185,'endpoint_y':.23,'neighbor_y':.23},reader)
        self.assertIsNone(rating)
        self.assertEqual(status,'conflicting_new_roi_ocr')
    def test_turn_allowed_only_at_unique_endpoints(self):
        base={'id':'base','x1':.20,'y1':.20,'x2':.30,'y2':.20}
        seg=[{'source_edge_id':'base','classification':'candidate_wire',
              'x1':.20,'y1':.20,'x2':.30,'y2':.20},
             {'source_edge_id':'bend','classification':'candidate_wire',
              'x1':.30,'y1':.20,'x2':.30,'y2':.38},
             {'source_edge_id':'finish','classification':'candidate_wire',
              'x1':.30,'y1':.38,'x2':.50,'y2':.38}]
        result=follow_endpoint_graph(base,seg)
        self.assertEqual(result['edge_ids'],['base','bend','finish'])
        self.assertEqual(result['status'],'endpoint_join_geometric_hypothesis')
        self.assertFalse(result['verified'])
    def test_branch_and_tee_never_joined(self):
        base={'id':'base','x1':.20,'y1':.20,'x2':.30,'y2':.20}
        branch=[
            {'source_edge_id':'a','classification':'candidate_wire','x1':.30,'y1':.20,'x2':.40,'y2':.20},
            {'source_edge_id':'b','classification':'candidate_wire','x1':.30,'y1':.20,'x2':.30,'y2':.30}
        ]
        result=follow_endpoint_graph(base,branch)
        self.assertEqual(result['edge_ids'],['base'])
        self.assertEqual(result['status'],'branching_endpoint_requires_review')
        tee=[{'source_edge_id':'tee','classification':'candidate_wire',
              'x1':.30,'y1':.10,'x2':.30,'y2':.30}]
        result=follow_endpoint_graph(base,tee)
        self.assertEqual(result['edge_ids'],['base'])
        self.assertEqual(result['status'],'tee_or_interior_junction_requires_review')
    def test_terminal_history_conflict_is_reported_not_suppressed(self):
        endpoint=[.66725,.65769]
        circles=[{'id':'near14','ocr_text':'14','ocr_confidence':.85,'x':.67430,'y':.65644}]
        prior=[{'terminal_text':'14','geometric_distance':.00715,'circle_id':'old14'},
               {'terminal_text':'21','geometric_distance':.02962,'circle_id':'old21'}]
        result=rank_terminal_evidence(endpoint,circles,prior)
        self.assertEqual(result['best_geometric_candidate']['number'],'14')
        self.assertTrue(result['conflict'])
        self.assertEqual(result['historical_numbers'],['14','21'])
        self.assertEqual(result['status'],'conflicting_historical_terminal_numbers_review_required')
        self.assertFalse(result['electrically_verified'])
    def test_current_conflict_does_not_choose_arbitrarily(self):
        circles=[{'id':'a','ocr_text':'5','ocr_confidence':.9,'x':.71,'y':.2},
                 {'id':'b','ocr_text':'6','ocr_confidence':.91,'x':.72,'y':.2}]
        result=rank_terminal_evidence([.70,.2],circles,[])
        self.assertTrue(result['conflict'])
        self.assertIsNone(result['best_geometric_candidate'])
    def test_reuse_v0317_and_do_not_repeat_old_or_new_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'saved.db'
            fixture(db)
            image=Path(tmp)/'missing.png'
            old=build_trace(db,'junction_block',image)
            self.assertFalse(old['cache_hit'])
            # Prior reading exists, so new OCR is NOT called at all.
            reader=Mock(side_effect=AssertionError('OCR should not be called'))
            new=build(db,'junction_block',image,reader)
            self.assertEqual(new['older_stages_rerun'],0)
            self.assertEqual(new['targeted_new_ocr_attempts'],0)
            self.assertFalse(new['cache_hit'])
            new_again=build(db,'junction_block',image,reader)
            self.assertTrue(new_again['cache_hit'])
            data=latest(db,'junction_block')
            self.assertEqual(len(data['items']),1)
            self.assertEqual(data['items'][0]['rating_text'],'15A')
            self.assertFalse(data['items'][0]['electrically_verified'])
            with sqlite3.connect(db) as sql:
                self.assertEqual(sql.execute('SELECT count(*) FROM enhanced_runs_v0318').fetchone()[0],1)
                self.assertEqual(sql.execute('SELECT count(*) FROM enhanced_items_v0318').fetchone()[0],1)
            # Any new parent trace run should invalidate v0.3.18 view, not silently reuse stale input.
            with sqlite3.connect(db) as sql:
                sql.execute("""INSERT INTO trace_runs_v0317
                  (id,diagram_id,component_run_id,input_fingerprint,summary_json)
                  VALUES('new','junction_block','cr','newinput','{}')""")
                sql.commit()
            self.assertTrue(latest(db,'junction_block')['stale'])
    def test_without_old_trace_fails_before_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db.sqlite'
            with sqlite3.connect(path) as con:
                from autowiring.trace_enhanced import SCHEMA
                from autowiring.trace_review import SCHEMA as OLD_SCHEMA
                con.executescript(SCHEMA+OLD_SCHEMA)
            with self.assertRaisesRegex(ValueError,'v0.3.17'):
                build(path,'junction_block',Path(tmp)/'missing.png')

if __name__=='__main__':unittest.main()

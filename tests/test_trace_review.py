"""v0.3.17 regressions: no upstream recomputation, idempotent cache, honest trace."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from autowiring.trace_review import (
    SCHEMA, build, latest, normalize_rating, review, trace_terminal, _trace_chain, measure_shape
)

def fixture(path):
    """Minimal persisted v0.3.16-era database: no image, CV or Tesseract required."""
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA + """
        CREATE TABLE component_runs_v0316(id TEXT PRIMARY KEY,diagram_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE component_items_v0316(
          id TEXT PRIMARY KEY,run_id TEXT,source_gap_id TEXT,fuse_label TEXT,
          source_edge_id TEXT,target_edge_id TEXT,x REAL,y REAL);
        CREATE TABLE continuity_items_v0314(
          id TEXT PRIMARY KEY,association_id TEXT,endpoint_x REAL,endpoint_y REAL,
          neighbor_x REAL,neighbor_y REAL);
        CREATE TABLE association_candidates_v035(id TEXT PRIMARY KEY,run_id TEXT);
        CREATE TABLE association_runs_v035(id TEXT PRIMARY KEY,segment_run_id TEXT);
        CREATE TABLE graph_edges_v033(
          id TEXT PRIMARY KEY,x1 REAL,y1 REAL,x2 REAL,y2 REAL);
        CREATE TABLE segment_edges_v034(
          id TEXT PRIMARY KEY,run_id TEXT,source_edge_id TEXT,
          classification TEXT,x1 REAL,y1 REAL,x2 REAL,y2 REAL);
        CREATE TABLE independent_runs_v039(
          id TEXT PRIMARY KEY,diagram_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE independent_circles_v039(
          id TEXT PRIMARY KEY,run_id TEXT,x REAL,y REAL,ocr_text TEXT,ocr_confidence REAL);
        CREATE TABLE path_match_runs_v0310(
          id TEXT PRIMARY KEY,diagram_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE path_matches_v0310(
          id TEXT PRIMARY KEY,run_id TEXT,fuse_label TEXT,association_id TEXT,
          circle_id TEXT,terminal_text TEXT,ocr_confidence REAL,geometric_distance REAL,
          status TEXT,reason TEXT);
        CREATE TABLE auto_runs_v032(
          id TEXT PRIMARY KEY,diagram_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE auto_candidates_v032(
          id TEXT PRIMARY KEY,run_id TEXT,kind TEXT,label TEXT,
          x REAL,y REAL,w REAL,h REAL,confidence REAL);
        """)
        db.execute("INSERT INTO component_runs_v0316(id,diagram_id) VALUES('cr','junction_block')")
        db.execute("""INSERT INTO component_items_v0316
           VALUES('comp','cr','gap','IG COIL','left','right',.157,.2)""")
        db.execute("INSERT INTO continuity_items_v0314 VALUES('gap','assoc',.128,.2,.185,.2)")
        db.execute("INSERT INTO association_candidates_v035 VALUES('assoc','assoc_run')")
        db.execute("INSERT INTO association_runs_v035 VALUES('assoc_run','segments')")
        db.execute("INSERT INTO graph_edges_v033 VALUES('right',.185,.2,.7,.2)")
        db.execute("INSERT INTO segment_edges_v034 VALUES('s1','segments','right','candidate_wire',.185,.2,.7,.2)")
        db.execute("INSERT INTO segment_edges_v034 VALUES('s2','segments','extension','candidate_wire',.7,.2,.72,.2)")
        db.execute("INSERT INTO independent_runs_v039(id,diagram_id) VALUES('ir','junction_block')")
        db.execute("INSERT INTO independent_circles_v039 VALUES('pin5','ir',.727,.201,'5',.91)")
        db.execute("INSERT INTO path_match_runs_v0310(id,diagram_id) VALUES('pm','junction_block')")
        db.execute("""INSERT INTO path_matches_v0310
          VALUES('pm1','pm','IG COIL','assoc','pin5','5',.91,.014,
                 'geometric_candidate_unverified','historic geometry only')""")
        db.execute("INSERT INTO auto_runs_v032(id,diagram_id) VALUES('ar','junction_block')")
        db.execute("""INSERT INTO auto_candidates_v032
          VALUES('rating','ar','ocr_fuse_label','15A',.197,.19,.018,.019,.92)""")
        db.commit()

class TraceReviewTests(unittest.TestCase):
    def test_rating_is_strict(self):
        self.assertEqual(normalize_rating(' 15 A '),'15A')
        self.assertEqual(normalize_rating('7,5A'),'7.5A')
        self.assertIsNone(normalize_rating('15A 10A'))
        self.assertIsNone(normalize_rating('IG COIL'))
    def test_no_ocr_without_circle(self):
        candidate,ranked,status=trace_terminal([[.3,.3],[.7,.3]],[])
        self.assertIsNone(candidate)
        self.assertEqual(status,'no_eligible_cached_ocr_circle_near_endpoint')
    def test_ambiguous_terminal_not_selected(self):
        c=[dict(id='a',ocr_text='5',ocr_confidence=.9,x=.71,y=.2),
           dict(id='b',ocr_text='6',ocr_confidence=.9,x=.712,y=.2)]
        chosen,alternatives,status=trace_terminal([[.2,.2],[.7,.2]],c)
        self.assertIsNone(chosen)
        self.assertEqual(status,'ambiguous_terminal_circles')
        self.assertEqual(len(alternatives),2)
    def test_crossing_does_not_join(self):
        start={'id':'wire','x1':.2,'y1':.2,'x2':.7,'y2':.2}
        pool=[{'source_edge_id':'vertical','classification':'candidate_wire',
               'x1':.5,'y1':.1,'x2':.5,'y2':.3}]
        points,ids,status=_trace_chain(start,pool)
        self.assertEqual(ids,['wire'])
        self.assertEqual(len(points),2)
    def test_reuse_and_idempotent_build_and_manual_visual_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'saved.db'
            fixture(path)
            original_image=Path(tmp)/'nonexistent.png'
            first=build(path,'junction_block',original_image)
            self.assertFalse(first['cache_hit'])
            self.assertEqual(first['older_stages_rerun'],0)
            self.assertEqual(first['focused_rating_ocr_attempts'],0)
            self.assertEqual(first['ratings_ocr_candidates'],1)
            self.assertEqual(first['geometric_terminal_leads'],1)
            self.assertEqual(first['previous_path_match_rows_reused'],1)
            self.assertEqual(first['electrically_verified_connections'],0)
            before=latest(path,'junction_block')
            self.assertEqual(before['items'][0]['terminal_text'],'5')
            self.assertEqual(before['items'][0]['rating_text'],'15A')
            self.assertFalse(before['items'][0]['trace']['electrically_verified'])
            self.assertEqual(len(before['items'][0]['trace']['prior_terminal_suggestions']),1)
            second=build(path,'junction_block',original_image)
            self.assertTrue(second['cache_hit'])
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM trace_runs_v0317').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT count(*) FROM trace_items_v0317').fetchone()[0],1)
            review(path,'junction_block','comp','confirmed_fuse_symbol','10A')
            after=latest(path,'junction_block')
            self.assertEqual(after['items'][0]['human_review'],'confirmed_fuse_symbol')
            self.assertEqual(after['items'][0]['display_rating'],'10A')
            self.assertEqual(after['run']['visual_reviewed_symbols'],1)
            self.assertFalse(after['items'][0]['electrically_verified'])
            with self.assertRaises(ValueError):
                review(path,'junction_block','another_component','confirmed_fuse_symbol')
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM trace_runs_v0317').fetchone()[0],1)
                db.execute("INSERT INTO component_runs_v0316(id,diagram_id) VALUES('new_cr','junction_block')")
                db.commit()
            stale=latest(path,'junction_block')
            self.assertTrue(stale['stale'])
            self.assertIsNone(stale['run'])

if __name__=='__main__':
    unittest.main()

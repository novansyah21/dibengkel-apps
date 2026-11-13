import tempfile,sqlite3,unittest
from pathlib import Path
from autowiring.auto_mapping import SCHEMA as AUTO
from autowiring.circuit_graph import build,latest
class GraphTests(unittest.TestCase):
 def test_crossing_remains_ambiguous(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db.sqlite'
   with sqlite3.connect(p) as db:
    db.executescript(AUTO)
    db.execute("INSERT INTO auto_runs_v032(id,diagram_id,image_sha256,ocr_available,cv_available,ocr_count,line_count) VALUES('r','test','hash',1,1,0,2)")
    for i,axis,x,y,w,h in [('h','horizontal',.1,.49,.8,.02),('v','vertical',.49,.1,.02,.8)]:
     db.execute("INSERT INTO auto_candidates_v032(id,run_id,diagram_id,kind,label,x,y,w,h,confidence,source) VALUES(?,'r','test','line_segment_candidate',?,?,?,?,?,.5,'cv')",(i,axis,x,y,w,h))
   out=build(p,'test');self.assertEqual(out['edges'],2);self.assertEqual(out['ambiguous_crossings'],1);self.assertEqual(out['electrically_verified_connections'],0)
   self.assertEqual(len(latest(p,'test')['events']),1)

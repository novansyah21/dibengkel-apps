import unittest
from autowiring.continuity_audit import candidates
class ContinuityTests(unittest.TestCase):
 def test_nearby_collinear(self):
  a=dict(source_edge_id='a',x1=.1,y1=.15,x2=.3,y2=.15)
  b=dict(source_edge_id='b',x1=.32,y1=.15,x2=.5,y2=.15)
  x=candidates(a,[a,b]);self.assertEqual(len(x),1)
  self.assertEqual(x[0]['status'],'visual_gap_requires_review')
 def test_different_rows_not_connected(self):
  a=dict(source_edge_id='a',x1=.1,y1=.15,x2=.3,y2=.15)
  b=dict(source_edge_id='b',x1=.32,y1=.23,x2=.5,y2=.23)
  self.assertEqual(candidates(a,[a,b]),[])
if __name__=='__main__':unittest.main()

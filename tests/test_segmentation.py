import unittest
from autowiring.segmentation import classify,_group
class TestSegmentation(unittest.TestCase):
 def test_column_excluded(self):
  self.assertEqual(classify('junction_block',dict(axis='vertical',x1=.7,x2=.7,y1=.1,y2=.8))[1],'excluded_structural')
 def test_horizontal_kept(self):
  self.assertEqual(classify('junction_block',dict(axis='horizontal',x1=.1,x2=.9,y1=.3,y2=.3))[1],'candidate_wire')
 def test_bottom_excluded(self):
  self.assertEqual(classify('junction_block',dict(axis='horizontal',x1=.1,x2=.9,y1=.95,y2=.95))[1],'excluded_structural')
 def test_generic_kept(self):
  self.assertEqual(classify('bcm_wiring',dict(axis='vertical',x1=.7,x2=.7,y1=.1,y2=.8))[1],'candidate_wire')
 def test_collinear_group(self):
  a=[dict(axis='horizontal',x1=.1,x2=.3,y1=.2,y2=.2),dict(axis='horizontal',x1=.302,x2=.5,y1=.2,y2=.2)]
  self.assertEqual(len(_group(a)),1)
if __name__=='__main__':unittest.main()

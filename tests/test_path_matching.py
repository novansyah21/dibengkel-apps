import unittest
from autowiring.path_matching import match_one
EDGE=dict(x1=.2,y1=.3,x2=.7,y2=.3)
class MatchTests(unittest.TestCase):
 def test_match(self):
  result,reason=match_one([EDGE],[dict(id='c1',x=.73,y=.3,ocr_text='6')])
  self.assertEqual(result['circle']['ocr_text'],'6')
  self.assertEqual(reason,'geometric_row_candidate_only')
 def test_reject_other_row(self):
  result,reason=match_one([EDGE],[dict(x=.73,y=.5,ocr_text='6')])
  self.assertIsNone(result)
 def test_ambiguous(self):
  circles=[dict(x=.73,y=.3,ocr_text='6'),dict(x=.731,y=.3,ocr_text='5')]
  result,reason=match_one([EDGE],circles)
  self.assertIsNone(result);self.assertEqual(reason,'ambiguous_circle_candidates')
if __name__=='__main__':unittest.main()

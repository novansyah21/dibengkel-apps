import unittest
from autowiring.match_diagnostics import diagnose
class DiagnosticTests(unittest.TestCase):
 def test_vertical_rejection(self):
  edges=[dict(x1=.2,y1=.1,x2=.6,y2=.1)]
  circles=[dict(id='a',ocr_text='6',ocr_confidence=.8,x=.61,y=.13)]
  x,y,opts,reason=diagnose(edges,circles)
  self.assertEqual(reason,'no_readable_circle_on_segment_row')
  self.assertIn('vertical_offset_exceeds_tolerance',opts[0]['rejection_reasons'])
 def test_valid_candidate(self):
  edges=[dict(x1=.2,y1=.1,x2=.6,y2=.1)]
  circles=[dict(id='a',ocr_text='5',ocr_confidence=.7,x=.61,y=.105)]
  self.assertEqual(diagnose(edges,circles)[-1],'geometric_row_candidate_only')
if __name__=='__main__':unittest.main()

import unittest
from autowiring.terminal_detection import column_candidate,endpoint
class TerminalDetectionTests(unittest.TestCase):
 def test_header_match(self):
  h=[dict(label='G271',x=.49,w=.02),dict(label='E325',x=.8,w=.02)]
  self.assertEqual(column_candidate(h,.5),'G271')
 def test_ambiguous_header(self):
  h=[dict(label='G271',x=.49,w=.02),dict(label='G272',x=.495,w=.02)]
  self.assertIsNone(column_candidate(h,.5))
 def test_outside_threshold(self):
  self.assertIsNone(column_candidate([dict(label='G271',x=.49,w=.02)],.8))
 def test_right_endpoint(self):
  self.assertEqual(endpoint([dict(x1=.1,x2=.6,y1=.2,y2=.2),dict(x1=.3,x2=.5,y1=.4,y2=.4)]),(.6,.2))
if __name__=='__main__':unittest.main()

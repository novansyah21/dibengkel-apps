import unittest
from autowiring.circle_detection import match_circles
class CircleMatchTests(unittest.TestCase):
 def test_nearest(self):
  c=[dict(x=.8,y=.2),dict(x=.6,y=.5)]
  self.assertEqual(match_circles(c,.801,.201)[1],c[0])
 def test_reject_distant(self):
  self.assertIsNone(match_circles([dict(x=.8,y=.2)],.2,.2))
 def test_reject_ambiguous(self):
  c=[dict(x=.8,y=.2),dict(x=.802,y=.2)]
  self.assertIsNone(match_circles(c,.801,.2))
if __name__=='__main__':unittest.main()

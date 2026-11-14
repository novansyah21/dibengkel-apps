import unittest
from autowiring.evidence import rank_circle
class EvidenceTests(unittest.TestCase):
 def test_nearest(self):
  label,dist,status=rank_circle(dict(x=.5,y=.5),[dict(fuse_label='MTR',endpoint_x=.51,endpoint_y=.5)])
  self.assertEqual(label,'MTR');self.assertEqual(status,'nearest_endpoint_only')
 def test_far(self):
  label,dist,status=rank_circle(dict(x=.1,y=.1),[dict(fuse_label='MTR',endpoint_x=.5,endpoint_y=.5)])
  self.assertIsNone(label);self.assertEqual(status,'too_far_from_endpoint')
 def test_tie(self):
  endpoints=[dict(fuse_label='MTR',endpoint_x=.5,endpoint_y=.5),dict(fuse_label='ABS',endpoint_x=.502,endpoint_y=.5)]
  label,dist,status=rank_circle(dict(x=.501,y=.5),endpoints)
  self.assertIsNone(label);self.assertEqual(status,'ambiguous_nearest_endpoint')
if __name__=='__main__':unittest.main()

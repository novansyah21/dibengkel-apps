import unittest
from autowiring.component_graph import classify
class ComponentGraphTests(unittest.TestCase):
 def test_fuse_is_only_hypothesis(self):
  r=classify({'gap':.056,'fuse_label':'IG COIL'},{'ink_fraction':.25,'centerline_ink_fraction':.17})
  self.assertEqual(r['component_type'],'fuse_symbol_candidate')
  self.assertIn('review',r['status'])
  self.assertIsNone(r['rating_text'])
 def test_unknown_does_not_force_fuse(self):
  r=classify({'gap':.09,'fuse_label':'ABS'},{'ink_fraction':0,'centerline_ink_fraction':0})
  self.assertEqual(r['component_type'],'unknown_component_candidate')
if __name__=='__main__':unittest.main()

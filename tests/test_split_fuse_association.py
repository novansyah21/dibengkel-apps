import unittest
from autowiring.fuse_audit import audit
from autowiring.association import candidates
class SplitFuseTests(unittest.TestCase):
 def test_split_tokens_audited(self):
  labels=[dict(id='a',kind='ocr_text',label='IG',x=.10,y=.20,w=.02,h=.01),dict(id='b',kind='ocr_text',label='COIL',x=.125,y=.20,w=.04,h=.01)]
  edges=[dict(source_edge_id='e1',classification='candidate_wire',x1=.1,y1=.205,x2=.7,y2=.205,group_id='g')]
  self.assertEqual(audit(labels,edges,[])[0]['edge_ids'],['e1'])
  self.assertEqual(candidates(labels,edges),[])
if __name__=='__main__':unittest.main()

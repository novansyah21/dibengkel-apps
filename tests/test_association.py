import unittest
from autowiring.association import candidates
class AssociationTests(unittest.TestCase):
 def test_fuse_to_horizontal(self):
  labels=[dict(id='f1',kind='ocr_fuse_label',label='MTR',x=.1,y=.19,w=.04,h=.02)]
  edges=[dict(source_edge_id='e1',classification='candidate_wire',x1=.1,x2=.8,y1=.2,y2=.2,group_id='g')]
  r=candidates(labels,edges)
  self.assertEqual(len(r),1);self.assertEqual(r[0]['edge_ids'],['e1'])
  self.assertIsNone(r[0]['terminal_text'])
 def test_excluded_ignored(self):
  labels=[dict(id='f1',kind='ocr_fuse_label',label='ABS',x=.1,y=.19,w=.04,h=.02)]
  edges=[dict(source_edge_id='e1',classification='excluded_structural',x1=.1,x2=.8,y1=.2,y2=.2,group_id='g')]
  self.assertEqual(candidates(labels,edges),[])
 def test_distant_label_ignored(self):
  labels=[dict(id='f1',kind='ocr_fuse_label',label='BACK',x=.1,y=.7,w=.04,h=.02)]
  edges=[dict(source_edge_id='e1',classification='candidate_wire',x1=.1,x2=.8,y1=.2,y2=.2,group_id='g')]
  self.assertEqual(candidates(labels,edges),[])
 def test_terminal_text_not_assumed(self):
  labels=[dict(id='f1',kind='ocr_fuse_label',label='MTR',x=.1,y=.19,w=.04,h=.02),dict(id='t1',kind='ocr_terminal_number_candidate',label='6',x=.79,y=.19,w=.02,h=.02)]
  edges=[dict(source_edge_id='e1',classification='candidate_wire',x1=.1,x2=.8,y1=.2,y2=.2,group_id='g')]
  self.assertEqual(candidates(labels,edges)[0]['terminal_text'],'6')
if __name__=='__main__':unittest.main()

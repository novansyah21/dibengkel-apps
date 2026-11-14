import unittest
from autowiring.fuse_audit import canonical,audit
class FuseAuditTests(unittest.TestCase):
 def test_labels(self):
  for raw,expected in [('IG COIL','IG COIL'),('IGCOIL','IG COIL'),('A/B CONT','A/B'),('A/B','A/B'),('MTR','MTR')]:self.assertEqual(canonical(raw),expected)
 def test_split_ocr(self):
  a=dict(id='a',kind='ocr_text',label='IG',x=.1,y=.2,w=.02,h=.01)
  b=dict(id='b',kind='ocr_text',label='COIL',x=.125,y=.2,w=.04,h=.01)
  e=dict(classification='candidate_wire',x1=.1,y1=.205,x2=.6,y2=.205,source_edge_id='edge1')
  rows=audit([a,b],[e],[])
  self.assertEqual(rows[0]['label'],'IG COIL')
  self.assertEqual(rows[0]['status'],'missing_association_candidate')
 def test_no_invented_label(self):
  self.assertEqual(audit([],[],[]),[])
if __name__=='__main__':unittest.main()

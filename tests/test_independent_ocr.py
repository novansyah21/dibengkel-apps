import unittest
from autowiring.independent_ocr import scan_circles
class IndependentOCRTests(unittest.TestCase):
 def test_reads_all_without_endpoint_filter(self):
  circles=[{'x':.1,'y':.2,'r':.01},{'x':.8,'y':.9,'r':.01}]
  calls=[]
  def fake(image,c):
   calls.append(c['x'])
   return ('6',.8,'test') if c['x']==.8 else (None,0.,'no OCR')
  rows=scan_circles(circles,None,fake)
  self.assertEqual(calls,[.1,.8])
  self.assertEqual(rows[1]['ocr_text'],'6')
  self.assertEqual(rows[1]['status'],'ocr_read_unassociated')
if __name__=='__main__':unittest.main()

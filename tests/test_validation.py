import unittest
from autowiring.validation import magic,eligible
class ValidationTests(unittest.TestCase):
 def test_magic(self):
  self.assertEqual(magic(b'\x89PNG\r\n\x1a\n'+b'0'*20),'png')
  self.assertEqual(magic(b'GIF89a'+b'0'*20),'gif')
  self.assertIsNone(magic(b'<html>'))
 def test_filter(self):
  self.assertTrue(eligible('https://charm.li/images/example/'))
  self.assertFalse(eligible('https://charm.li/icons/diagrams.svg'))
if __name__=='__main__':unittest.main()

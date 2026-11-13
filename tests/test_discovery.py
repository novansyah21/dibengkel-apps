import sqlite3,unittest
from autowiring.core import schema
from autowiring.discovery import extend_schema,import_report,classify_link,summary

class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON');schema(self.db);extend_schema(self.db)
 def tearDown(self):self.db.close()
 def test_charm_year_not_model(self):
  report={'sources':[{'source':'charm','url':'https://charm.li/Suzuki/','links':[{'kind':'page','url':'https://charm.li/Suzuki/2007/','label':'2007'}]}]}
  import_report(self.db,report)
  self.assertIn('Suzuki',summary(self.db)['manufacturers'])
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM vehicle_models').fetchone()[0],0)
  self.assertEqual(self.db.execute('SELECT model_year FROM catalogue_nodes').fetchone()[0],2007)
 def test_bmw_model(self):
  report={'sources':[{'source':'bmwteka','url':'https://bmwteka.com/en/bmw/e36','links':[{'kind':'page','url':'https://bmwteka.com/en/bmw/e36','label':'BMW E36'}]}]}
  import_report(self.db,report)
  self.assertEqual(self.db.execute('SELECT code FROM vehicle_models').fetchone()[0],'E36')
 def test_no_false_diagrams(self):
  self.assertEqual(classify_link('bmwteka','https://bmwteka.com/en/tis/documents/123','repair')[0],'repair_document_candidate')
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM diagrams').fetchone()[0],0)
if __name__=='__main__':unittest.main()

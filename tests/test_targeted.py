import sqlite3,unittest
from autowiring.core import schema
from autowiring.discovery import extend_schema,manufacturer_id,record_link
from autowiring.targeted import migrate,promote_candidates,split_charm_variant,classify_document
class TestTargeted(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');schema(self.db);extend_schema(self.db);migrate(self.db)
  self.db.execute("INSERT INTO sources(slug,base_url) VALUES('charm','https://charm.li/Suzuki/')")
 def tearDown(self):self.db.close()
 def test_variant(self):
  self.assertEqual(split_charm_variant('SX4 2WD L4-2.0L'),('SX4','2WD','L4-2.0L'))
 def test_promotion(self):
  record_link(self.db,1,'charm','https://charm.li/Suzuki/2007/',{'kind':'page','url':'https://charm.li/Suzuki/2007/SX4%202WD%20L4-2.0L/','label':'SX4 2WD L4-2.0L'})
  promote_candidates(self.db)
  self.assertEqual(self.db.execute('SELECT code FROM vehicle_models').fetchone()[0],'SX4')
  self.assertEqual(self.db.execute('SELECT model_year,engine,drivetrain,status FROM vehicle_variants_v2').fetchone(),(2007,'L4-2.0L','2WD','candidate'))
 def test_classification(self):
  self.assertEqual(classify_document('https://example.org/doc','Electrical Wiring Diagram'),'wiring_diagram_candidate')
if __name__=='__main__':unittest.main()

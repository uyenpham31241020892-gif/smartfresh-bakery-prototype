"""The assumed cost is based on preparation and list price, not discounted sales."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.costs import estimate

class Costs(unittest.TestCase):
 def test_unsold_stock_is_included_once_and_discounts_do_not_reduce_cost(self):
  p={'sku':dict(price=25000,prepared=10,stock=4,sold=6,revenue=120000)}
  r=estimate(p)
  self.assertEqual(r['preparation_cost'],112500)
  self.assertEqual(r['unsold_cost_included'],45000)
  self.assertEqual(r['contribution_before_overhead'],7500)
  self.assertIsNone(r['disposal_fee']);self.assertIsNone(r['operating_expenses']);self.assertIsNone(r['net_profit'])
  p['sku']['revenue']=90000
  self.assertEqual(estimate(p)['preparation_cost'],112500)
 def test_empty_preparation_cost_is_genuinely_zero(self):
  r=estimate({});self.assertEqual(r['preparation_cost'],0)
  self.assertEqual(r['status'],'ASSUMED_NOT_VERIFIED')
 def test_unit_rounding_to_vnd_is_half_up(self):
  r=estimate({'sku':dict(price=30,prepared=3,stock=2,revenue=25)})
  self.assertEqual(r['rows'][0]['unit_cost_assumed'],14)
  self.assertEqual(r['preparation_cost'],42)
  self.assertEqual(r['contribution_before_overhead'],-17)

if __name__=='__main__':unittest.main(verbosity=2)

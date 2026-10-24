import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unittest
from test_pos import fixtures,until,SKU
from pos_core import Session,quote_price
class NewMechanics(unittest.TestCase):
 def test_nonround_approval_receipt(self):
  m,c,s,h=fixtures();x=Session(m,c,s,h);until(x,'20:00');p=x.propose_price('M1_ONLY',SKU,approved_cash_price_vnd=27195);x.approve(p['id']);x.advance();self.assertEqual(x.states['M1_ONLY',SKU].pos[-1]['unit_price_vnd'],27195)
 def test_adaptive_batch_and_causality(self):
  m,c,s,h=fixtures(0);x=Session(m,c,s,h);until(x,'16:00');before=x.states['M2_ONLY',SKU].inventory;x.schedule_batch('M2_ONLY',SKU,8,'17:00');self.assertEqual(x.states['M2_ONLY',SKU].inventory,before);until(x,'17:00');self.assertEqual(x.states['M2_ONLY',SKU].inventory,before+8)
  with self.assertRaises(ValueError):x.schedule_batch('BASELINE',SKU,8,'18:00')
  with self.assertRaises(ValueError):x.schedule_batch('M2_ONLY',SKU,8,'17:15')
 def test_weekly_order_does_not_use_today(self):
  m,c,s,h=fixtures();x=Session(m,c,s,h);q=x.baseline_qty('BASELINE',SKU);x.hist['BASELINE',SKU].append(dict(h[-1],date=x.day,sold_qty=99999));self.assertEqual(q,x.baseline_qty('BASELINE',SKU))
 def test_no_double_count_waste(self):
  m,c,s,h=fixtures(0);s[SKU]['markdown_action_cost_vnd_assumed']=350;x=Session(m,c,s,h);until(x,'22:00')
  for r in x.observed_daily:self.assertEqual(r['contribution_vnd_assumed'],r['revenue_vnd']-r['production_cost_vnd_assumed']-r['disposal_cost_vnd_assumed']-r['markdown_operations_cost_vnd_assumed'])
if __name__=='__main__':unittest.main(verbosity=2)

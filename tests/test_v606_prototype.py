"""Public-only prototype integration and deterministic stress comparison."""
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.v606 import Engine,Simulator
from services.workflow import Workflow
from services.store import Store

class Prototype(unittest.TestCase):
 def test_model_workflow_and_background_sales(self):
  with tempfile.TemporaryDirectory() as temp:
   e=Engine();sim=Simulator(e);w=Workflow(e,sim,Store(str(Path(temp)/'test.sqlite3')))
   s=w.create();self.assertEqual(s['day'],'2022-07-01');self.assertEqual(s['prediction_origin'],'AI_M2')
   s=w.mutate(s['id'],s['revision'],'plan_approve');s=w.mutate(s['id'],s['revision'],'prepared')
   s=w.mutate(s['id'],s['revision'],'tick',{'target':600})
   self.assertGreater(sum(p['sold'] for p in s['products'].values()),0)
   w.assert_accounts(s)
 def test_same_stream_comparison_and_no_future_history(self):
  e=Engine();sim=Simulator(e);r=sim.comparison()
  self.assertEqual(r,sim.comparison());self.assertEqual(len(r['branches']),4)
  for b in r['branches']:
   self.assertEqual(b['sold']+b['lost'],b['eligible_purchase_requests'])
   self.assertLessEqual(b['eligible_purchase_requests'],r['potential_purchases'])
   self.assertEqual(b['prepared'],b['sold']+b['stock'])
  self.assertTrue(all(d<'2022-07-01' for d,s in sim.history_before('2022-07-01')))

if __name__=='__main__':unittest.main(verbosity=2)

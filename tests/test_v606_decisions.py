"""No-change pricing never asks approval; real changes keep the approval boundary."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.v606 import Engine,Simulator
from services.workflow import Workflow
from services.store import Store
from services.evaluation import reconcile

class Decisions(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.engine=Engine();self.sim=Simulator(self.engine)
  self.w=Workflow(self.engine,self.sim,Store(str(Path(self.temp.name)/'test.sqlite3')))
  self.s=self.w.create()
  for name in ('plan_approve','prepared'):self.s=self.w.mutate(self.s['id'],self.s['revision'],name)
 def tearDown(self):self.temp.cleanup()
 def test_hold_logs_without_stopping_or_approving(self):
  original=self.engine.price
  def hold(*args,**kwargs):
   row=original(*args,**kwargs)
   return {**row,'discount':row['previous'],'new_price':round(row['price']*(1-row['previous']/100))}
  with patch.object(self.engine,'price',side_effect=hold):
   s=self.w.mutate(self.s['id'],self.s['revision'],'tick',{'target':1170})
  self.assertEqual(s['phase'],'running');self.assertIsNone(s['pending'])
  self.assertEqual(s['decisions'][-1]['status'],'no_change');self.assertFalse(s['decisions'][-1]['requires_approval'])
  self.assertTrue(all(p['discount']==0 for p in s['products'].values()))
  with patch.object(self.engine,'price',side_effect=hold):
   s=self.w.mutate(s['id'],s['revision'],'tick',{'target':1200})
  self.assertEqual(s['minute'],1200);self.assertEqual(s['phase'],'running')
 def test_only_changed_sku_requires_approval_and_price_does_not_apply_early(self):
  original=self.engine.price;sku=next(iter(self.engine.master))
  def proposed(*args,**kwargs):
   row=original(*args,**kwargs)
   # Trusted positive evidence is a test-only fixture, absent from the live V606 dataset.
   if args[0]==sku:row={**row,'discount':20,'new_price':round(row['price']*.8),'economic_gate':{'status':'VERIFIED_POSITIVE_BENEFIT','evidence_id':'test-only-case'}}
   else:row={**row,'discount':row['previous'],'new_price':round(row['price']*(1-row['previous']/100))}
   return row
  with patch.object(self.engine,'price',side_effect=proposed):
   s=self.w.mutate(self.s['id'],self.s['revision'],'tick',{'target':1170})
  self.assertEqual(s['phase'],'price_pending');self.assertEqual(len(s['pending']['rows']),1)
  self.assertEqual(len(s['pending']['held_rows']),6);self.assertTrue(s['pending']['requires_approval'])
  self.assertTrue(all(p['discount']==0 for p in s['products'].values()))
  pid=s['pending']['id'];s=self.w.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':pid})
  self.assertEqual(s['products'][sku]['discount'],0)
  s=self.w.mutate(s['id'],s['revision'],'price_apply',{'proposal_id':pid})
  self.assertEqual(s['products'][sku]['discount'],20)
  self.assertTrue(all(p['discount']==0 for k,p in s['products'].items() if k!=sku));self.w.assert_accounts(s)
 def test_cost_assumed_and_reduced_stock_on_same_customer_stream(self):
  self.assertEqual(sum(not e['promo'] for e in self.sim.events('2022-07-01',42)),823)
  self.assertLess(sum(p['prepared'] for p in self.s['plan']),1244)
  r=reconcile({**self.s,'phase':'closed'})
  expected=sum(round(p['price']*.45)*p['prepared'] for p in self.s['products'].values())
  self.assertEqual(r['kpis']['production_cost_assumed'],expected)
  self.assertEqual(r['kpis']['contribution_before_overhead'],-expected)
  self.assertIsNone(r['financial_estimate']['net_profit'])

if __name__=='__main__':unittest.main(verbosity=2)

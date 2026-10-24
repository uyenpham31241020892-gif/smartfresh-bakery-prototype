"""Busy scenario service, live accounting and observed-only AI context tests."""
import sys
import tempfile
import unittest
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.v606 import Engine,Simulator,POLICY_VERSION
from services.store import Store
from services.workflow import Workflow
from services.realtime import Realtime
from services.assistant import Assistant

class Service(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.engine=Engine();cls.sim=Simulator(cls.engine)
 def test_stock_remaining_at_2130_and_reconciled_for_multiple_seeds(self):
  for seed in (0,1,42,606):
   with self.subTest(seed=seed),tempfile.TemporaryDirectory() as t:
    w=Workflow(self.engine,self.sim,Store(str(Path(t)/'test.sqlite3')));s=w.create(seed=seed)
    self.assertEqual(s['prediction_origin'],'AI_M2')
    for name in ('plan_approve','prepared'):s=w.mutate(s['id'],s['revision'],name)
    for target in (600,773,1170,1200,1230,1260,1290):
     s=w.mutate(s['id'],s['revision'],'tick',{'target':target})
     if target==600:self.assertGreater(sum(p['sold'] for p in s['products'].values()),0)
     if s['pending']:
      self.assertEqual(s['pending']['origin'],'AI_M1')
      pid=s['pending']['id']
      s=w.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':pid})
      s=w.mutate(s['id'],s['revision'],'price_apply',{'proposal_id':pid})
     w.assert_accounts(s)
    self.assertTrue(all(p['stock_at_2130']>0 and p.get('first_stockout_minute',1320)>=1290 for p in s['products'].values()))
    self.assertEqual(sum(p['lost'] for p in s['products'].values()),0)
 def test_clock_emits_incremental_transactions(self):
  with tempfile.TemporaryDirectory() as t:
   store=Store(str(Path(t)/'clock.sqlite3'));w=Workflow(self.engine,self.sim,store);s=w.create()
   for name in ('plan_approve','prepared'):s=w.mutate(s['id'],s['revision'],name)
   clock=Realtime(w,store);clock.configure(s['id'],True,1.)
   with store.connect() as db:base=db.execute('select last_wall from simulation_clocks where sid=?',(s['id'],)).fetchone()[0]
   clock.step(base+30);a=store.get(s['id']);clock.step(base+60);b=store.get(s['id'])
   self.assertGreater(b['minute'],a['minute']);self.assertGreater(len(b['ledger']),len(a['ledger']))
   w.assert_accounts(b)
 def test_supply_policy_never_reads_seeded_future(self):
  plans=self.engine.plan('2022-07-01',self.sim.seed,self.sim.calendar['2022-07-01'])
  for p in plans:
   self.assertLess(p['features']['history_through'],'2022-07-01')
   self.assertEqual(p['supply']['policy'],POLICY_VERSION)
   self.assertGreater(p['prepared'],p['forecast'])
  spec=self.engine.master['TP-DN-001'];old=spec['daily_capacity_units_assumed']
  try:
   spec['daily_capacity_units_assumed']='4';self.assertFalse(self.engine.supply('TP-DN-001',100000)['capacity_feasible'])
  finally:spec['daily_capacity_units_assumed']=old
 def test_copilot_reads_real_sales_and_model_but_not_hidden_lost_demand(self):
  with tempfile.TemporaryDirectory() as t:
   w=Workflow(self.engine,self.sim,Store(str(Path(t)/'ai.sqlite3')));s=w.create()
   for name in ('plan_approve','prepared'):s=w.mutate(s['id'],s['revision'],name)
   s=w.mutate(s['id'],s['revision'],'tick',{'target':600})
   sku=s['plan'][0]['sku'];ai=Assistant();captured=[]
   replies=[{'id':'one','output':[{'type':'function_call','name':'get_session_context','arguments':'{}','call_id':'one'}]},
    {'id':'two','output':[{'type':'function_call','name':'get_model_evidence','arguments':json.dumps({'sku':sku}),'call_id':'two'}]},
    {'id':'three','output':[{'type':'message','content':[{'type':'output_text','text':'Observed context read.'}]}]}]
   def request(payload):captured.append(json.loads(json.dumps(payload)));return replies[len(captured)-1]
   ai.request=request
   result=ai.chat('Explain model, sales and stock',s,lambda sku:{'m2':next(p for p in s['plan'] if p['sku']==sku)})
   self.assertEqual(result['tools_used'],['get_session_context','get_model_evidence'])
   tools=[json.loads(m['output']) for m in captured[-1]['input'] if m.get('type')=='function_call_output']
   context=tools[0]
   self.assertIn('observed_sales_metrics',context);self.assertIn('supply_plans',context)
   self.assertEqual(context['observed_sales_metrics'][sku]['sold_cumulative'],s['products'][sku]['sold'])
   self.assertNotIn('lost',context['observed_products'][sku]);self.assertNotIn('future_events',context)
   self.assertEqual(tools[1]['scenario_supply_derivation']['service_status'],'PLANNING_GOAL_NOT_GUARANTEE')

if __name__=='__main__':unittest.main(verbosity=2)

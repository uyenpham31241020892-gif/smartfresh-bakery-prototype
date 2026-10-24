"""Late-first prices, historical source isolation and explanations before approval."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.cautious_pricing import recommend
from services.clearance import SCENARIO
from services.v606 import Engine,Simulator,TRAINED_CLEARANCE_VERSION
from services.workflow import Workflow
from services.store import Store
from services.assistant import Assistant
from services.explanations import Explanations
from services.proposal_narrative import prepare
from services.baseline_history import report,bundle
from services.business_reports import analysis_context


class LateFirst(unittest.TestCase):
 def quote(self,minute=1170,stock=80,prepared=140,remaining=30,service=20,previous=0,sold=60,past=0,s30=3,s60=8):
  return recommend(dict(price=25000,minute=minute,stock=stock,previous=previous,sales30=s30,sales60=s60),prepared,remaining,service,
   scenario=SCENARIO,history=dict(sold_today=sold,past_discount_value=past))

 def test_no_routine_early_cuts_but_exception_can_offer_small_cut(self):
  for minute in [1170,1200,1230]:self.assertEqual(self.quote(minute=minute)['discount'],0)
  exceptional=self.quote(stock=150,prepared=200,remaining=5,service=4,sold=50,s30=0,s60=0)
  self.assertEqual(exceptional['discount'],10)
  self.assertEqual(exceptional['reason'],'MARKDOWN_EXCEPTIONAL_EARLY_SURPLUS')

 def test_budget_counts_past_concessions_and_does_not_compound_or_force_deep_cut(self):
  q=self.quote(minute=1260,remaining=10,service=5,sold=100)
  self.assertEqual(q['discount'],10)
  self.assertLessEqual(q['economic_gate']['total_concession_exposure'],q['economic_gate']['daily_concession_budget'])
  self.assertEqual(self.quote(minute=1260,remaining=10,service=5,sold=100,past=1000000)['discount'],0)
  self.assertEqual(self.quote(minute=1290,previous=30,remaining=10,service=0,sold=100)['discount'],30)
  self.assertEqual(self.quote(minute=1290,stock=10,remaining=8,service=0,sold=100)['discount'],0)

 def test_history_changes_projections_and_future_baseline_is_not_reported(self):
  r=report('2022-05-01',180)
  self.assertTrue(all(d['day']<'2022-05-01' for d in r['rows']))
  full=report('2022-07-03',180)
  self.assertEqual(full['closed_days'],171);self.assertEqual(full['summary']['revenue'],782772100)
  self.assertEqual(sum(r['metrics']['revenue'] for r in full['rows'] if r['metrics']),782772100)
  c=analysis_context(full,'baseline');self.assertEqual(c['selected_day'],'2022-06-30')
  self.assertIn('proxy',c['qualification'])
  row=dict(price=25000,minute=1260,stock=50,previous=0,sales30=2,sales60=4)
  old=recommend(row,140,10,5,scenario=SCENARIO,history=dict(sold_today=90,own_remaining_projection=48))
  self.assertEqual(old['discount'],0)

 def test_upgrade_cancels_unapplied_old_quote_without_changing_receipts_or_market(self):
  with tempfile.TemporaryDirectory() as t:
   old=Engine(version=TRAINED_CLEARANCE_VERSION);new=Engine();sim=Simulator(old);store=Store(Path(t)/'upgrade.db')
   w=Workflow(old,sim,store);s=w.create()
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   s=w.mutate(s['id'],s['revision'],'tick',{'target':1170});self.assertEqual(s['phase'],'price_pending')
   before=copy.deepcopy(s);w.active_engine=lambda:new;w.version_engine=lambda v:new if v==new.version else old
   s=w.mutate(s['id'],s['revision'],'adopt_price_policy')
   self.assertEqual(s['phase'],'running');self.assertIsNone(s['pending'])
   for key in ['products','ledger','weather','simulator_hash','simulator_version','model_hashes']:self.assertEqual(s[key],before[key])
   self.assertEqual(s['model_version'],new.version)

 def test_closed_parent_history_is_available_inside_the_tick_transaction(self):
  with tempfile.TemporaryDirectory() as t:
   e=Engine();w=Workflow(e,Simulator(e),Store(Path(t)/'history.db'));s=w.create()
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   while s['minute']<1320:
    s=w.mutate(s['id'],s['revision'],'tick',{'target':1320})
    if s['pending']:
     pid=s['pending']['id']
     for a in ['price_approve','price_apply']:s=w.mutate(s['id'],s['revision'],a,{'proposal_id':pid})
   s=w.mutate(s['id'],s['revision'],'close');s=w.next_day(s['id'])
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   s=w.mutate(s['id'],s['revision'],'tick',{'target':1170})
   p=s['pending'] or s['decisions'][-1]
   self.assertEqual(p['origin'],'AI_M1');self.assertFalse(w.safety.incidents(s['id']))
   for r in p['rows']+p.get('held_rows',[]):
    h=r['pricing_policy']['history'];self.assertEqual(h['own_history_days'],1)
    self.assertEqual(h['comparisons']['yesterday']['source'],'OWN_CLOSED_BRANCH')

 def test_server_prefetch_produces_immutable_explanation_before_model_or_approval(self):
  with tempfile.TemporaryDirectory() as t:
   e=Engine();w=Workflow(e,Simulator(e),Store(Path(t)/'explain.db'));s=w.create()
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   for target in [1170,1200,1230,1260]:s=w.mutate(s['id'],s['revision'],'tick',{'target':target})
   self.assertEqual(s['phase'],'price_pending');release=Event();calls=[];service=Explanations();client=Assistant()
   def evidence(snapshot,sku):
    calls.append((snapshot['minute'],sku));p=snapshot['pending'];return dict(m2=next(r for r in snapshot['plan'] if r['sku']==sku),m1=next(r for r in p['rows']+p['held_rows'] if r['sku']==sku))
   def request(payload):
    release.wait(4);self.assertFalse(payload['tools']);self.assertEqual(payload['tool_choice'],'none')
    context=json.loads(payload['input'][0]['content']);answer=json.dumps(dict(priorities=list(context['facts'])[:3],action=context['actions'][0]))
    return dict(id='grounded',output=[dict(type='message',content=[dict(type='output_text',text=answer)])])
   client.request=request
   try:
    result=service.get(s,'m1',client,evidence)
    self.assertEqual(result['status'],'running');self.assertTrue(result['evidence_ready']);self.assertIn('trước quyết định duyệt',result['answer'])
    self.assertEqual(len(calls),7);s['minute']=1290;release.set();service.pool.shutdown(wait=True)
    result=service.get(s,'m1',client,evidence)
    self.assertEqual(result['ai_status'],'ready');self.assertIn('21:00',result['answer']);self.assertNotIn('21:30, đọc',result['answer'])
    self.assertEqual(len(calls),7)
   finally:release.set();service.pool.shutdown(wait=True);service.report_pool.shutdown(wait=True)


if __name__=='__main__':unittest.main(verbosity=2)

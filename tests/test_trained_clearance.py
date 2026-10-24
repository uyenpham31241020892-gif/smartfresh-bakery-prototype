"""Risk forecasting, conditional markdown, sensitivity and frozen-day boundaries."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.clearance import recommend,SCENARIO,DIRECTORY,POLICY
from services.v606 import Engine,Simulator,BENEFIT_GUARD_VERSION,TRAINED_CLEARANCE_VERSION
from services.workflow import Workflow
from services.store import Store
from services.safety import GuardError


class Clearance(unittest.TestCase):
 def quote(self,**changes):
  row=dict(price=25000,minute=1170,stock=100,previous=0,sales30=3,sales60=8)
  row.update(changes)
  return recommend(row,140,40,28,scenario=SCENARIO)

 def test_not_early_not_forced_and_service_can_hold(self):
  self.assertEqual(self.quote(minute=1169)['discount'],0)
  self.assertEqual(self.quote(stock=42)['discount'],0)
  self.assertEqual(self.quote(stock=60,sales30=25,sales60=50)['discount'],0)
  self.assertEqual(self.quote(stock=0)['discount'],0)
  self.assertEqual(self.quote()['discount'],20)
  r=self.quote();self.assertIsNone(r['economic_gate']['verified_extra_units'])
  self.assertLess(r['economic_gate']['zero_response_revenue_change'],0)

 def test_tiers_depend_on_inventory_and_late_clearance_does_not_need_fake_profit(self):
  row=dict(price=25000,minute=1170,stock=64,previous=0,sales30=3,sales60=8)
  thin=recommend(row,140,50,39,scenario=SCENARIO)
  self.assertEqual(thin['discount'],10)
  self.assertEqual(self.quote()['discount'],20)
  late=self.quote(minute=1260,previous=20)
  self.assertEqual(late['discount'],30)
  self.assertGreaterEqual(late['economic_gate']['assumed_net_revenue_change'],0)
  self.assertEqual(self.quote(minute=1290,previous=40)['discount'],40)

 def test_training_and_hashes_are_bound_and_forecast_beats_pace_on_validation(self):
  r=json.loads((DIRECTORY/'training_report.json').read_text())
  self.assertEqual((r['fit_rows'],r['validation_rows']),(3885,2100))
  self.assertFalse(r['test_access']);self.assertFalse(r['causal_price_response_learned'])
  self.assertEqual(r['trained_until'],'2022-04-30')
  for h in r['horizons'].values():self.assertLess(h['validation_censored_loss'],h['pace_baseline_censored_loss'])
  e=Engine();self.assertTrue(e.require_integrity())
  self.assertEqual(len([k for k in e.manifest['native_model_hashes'] if k.startswith('remaining/')]),3)
  self.assertNotIn('logged_action_discount_pct',r['columns'])
  self.assertNotIn('sold_next30_observed',r['columns'])

 def test_old_stream_and_active_day_survive_new_simulator(self):
  old=Engine(version=BENEFIT_GUARD_VERSION);oldsim=Simulator(old);new=Engine();sim=Simulator(new)
  organic=oldsim.events('2022-07-01',42)
  self.assertEqual(organic,sim.events('2022-07-01',42,version=oldsim.version))
  events=sim.events('2022-07-01',42)
  self.assertEqual(organic,[e for e in events if not e['promo']])
  self.assertTrue(all(e['minute']>=1170 for e in events if e['promo']))
  with tempfile.TemporaryDirectory() as t:
   store=Store(Path(t)/'old.db');w=Workflow(old,oldsim,store);s=w.create()
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   upgraded=Workflow(new,sim,store);upgraded.version_engine=lambda v:old if v==old.version else new
   s=upgraded.mutate(s['id'],s['revision'],'tick',{'target':1170})
   self.assertEqual(s['model_version'],old.version);self.assertIsNone(s['pending'])
   fork=upgraded.fork_simulation(s['id'])
   self.assertEqual(fork['simulator_version'],oldsim.version)
   self.assertNotIn('price_response_scenario',fork['weather'])

 def test_assumed_benefit_cannot_unlock_live_or_old_market_or_unscored_override(self):
  r=self.quote();r['sku']='A'
  s=dict(mode='simulation',simulator_version=SCENARIO,pending=dict(origin='AI_M1'),products={'A':dict(discount=0)})
  Workflow.require_price_benefit(s,r,r['discount'])
  for changes,tier in [({'mode':'live'},20),({'simulator_version':'old'},20),({},30)]:
   with self.assertRaises(GuardError):Workflow.require_price_benefit({**s,**changes},r,tier)
  hold=recommend(dict(price=25000,minute=1290,stock=100,previous=0,sales30=1,sales60=2),140,5,0,scenario=None)
  self.assertEqual(hold['discount'],0)

 def test_actual_trained_quote_requires_approval_and_changes_only_future_receipts(self):
  with tempfile.TemporaryDirectory() as t:
   e=Engine(version=TRAINED_CLEARANCE_VERSION);sim=Simulator(e);w=Workflow(e,sim,Store(Path(t)/'new.db'));s=w.create()
   for a in ['plan_approve','prepared']:s=w.mutate(s['id'],s['revision'],a)
   s=w.mutate(s['id'],s['revision'],'tick',{'target':1170})
   self.assertEqual(s['phase'],'price_pending');self.assertTrue(s['pending']['held_rows'])
   self.assertTrue(all(p['discount']==0 for p in s['products'].values()))
   before=copy.deepcopy(s['ledger']);pid=s['pending']['id']
   for a in ['price_approve','price_apply']:s=w.mutate(s['id'],s['revision'],a,{'proposal_id':pid})
   self.assertEqual(s['ledger'],before)
   self.assertTrue(any(p['discount']>0 for p in s['products'].values()))
   s=w.mutate(s['id'],s['revision'],'tick',{'target':1200});w.assert_accounts(s)
   self.assertTrue(any(t['discount']>0 for t in s['ledger']))


if __name__=='__main__':unittest.main(verbosity=2)

"""As-of adaptive planning, scale correctness and daily closed-loop behavior."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.v606 import Engine,Simulator,LEGACY_VERSION,CURRENT_VERSION
from services.workflow import Workflow
from services.store import Store
from services.planning import adaptive_supply


class Planning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=Engine();cls.sim=Simulator(cls.engine)

    def inputs(self):
        sku='TP-DN-001';day='2022-07-02'
        visible=dict(self.sim.seed);visible[('2022-07-01',sku)]=100
        outcome=dict(date='2022-07-01',sku_code=sku,prepared_qty=140,stockout=0,observation_scale=4,sold_to_2130=92)
        outcomes={('2022-07-01',sku):outcome}
        f=self.engine.features(day,sku,visible,self.sim.calendar[day],outcomes)
        obs=[dict(date='2022-07-01',sku_code=sku,sold_qty=100,prepared_qty=140,censored_demand_flag=0,sold_to_2130=92)]
        h=self.engine.history(day,sku,visible,outcomes)
        return sku,f,h,obs

    def test_busy_local_history_normalizes_once_seed_stays_unchanged(self):
        sku,f,h,obs=self.inputs()
        self.assertEqual(f['sold_calendar_lag1'],25)
        self.assertEqual(h[-1]['sold_qty'],100)
        seed=[r for r in self.engine.seed_rows if r['sku_code']==sku and r['date']=='2022-06-30'][0]
        visible=dict(self.sim.seed)
        self.assertEqual(self.engine.history('2022-07-01',sku,visible,normalize=True)[-1]['sold_qty'],seed['sold_qty'])

    def test_observed_sales_and_model_change_supply_without_clip(self):
        sku,f,h,obs=self.inputs();f['ood_flag']=0
        args=(sku,30,f,h,obs,self.engine.master[sku])
        a=adaptive_supply(*args)
        changed=copy.deepcopy(obs);changed[0]['sold_qty']=160;changed[0]['prepared_qty']=200
        b=adaptive_supply(sku,30,f,h,changed,self.engine.master[sku])
        c=adaptive_supply(sku,45,f,h,obs,self.engine.master[sku])
        self.assertGreater(b['quantity'],a['quantity'])
        self.assertGreater(c['quantity'],a['quantity'])
        self.assertEqual(a['observation_days'],1)
        self.assertEqual(a['share_source'],'OWN_COMPLETED_POS')

    def test_ood_is_a_real_observed_fallback_not_just_a_label(self):
        sku,f,h,obs=self.inputs();f.update(ood_flag=1,ood_reasons='WEATHER_HISTORY_MISSING')
        a=adaptive_supply(sku,30,f,h,obs,self.engine.master[sku])
        b=adaptive_supply(sku,30000,f,h,obs,self.engine.master[sku])
        self.assertEqual(a['quantity'],b['quantity'])
        self.assertFalse(a['model_used']);self.assertEqual(a['model_weight'],0)

    def test_censored_sales_are_lower_bounds_and_capacity_can_fail(self):
        sku,f,h,obs=self.inputs();obs[0].update(censored_demand_flag=1,sold_qty=140)
        a=adaptive_supply(sku,30,f,h,obs,self.engine.master[sku])
        self.assertGreaterEqual(a['expected_requests_assumed'],147)
        spec={**self.engine.master[sku],'daily_capacity_units_assumed':4}
        b=adaptive_supply(sku,30,f,h,obs,spec)
        self.assertFalse(b['capacity_feasible']);self.assertEqual(b['quantity'],16)
        self.assertLess(b['stock_at_2130_lower_scenario'],0)

    def test_future_rejected_and_hidden_values_do_not_affect_plan(self):
        sku,f,h,obs=self.inputs()
        a=adaptive_supply(sku,30,f,h,obs,self.engine.master[sku])
        hidden=[{**r,'hidden_demand':99999,'lost':99999} for r in obs]
        self.assertEqual(a,adaptive_supply(sku,30,f,h,hidden,self.engine.master[sku]))
        with self.assertRaises(ValueError):adaptive_supply(sku,30,f,h,[{**obs[0],'date':f['date']}],self.engine.master[sku])
        with self.assertRaises(ValueError):self.engine.features('2022-07-01',sku,{('2022-07-01',sku):10},self.sim.calendar['2022-07-01'])
        with self.assertRaises(ValueError):self.engine.features('2022-07-01',sku,self.sim.seed,{**self.sim.calendar['2022-07-01'],'weather_reference_date':'2022-07-01'})

    def test_weather_only_exact_previous_date_and_missing_not_zero(self):
        w=self.sim.calendar['2022-07-02']
        self.assertEqual(w['weather_reference_date'],'2022-07-01')
        self.assertAlmostEqual(w['prior_day_rain_mm'],5.8)
        self.assertFalse(w['weather_provenance']['vintage_verified'])
        sku='TP-DN-001';missing={**self.sim.calendar['2022-07-01'],'prior_day_rain_mm':None,'prior_day_temp_c':None}
        plan=self.engine.plan('2022-07-01',self.sim.seed,missing)
        self.assertTrue(all(not p['supply']['model_used'] for p in plan))

    def test_legacy_plan_and_market_are_preserved(self):
        old=Engine(version=LEGACY_VERSION);sim=Simulator(old)
        plan=old.plan('2022-07-01',sim.seed,sim.calendar['2022-07-01'])
        self.assertEqual(sum(p['prepared'] for p in plan),980)
        self.assertEqual(self.sim.events('2022-07-01',42,version=sim.version),sim.events('2022-07-01',42))

    def test_training_review_retains_original_when_challenger_undershoots(self):
        review=self.engine.training_review
        self.assertEqual(review['configurations'],64)
        self.assertFalse(review['promoted'])
        self.assertFalse(review['day']['promotion_eligible'])
        self.assertGreater(review['day']['selected']['metrics']['censored_underforecast_rate'],review['day']['original_reproduced']['censored_underforecast_rate'])

    def test_four_day_loop_updates_features_preparation_and_2130_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'loop.sqlite3');w=Workflow(self.engine,self.sim,store)
            s=w.create();quantities=[]
            for i in range(4):
                self.assertEqual(s['day_context']['past_closed_days'],i)
                quantities.append([p['prepared'] for p in s['plan']])
                self.assertTrue(all(p['supply']['observation_days']==i for p in s['plan']))
                for action in ('plan_approve','prepared'):s=w.mutate(s['id'],s['revision'],action)
                while s['minute']<1320:
                    s=w.mutate(s['id'],s['revision'],'tick',{'target':1320})
                    if s['pending']:
                        payload={'proposal_id':s['pending']['id']}
                        for action in ('price_approve','price_apply'):s=w.mutate(s['id'],s['revision'],action,payload)
                self.assertTrue(all('stock_at_2130' in p for p in s['products'].values()))
                w.assert_accounts(s);s=w.mutate(s['id'],s['revision'],'close')
                if i<3:s=w.next_day(s['id'])
            self.assertGreater(len({tuple(q) for q in quantities}),1)
            print('4-day development preparation:',[sum(q) for q in quantities])


if __name__=='__main__':unittest.main(verbosity=2)

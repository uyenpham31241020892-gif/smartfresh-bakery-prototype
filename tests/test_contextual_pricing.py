"""Early markdown is conditional, explainable and never an automatic price change."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.pricing import markdown
from services.v606 import Engine,Simulator,ADAPTIVE_M2_VERSION


class Pricing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=Engine();cls.sim=Simulator(cls.engine)
        cls.spec=cls.engine.master['TP-DN-002']

    def quote(self,**kwargs):
        state=dict(minute=1170,stock=80,prepared=140,previous=0,sales30=3,sales60=8,model_next30=4,model_action='HOLD')
        state.update(kwargs)
        return markdown(self.spec,**state)

    def test_1930_can_mark_down_even_when_logged_classifier_holds(self):
        r=self.quote()
        self.assertGreater(r['discount'],0)
        self.assertLess(r['new_price'],25000)
        self.assertEqual(r['pricing_policy']['model_logged_action'],'HOLD')
        self.assertEqual(r['pricing_policy']['origin'],'FROZEN_M1_FORECAST_PLUS_DECLARED_OBSERVED_SURPLUS_RULE')

    def test_before_1930_cannot_mark_down(self):
        r=self.quote(minute=1169,stock=200,prepared=220)
        self.assertEqual(r['discount'],0)

    def test_fast_selling_and_stock_for_2130_keep_price(self):
        r=self.quote(sales30=20,sales60=40,model_next30=20)
        self.assertEqual(r['new_price'],25000)
        self.assertEqual(r['reason'],'HOLD_PROTECT_STOCK_TO_2130')
        self.assertEqual(self.quote(stock=0)['reason'],'HOLD_SOLD_OUT')

    def test_same_clock_different_stock_and_pace_give_different_actions(self):
        moderate=self.quote()
        high=self.quote(stock=200,prepared=220,sales30=1,sales60=2,model_next30=1)
        fast=self.quote(sales30=20,sales60=40,model_next30=20)
        self.assertGreater(high['discount'],moderate['discount'])
        self.assertGreater(moderate['discount'],fast['discount'])

    def test_no_price_increase_or_repeated_discount_compounding(self):
        r=self.quote(previous=15,sales30=20,sales60=40,model_next30=20)
        self.assertEqual(r['new_price'],21250)
        self.assertEqual(r['discount'],15)
        for minute in (1170,1200,1230,1260,1290):
            self.assertLessEqual(self.quote(minute=minute,previous=20)['new_price'],20000)

    def test_known_reference_cash_floor_and_unknown_sku_can_participate(self):
        r=markdown(self.engine.master['TP-CR-001'],1310,100,140,0,0,0,1,'HOLD')
        self.assertEqual(r['new_price'],20000)
        r=markdown(self.engine.master['TP-DN-001'],1170,100,140,0,1,2,1,'HOLD')
        self.assertGreater(r['discount'],0)

    def test_invalid_prediction_rejected(self):
        with self.assertRaises(ValueError):self.quote(model_next30=math.nan)

    def test_customer_stream_changes_by_day_and_stays_reproducible(self):
        a=self.sim.events('2022-07-01',42);b=self.sim.events('2022-07-02',42)
        self.assertEqual(a,self.sim.events('2022-07-01',42))
        self.assertNotEqual(a,b)
        self.assertNotEqual(sum(e['sku']=='TP-DN-001' for e in a),sum(e['sku']=='TP-DN-001' for e in b))

    def test_frozen_models_used_and_v4_remains_pinned_to_old_price_rule(self):
        w=self.sim.calendar['2022-07-01']
        from services.v606 import BENEFIT_GUARD_VERSION
        r=Engine(version=BENEFIT_GUARD_VERSION).price('TP-DN-002',0,100,140,0,1,2,30,w,1170)
        self.assertIn('model_next30_under_logged_action',r['pricing_policy'])
        self.assertEqual(r['discount'],0)
        self.assertEqual(r['economic_gate']['status'],'HOLD_NO_VERIFIED_INCREMENTAL_BENEFIT')
        old=Engine(version=ADAPTIVE_M2_VERSION)
        self.assertEqual(old.price('TP-DN-002',0,100,140,0,1,2,30,w,1170)['discount'],0)


if __name__=='__main__':unittest.main(verbosity=2)

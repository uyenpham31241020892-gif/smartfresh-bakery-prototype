"""Synthetic public contexts only; never open the private test market."""
import importlib.util
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'v606/03_TEST_POS_RUNTIME/code'))
sys.path.insert(0, str(ROOT / 'v606'))
import model_adapter as adapter
from features_asof import m2_features


def fixture():
    sku = 'TP-DN-002'
    h = [dict(date=str(date(2022, 6, 15)-timedelta(days=i)), sku_code=sku,
              sold_qty=20, prepared_qty=24, censored_demand_flag=0)
         for i in range(28, 0, -1)]
    ctx = dict(date='2022-06-15', sku_code=sku, completed_branch_history=h,
               decision_at='2022-06-15T06:00:00+07:00', is_public_holiday=0,
               is_tet_run_up=0, is_weekend=0, sku_master=adapter.MASTER[sku],
               weather_prior_day=dict(rain_mm=0, temp_c=28))
    return m2_features(ctx), h


class AdapterSafety(unittest.TestCase):
    def test_real_frozen_model_inference_and_capacity(self):
        f, h = fixture()
        plan = adapter.prepare(f, h)
        self.assertGreater(plan['initial_qty'], 0)
        self.assertLessEqual(plan['initial_qty'], 80)
        self.assertEqual(plan['initial_qty'] % 4, 0)

    def test_future_or_other_sku_history_rejected(self):
        f, h = fixture()
        for change in ({'date': f['date']}, {'sku_code': 'TP-RV-001'}):
            with self.assertRaises(ValueError):
                adapter.prepare(f, h + [{**h[-1], **change}])
        f['weather_reference_date'] = f['date']
        with self.assertRaises(ValueError):
            adapter.prepare(f, h)

    def test_hidden_and_label_columns_never_enter_X(self):
        f, _ = fixture()
        f.update(lost_sales=999, served_sales_lower_bound=999, logged_action_discount_pct=50)
        x = adapter.frame(f, adapter.CONTRACT['m2_predictive_columns'])
        self.assertEqual(list(x.columns), adapter.CONTRACT['m2_predictive_columns'])
        self.assertNotIn('lost_sales', x.columns)

    def test_ood_uses_declared_fallback(self):
        f, h = fixture()
        f['ood_flag'] = 1
        plan = adapter.prepare(f, h)
        self.assertEqual(plan['initial_qty'], 24)
        self.assertIn('FALLBACK', plan['policy_status'])

    def test_m1_hold_and_never_raise_existing_price(self):
        f = dict(sku_code='TP-DN-002', time='19:30', prepared_qty=24,
                 inventory_at_decision=12, sold_last_30min=2, sold_last_60min=4,
                 shelf_inventory=12, backroom_inventory=0, previous_discount_pct=0,
                 baseline_announced_2100_pct=None)
        state = dict(model_features=f, price_context=dict(current_unit_price_vnd=25000))
        self.assertEqual(adapter.markdown(state, '2022-06-15T19:30:00+07:00'),
                         {'approved_cash_price_vnd': 25000})
        f['time'] = '21:30'
        state['price_context']['current_unit_price_vnd'] = 19000
        self.assertLessEqual(adapter.markdown(state, '2022-06-15T21:30:00+07:00')['approved_cash_price_vnd'], 19000)


if __name__ == '__main__':
    unittest.main(verbosity=2)

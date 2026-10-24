"""Historical reporting must not inflate reruns or invent missing days."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.store import Store
from services.business_reports import report, change


class Reports(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'report.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def save(self,sid,day,sold=10,prepared=20,phase='closed',**extra):
        state=dict(id=sid,day=day,revision=1,phase=phase,mode='simulation',seed=42,
                   model_version='v606',simulator_version='busy4',simulator_hash='market',
                   products={'A':dict(price=10000,prepared=prepared,sold=sold,stock=prepared-sold,revenue=sold*10000)},
                   ledger=[dict(sku='A',qty=sold,unit_price=10000,paid=sold*10000,discount=0)] if sold else [])
        state.update(extra)
        with self.store.connect() as db:
            db.execute('INSERT INTO sessions(id,state) VALUES (?,?)',(sid,json.dumps(state)))
        return state

    def test_exact_day_week_month_and_percent(self):
        self.save('day','2024-03-30',sold=10)
        self.save('week','2024-03-24',sold=8)
        self.save('month','2024-02-29',sold=5)
        self.save('current','2024-03-31',sold=12)
        r=report(self.store,'current',7)
        self.assertEqual(r['comparisons']['day']['changes']['sold']['percent'],20)
        self.assertEqual(r['comparisons']['week']['changes']['sold']['percent'],50)
        self.assertEqual(r['comparisons']['month']['changes']['sold']['percent'],140)
        self.assertEqual(r['comparisons']['month']['day'],'2024-02-29')
        self.assertEqual(r['comparisons']['day']['changes']['stock']['percent'],-20)
        self.assertEqual(len(r['rows']),7)

    def test_reruns_not_summed_selected_session_is_respected_and_scopes_isolated(self):
        self.save('first','2024-07-01',sold=5)
        self.save('latest','2024-07-01',sold=8)
        self.save('other_seed','2024-07-01',sold=19,seed=7)
        self.save('live','2024-07-01',sold=19,mode='live')
        self.save('old','2024-07-01',sold=19,model_version='old')
        self.save('other_market','2024-07-01',sold=19,simulator_hash='different')
        self.save('current','2024-07-02',sold=10)
        self.save('rerun_current','2024-07-02',sold=18)
        r=report(self.store,'current')
        self.assertEqual(r['rows'][-2]['metrics']['sold'],8)
        self.assertEqual(r['rows'][-1]['metrics']['sold'],10)
        self.assertEqual(r['comparisons']['day']['changes']['sold']['percent'],25)

    def test_gaps_are_unknown_not_zero_and_running_day_has_no_percent(self):
        self.save('current','2024-07-03',phase='running')
        r=report(self.store,'current')
        self.assertEqual(r['rows'][-2]['status'],'missing')
        self.assertIsNone(r['rows'][-2]['metrics'])
        self.assertEqual(r['rows'][-1]['status'],'provisional')
        self.assertIsNone(r['current'])
        self.assertEqual(r['selected_metrics']['sold'],10)
        self.assertIsNone(r['comparisons']['day']['changes']['sold']['percent'])

    def test_zero_baseline_and_negative_contribution(self):
        self.assertEqual(change(10,0),dict(value=10,percent=None,reason='zero_baseline'))
        self.assertEqual(change(0,0)['reason'],'zero_baseline')
        self.assertEqual(change(-50,-100)['percent'],50)
        self.save('zero','2024-07-01',sold=0)
        self.save('current','2024-07-02',sold=10)
        self.assertEqual(report(self.store,'current')['comparisons']['day']['changes']['revenue']['reason'],'zero_baseline')

    def test_invalid_latest_day_excluded_and_no_fallback_to_old_rerun(self):
        self.save('old_valid','2024-07-01',sold=5)
        bad=self.save('bad','2024-07-01',sold=10)
        bad['products']['A']['stock']=999
        with self.store.connect() as db:db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(bad),'bad'))
        self.save('current','2024-07-02')
        r=report(self.store,'current')
        self.assertEqual(r['excluded_invalid'],1)
        self.assertIsNone(r['comparisons']['day']['previous'])
        self.assertEqual(report(self.store,'bad')['current_status'],'invalid')

    def test_history_not_limited_to_session_menu_30_entries(self):
        self.save('month','2024-06-01',sold=5)
        for i in range(40):self.save('rerun'+str(i),'2024-06-30',sold=8)
        self.save('current','2024-07-01')
        self.assertEqual(report(self.store,'current')['comparisons']['month']['previous']['sold'],5)
        with self.assertRaises(ValueError):report(self.store,'current',365)

    def test_report_does_not_mutate_sales_or_feature_inputs(self):
        original=self.save('current','2024-07-01',input_history=[{'date':'2024-06-30','sold':7}])
        report(self.store,'current')
        self.assertEqual(self.store.get('current'),original)

    def test_same_weights_and_market_keep_history_across_policy_change(self):
        self.save('old','2024-07-01',sold=5,model_version='policy-v3',model_hashes={'m2':'frozen'})
        self.save('new','2024-07-02',sold=10,model_version='policy-v4',model_hashes={'m2':'frozen'})
        r=report(self.store,'new')
        self.assertEqual(r['comparisons']['day']['changes']['sold']['percent'],100)
        self.assertEqual(r['rows'][-2]['model_version'],'policy-v3')


if __name__=='__main__':unittest.main(verbosity=2)

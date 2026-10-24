"""Weighted realized prices, exact price/volume bridge and grounded report AI."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.business_reports import report,analysis_context,totals,revenue_bridge
from services.store import Store
from services.assistant import Assistant


def state():
    return dict(id='report',day='2022-07-02',minute=1320,revision=5,phase='closed',mode='simulation',seed=42,
        model_version='test',simulator_version='test',simulator_hash='test',weather={},source='unit fixture',plan=[],decisions=[],pending=None,
        products={'A':dict(name='A cake',price=100,prepared=10,sold=5,stock=5,revenue=440,discount=20,lost=987654321),
                  'B':dict(name='B cake',price=200,prepared=4,sold=2,stock=2,revenue=400,discount=0,lost=987654321)},
        ledger=[dict(sku='A',minute=500,qty=2,unit_price=100,paid=200,discount=0),
                dict(sku='A',minute=1120,qty=3,unit_price=80,paid=240,discount=20),
                dict(sku='B',minute=1100,qty=2,unit_price=200,paid=400,discount=0)])


class Insights(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'r.sqlite3');self.s=state()
        with self.store.connect() as db:db.execute('INSERT INTO sessions(id,state) VALUES (?,?)',(self.s['id'],json.dumps(self.s)))
    def tearDown(self):self.temp.cleanup()

    def test_weighted_prices_discounts_and_cost_include_unsold_once(self):
        r=report(self.store,'report');m=r['selected_metrics']
        self.assertEqual(m['revenue'],840);self.assertEqual(m['sold'],7)
        self.assertEqual(m['average_price'],120);self.assertEqual(m['list_value'],900)
        self.assertEqual(m['discount_value'],60);self.assertEqual(m['discounted_units'],3)
        self.assertAlmostEqual(m['weighted_discount_pct'],100*60/900)
        self.assertEqual(m['production_cost_assumed'],810);self.assertEqual(m['contribution_before_overhead'],30)
        self.assertEqual(r['products'][0]['average_price'],88)
        self.assertEqual(next(h for h in r['hourly'] if h['minute']==1080)['average_price'],128)
        self.assertIsNone(next(h for h in r['hourly'] if h['minute']==540)['average_price'])

    def test_no_sale_is_unknown_average_price_not_zero(self):
        s=state();s['ledger']=[]
        for p in s['products'].values():p.update(sold=0,stock=p['prepared'],revenue=0)
        m=totals(s)
        self.assertIsNone(m['average_price']);self.assertIsNone(m['weighted_discount_pct'])
        json.dumps(m,allow_nan=False)

    def test_price_volume_bridge_is_exact_identity(self):
        a=dict(revenue=840,sold=7,average_price=120);b=dict(revenue=600,sold=6,average_price=100)
        bridge=revenue_bridge(a,b)
        self.assertEqual(bridge['volume_component'],100)
        self.assertEqual(bridge['average_price_and_mix_component'],140)
        self.assertEqual(bridge['revenue_change'],240)
        fractional=revenue_bridge(dict(revenue=303,sold=3,average_price=101),dict(revenue=201,sold=2,average_price=100.5))
        self.assertEqual(fractional['volume_component']+fractional['average_price_and_mix_component'],102)

    def test_sku_scoped_ai_does_not_read_other_product_totals_or_hidden_demand(self):
        c=analysis_context(report(self.store,'report'),'products','A')
        self.assertEqual(c['selected']['revenue'],440)
        self.assertEqual([p['sku'] for p in c['selected_products']],['A'])
        self.assertNotIn('B cake',json.dumps(c));self.assertNotIn('987654321',json.dumps(c))

    def test_ai_must_read_report_tool_and_receives_only_observed_context(self):
        c=analysis_context(report(self.store,'report'),'prices')
        client=Assistant();calls=[]
        from services.report_narrative import commentary_options
        narrative=json.dumps(dict(insights=[dict(fact_key='revenue',commentary=commentary_options(c)['revenue'][0])],actions=['HOLD_PRICE']))
        responses=[dict(id='one',output=[dict(type='function_call',name='get_business_report',arguments='{}',call_id='r')]),
                   dict(id='two',output=[dict(type='message',content=[dict(type='output_text',text=narrative)])])]
        def request(payload):calls.append(copy.deepcopy(payload));return responses[len(calls)-1]
        client.request=request
        answer=client.chat('Analyze report',self.s,lambda sku:{},c)
        self.assertIn('get_business_report',answer['tools_used'])
        self.assertNotIn('987654321',json.dumps(calls))
        self.assertEqual(json.loads(next(m['output'] for m in calls[-1]['input'] if m.get('type')=='function_call_output'))['selected']['revenue'],840)
        self.assertIn('02/07/2022 · 22:00',answer['answer'])
        client.request=lambda payload:responses[1]
        with self.assertRaises(ValueError):client.chat('Ungrounded answer',self.s,lambda sku:{},c)

    def test_ai_cannot_write_its_own_numeric_facts_or_unverified_causal_claim(self):
        from services.report_narrative import render
        c=analysis_context(report(self.store,'report'),'prices')
        for text in ('Doanh thu 99999','Giá thấp do giảm giá'):
            response=json.dumps(dict(insights=[dict(fact_key='revenue',commentary=text)],actions=['HOLD_PRICE']))
            with self.assertRaises(ValueError):render(response,c)


if __name__=='__main__':unittest.main(verbosity=2)

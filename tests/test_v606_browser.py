"""Real Edge UI against an isolated FastAPI/SQLite context; no cloud API calls."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class Browser(unittest.TestCase):
 def test_live_sku_sales_refresh_and_pending_readiness(self):
  from fastapi.testclient import TestClient
  from playwright.sync_api import sync_playwright
  with tempfile.TemporaryDirectory() as t:
   os.environ['SMARTFRESH_DB']=str(Path(t)/'browser.sqlite3')
   import app
   with TestClient(app.app) as c:
    self.assertEqual(c.post('/api/auth/setup',json={'username':'test-manager','password':'ValidationOnly606!'}).status_code,200)
    s=c.get('/api/state').json();sid=s['id']
    def action(name,payload=None):
     nonlocal s
     r=c.post('/api/sessions/'+sid+'/'+name,json={'revision':s['revision'],'payload':payload or {}})
     self.assertEqual(r.status_code,200,r.text);s=r.json()
    action('plan_approve');action('prepared')
    c.post('/api/realtime/'+sid,json={'enabled':False,'speed':30,'pause_confirm':True})
    s=c.get('/api/state?session_id='+sid).json()
    with sync_playwright() as p:
     browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page();errors=[]
     page.on('pageerror',lambda e:errors.append(str(e)))
     def route_api(route):
      req=route.request;path=req.url.split('8000',1)[1]
      if path.startswith('/api/report-explanation/'):
       import json
       from urllib.parse import parse_qs,urlparse
       section=parse_qs(urlparse(path).query).get('section',['overview'])[0]
       route.fulfill(status=200,content_type='application/json',body=json.dumps(dict(status='ready',answer='Report analysis for '+section,model='test-only',as_of_minute=1170,tools_used=['get_business_report'])))
       return
      if path.startswith('/api/proposal-explanation/'):
       import json
       explain_sid=path.split('/')[3].split('?')[0]
       route.fulfill(status=200,content_type='application/json',body=json.dumps(dict(status='ready',answer='Automatic proposal explanation from test context.',model='test-only',as_of_minute=app.store.get(explain_sid)['minute'])))
       return
      r=c.request(req.method,path,content=req.post_data,headers={'content-type':'application/json'} if req.post_data else {})
      route.fulfill(status=r.status_code,content_type=r.headers.get('content-type','application/json'),body=r.content)
     page.route('**/api/**',route_api)
     page.goto('http://127.0.0.1:8000');page.wait_for_function("typeof state!=='undefined'&&state!==null")
     page.wait_for_function("document.getElementById('proposal-ai-text')?.textContent.includes('Automatic proposal explanation')")
     self.assertEqual(page.evaluate('currentView'),'m2')
     self.assertFalse(page.locator('[data-view="m1"]').is_visible())
     self.assertTrue(page.locator('[data-view="m2"]').is_visible())
     self.assertFalse(page.locator('#advanced-nav').evaluate('(e)=>e.open'))
     self.assertTrue(page.locator('.proposal-layout table').evaluate('(e)=>e.scrollWidth<=e.parentElement.clientWidth+1'))
     (ROOT/'docs/qa').mkdir(exist_ok=True)
     page.screenshot(path=str(ROOT/'docs/qa/v606-morning-compact.png'),full_page=True)
     self.assertNotEqual(page.evaluate('money(null)'),page.evaluate('money(0)'))
     page.evaluate("go('settings')");self.assertEqual(page.locator('#settings-form').count(),1)
     self.assertEqual(page.locator('#check-gemini-models').count(),1)
     page.evaluate("go('ledger')")
     # Tick is an internal clock action; use workflow, since it is not a public human action.
     raw=app.workflow.mutate(sid,s['revision'],'tick',{'target':600});s=app.snapshot(raw)
     page.wait_for_function('state.minute===600')
     page.wait_for_selector('[data-live-sold]')
     self.assertGreater(sum(int(n) for n in page.locator('[data-live-sold]').all_text_contents()),0)
     before=sum(p['sold'] for p in raw['products'].values())
     raw=app.workflow.mutate(sid,raw['revision'],'tick',{'target':773})
     page.wait_for_function('state.minute===773')
     page.wait_for_function('Array.from(document.querySelectorAll("[data-live-sold]")).reduce((s,e)=>s+Number(e.textContent),0)>'+str(before))
     self.assertTrue(all(p['stock']>0 for p in raw['products'].values()))
     r=c.get('/api/readiness?session_id='+sid);self.assertEqual(r.status_code,200,r.text)
     pending={i['id']:i['status'] for i in r.json()['conditions']}
     self.assertEqual(pending['F_RECONCILIATION'],'PENDING');self.assertEqual(pending['S_2130'],'PENDING')
     raw=app.workflow.mutate(sid,raw['revision'],'tick',{'target':1170})
     self.assertIsNone(raw['pending']);self.assertEqual(raw['phase'],'running')
     page.wait_for_function('state.minute===1170');page.evaluate("go('m1')")
     self.assertTrue(page.locator('[data-view="m1"]').is_visible());self.assertFalse(page.locator('[data-view="m2"]').is_visible())
     self.assertEqual(page.locator('[data-approve="price"]').count(),0)
     self.assertTrue(all(p['discount']==0 for p in raw['products'].values()))
     self.assertTrue(page.evaluate('Boolean(state.proposal_explanation.answer)'))
     for target in (1200,1230,1260):raw=app.workflow.mutate(sid,raw['revision'],'tick',{'target':target})
     page.wait_for_function("state.minute===1260&&state.phase==='price_pending'")
     self.assertEqual(page.locator('[data-approve="price"]').count(),1)
     self.assertIn('giả định',page.locator('.sku-reason').first.inner_text())
     page.screenshot(path=str(ROOT/'docs/qa/v606-evening-compact.png'),full_page=True)
     # Verify the actual trained proposal passes the server approval boundary, then applies.
     pid=raw['pending']['id'];before=list(raw['ledger'])
     for name in ('price_approve','price_apply'):
      raw=app.workflow.mutate(sid,raw['revision'],name,{'proposal_id':pid})
     self.assertEqual(raw['ledger'],before)
     page.wait_for_function("state.phase==='running'&&Object.values(state.products).some(p=>p.discount>0)")
     page.evaluate("go('reports')");page.wait_for_timeout(500)
     page.wait_for_selector('[data-business-compare]')
     self.assertGreaterEqual(page.locator('.business-chart').count(),2)
     self.assertIn('chưa chốt',page.locator('.business-history').inner_text())
     self.assertIn('Chưa đủ hai ngày',page.locator('.business-kpis').inner_text())
     page.select_option('[data-business-days]','7')
     page.wait_for_function('businessData?.days===7')
     page.select_option('[data-business-metric]','revenue')
     self.assertEqual(page.locator('.business-history svg circle').count(),1)
     page.select_option('[data-business-compare]','week')
     self.assertEqual(page.locator('[data-business-compare]').input_value(),'week')
     page.screenshot(path=str(ROOT/'docs/qa/v606-business-report.png'),full_page=True)
     page.wait_for_function("document.getElementById('report-ai-text')?.textContent.includes('Report analysis for overview')")
     page.click('[data-business-tab="prices"]')
     page.wait_for_function("document.getElementById('report-ai-text')?.textContent.includes('Report analysis for prices')")
     self.assertGreaterEqual(page.locator('.report-charts svg').count(),2)
     page.screenshot(path=str(ROOT/'docs/qa/v606-report-prices.png'),full_page=True)
     page.click('[data-business-tab="products"]')
     page.select_option('[data-business-sku]','TP-DN-001')
     page.wait_for_function("document.getElementById('report-ai-text')?.textContent.includes('Report analysis for products')")
     self.assertEqual(page.locator('.report-stacks>div').count(),1)
     page.screenshot(path=str(ROOT/'docs/qa/v606-report-products.png'),full_page=True)
     page.click('[data-business-tab="baseline"]')
     page.wait_for_function("baselineData?.closed_days===171")
     self.assertIn('782.772.100',page.locator('.report-charts').inner_text())
     self.assertIn('proxy',page.locator('.report-charts').inner_text())
     self.assertEqual(page.evaluate('state.totals.revenue'),app.snapshot(app.store.get(sid))['totals']['revenue'])
     page.screenshot(path=str(ROOT/'docs/qa/v606-baseline-history.png'),full_page=True)
     page.click('[data-business-tab="products"]')
     page.set_viewport_size({'width':390,'height':844})
     self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
     page.set_viewport_size({'width':1280,'height':900})
     self.assertIn('45%',page.locator('#view').inner_text())
     self.assertEqual(page.evaluate('state.financial_estimate.rate'),.45)
     self.assertIsNotNone(page.evaluate('state.totals.cost_assumed'))
     raw=app.store.get(sid)
     while raw['minute']<1320:
      raw=app.workflow.mutate(sid,raw['revision'],'tick',{'target':1320})
      if raw['pending']:
       payload={'proposal_id':raw['pending']['id']}
       for action_name in ('price_approve','price_apply'):raw=app.workflow.mutate(sid,raw['revision'],action_name,payload)
     raw=app.workflow.mutate(sid,raw['revision'],'close')
     page.wait_for_function("state.phase==='closed'")
     page.wait_for_selector('[data-next-day]')
     page.click('[data-next-day]')
     page.wait_for_function("state.day==='2022-07-02'")
     self.assertEqual(page.evaluate('state.plan[0].supply.observation_days'),1)
     self.assertIsNotNone(page.evaluate('state.weather.prior_day_rain_mm'))
     self.assertIn('21:30',page.locator('.sku-reason').first.inner_text())
     self.assertIn('Reanalysis',page.locator('.planning-weather').inner_text())
     page.screenshot(path=str(ROOT/'docs/qa/v606-adaptive-next-day.png'),full_page=True)
     page.evaluate("go('monitoring')");page.wait_for_timeout(500)
     self.assertFalse(errors,errors)
     browser.close()

if __name__=='__main__':unittest.main(verbosity=2)

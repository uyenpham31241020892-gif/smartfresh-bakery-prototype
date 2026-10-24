import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
"""Dummy mechanics only. No officialtestcustomers or trainedmodel are executed."""
import unittest,tempfile,json,csv,subprocess,sys,socket,time,urllib.request,urllib.error,shutil
from pathlib import Path
from datetime import date,timedelta
from pos_core import Session,quote_price,quote_cash_price,BRANCHES
SKU='BK-003'
def fixtures(n=1,days=2):
 dates=[str(date(2022,6,15)+timedelta(days=i)) for i in range(days)]
 spec=dict(sku_code=SKU,product_name_reference='Bánh thử nghiệm',unit_price_vnd_reference=35000,unit_production_cost_vnd_assumed=16000,unit_disposal_cost_vnd_assumed=1000,batch_size_units_assumed=4,daily_capacity_units_assumed=400,max_batch_units_assumed=100,shelf_capacity_units_assumed=32,shelf_refill_threshold_units_assumed=8,production_lead_time_minutes_assumed=45,last_production_ready_time_assumed='19:30')
 cal={d:dict(date=d,weekday_iso=date.fromisoformat(d).isoweekday(),is_weekend=0,is_public_holiday=0,is_tet_run_up=0,is_commercial_or_cultural_event=0,is_vietnam_holiday_or_event_period=0,event_stratum='ordinary',tet_date='2022-02-01',open_time='08:00',close_time='22:00') for d in dates}
 hist=[dict(date=str(date(2022,6,15)-timedelta(days=i)),sku_code=SKU,prepared_qty=200,sold_qty=180,refill_qty=0,waste_qty=20,stockout_day_flag=0,censored_demand_flag=0) for i in range(7,0,-1)]
 market={(d,SKU):[dict(time=f'{8+i//4:02d}:{15*(i%4):02d}',base_intent_qty=n,discount_sensitive_pool_qty=0) for i in range(56)] for d in dates}
 return market,cal,{SKU:spec},hist
def session(n=1,days=2,mode='DEMO'):
 m,c,s,h=fixtures(n,days);return Session(m,c,s,h,mode=mode)
def until(x,t):
 if x.phase=='PREPARE':x.advance()
 while x.time<t:x.advance()
def dump(p,rows):
 with open(p,'w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
class Mechanics(unittest.TestCase):
 def test_01_integer_money_and_bound(self):
  for price in (25000,30000,35000,40000):
   for d in (0,10,15,20,25,30,35,40,45,50):
    q=quote_price(price,d);self.assertIsInstance(q['approved_unit_price_vnd'],int);self.assertLessEqual(q['approved_discount_pct'],50);self.assertAlmostEqual(q['approved_discount_pct'],100*(price-q['approved_unit_price_vnd'])/price)
  self.assertEqual(quote_price(25000,50)['approved_unit_price_vnd'],12500)
  self.assertEqual(quote_price(29400,7.5)['approved_unit_price_vnd'],27195)
  self.assertEqual(quote_cash_price(27400,23000)['approved_unit_price_vnd'],23000)
  self.assertEqual(quote_price(27400,0,23000,100*(27400-23000)/27400)['approved_unit_price_vnd'],23000)
  with self.assertRaises(ValueError):quote_cash_price(24500,12249)
 def test_02_pending_does_not_change_price(self):
  x=session();until(x,'20:00');x.propose_price('JOINT_M1_M2',SKU,20);self.assertEqual(x.context('JOINT_M1_M2')['items'][0]['current_unit_price_vnd'],35000)
 def test_03_2000_approval_updates_display_and_future_receipts(self):
  x=session();until(x,'20:00');old=[r.copy() for r in x.states['JOINT_M1_M2',SKU].pos];p=x.propose_price('JOINT_M1_M2',SKU,20);x.approve(p['id']);self.assertEqual(x.context('JOINT_M1_M2')['items'][0]['current_unit_price_vnd'],28000);x.advance();st=x.states['JOINT_M1_M2',SKU];new=[r for r in st.pos if r['transaction_at']>='2022-06-15T20:00:00+07:00'];self.assertTrue(new);self.assertTrue(all(r['unit_price_vnd']==28000 and r['discount_pct']==20 for r in new));self.assertTrue(all(r['unit_price_vnd']==35000 for r in old));self.assertEqual(st.pos[:len(old)],old)
 def test_04_rejection_keeps_price(self):
  x=session();until(x,'20:00');p=x.propose_price('M1_ONLY',SKU,20);x.approve(p['id'],False);self.assertEqual(x.states['M1_ONLY',SKU].price['approved_unit_price_vnd'],35000)
 def test_05_scheduled_price_no_early_activation(self):
  x=session();until(x,'19:30');p=x.propose_price('M1_ONLY',SKU,20,'20:00');x.approve(p['id']);self.assertEqual(x.states['M1_ONLY',SKU].price['approved_unit_price_vnd'],35000);until(x,'20:00');self.assertEqual(x.states['M1_ONLY',SKU].price['approved_unit_price_vnd'],28000)
 def test_06_stale_approval_rejected(self):
  x=session();until(x,'20:00');p=x.propose_price('M1_ONLY',SKU,20);x.advance()
  with self.assertRaises(ValueError):x.approve(p['id'])
 def test_07_baseline_fast_seller_keeps_zero(self):
  m,c,s,h=fixtures(0);m['2022-06-15',SKU][50]['base_intent_qty']=30;m['2022-06-15',SKU][51]['base_intent_qty']=30;x=Session(m,c,s,h,mode='DEMO');x.prepare('BASELINE',SKU,dict(initial_qty=100));until(x,'21:00');self.assertEqual(x.states['BASELINE',SKU].inventory,40);self.assertEqual(x.states['BASELINE',SKU].price['approved_discount_pct'],0)
 def test_08_sold_out_no_sticker(self):
  x=session(10);x.prepare('JOINT_M1_M2',SKU,dict(initial_qty=4));until(x,'20:00')
  with self.assertRaises(ValueError):x.propose_price('JOINT_M1_M2',SKU,20)
 def test_09_actual_floor_and_monotonic_cash(self):
  q=quote_price(35000,0,28000,40);self.assertLessEqual(q['approved_unit_price_vnd'],21000);self.assertGreaterEqual(q['approved_discount_pct'],40)
 def test_10_closed_loop_own_branch_history(self):
  x=session(2);x.prepare('M2_ONLY',SKU,dict(initial_qty=4));until(x,'22:00');d=x.day;self.assertEqual(x.phase,'CLOSED');x.advance();self.assertNotEqual(x.hist['BASELINE',SKU][-1]['sold_qty'],x.hist['M2_ONLY',SKU][-1]['sold_qty']);self.assertEqual(x.hist['M2_ONLY',SKU][-1]['date'],d)
 def test_11_inventory_and_revenue(self):
  x=session(3);until(x,'22:00')
  for b in BRANCHES:
   st=x.states[b,SKU];self.assertEqual(st.produced,st.sold+st.inventory);self.assertEqual(st.revenue,sum(r['amount_vnd'] for r in st.pos));self.assertGreater(st.refill,0)
 def test_12_frozen_requires_M2(self):
  x=session(mode='FROZEN')
  with self.assertRaises(ValueError):x.advance()
 def test_13_no_hidden_or_future_context(self):
  x=session();until(x,'20:00');c=x.context('JOINT_M1_M2');raw=json.dumps(c);self.assertFalse(any(t in raw for t in ('lost_base','base_intent_qty','discount_sensitive_pool','discount_beta','scenario_lambda')))
  for item in c['items']:
   self.assertTrue(all(r['available_at']<=c['as_of'] for r in item['observed_intervals']+item['recent_transactions']));self.assertTrue(all(r['date']<c['date'] for r in item['completed_branch_history']))
 def test_14_quantity_capacity_and_leadtime(self):
  x=session()
  for n in (1.5,-4,404,float('nan'),True):
   with self.assertRaises(ValueError):x.prepare('M2_ONLY',SKU,dict(initial_qty=n))
  with self.assertRaises(ValueError):x.prepare('M2_ONLY',SKU,dict(initial_qty=4,production_batches=[dict(qty=8,order_time='10:00',ready_time='10:15')]))
 def test_15_other_branch_price_unchanged(self):
  x=session();until(x,'20:00');p=x.propose_price('M1_ONLY',SKU,20);x.approve(p['id']);self.assertEqual(x.states['BASELINE',SKU].price['approved_unit_price_vnd'],35000)
 def test_16_own_last30_60(self):
  x=session(2);until(x,'20:00');i=x.context('M1_ONLY')['items'][0];self.assertEqual(i['sold_last_30min'],4);self.assertEqual(i['sold_last_60min'],8)
 def test_18_ready_batch_visible_before_pricing(self):
  x=session(0);x.prepare('JOINT_M1_M2',SKU,dict(initial_qty=4,production_batches=[dict(qty=8,order_time='18:45',ready_time='19:30')]))
  until(x,'19:30');item=x.context('JOINT_M1_M2')['items'][0];self.assertEqual(item['inventory_at_decision'],12);self.assertEqual(item['produced_qty_so_far'],12)
class HTTPGate(unittest.TestCase):
 def test_17_token_isolation_and_2000_POS(self):
  with tempfile.TemporaryDirectory(prefix='v604-api-dummy-') as temp:
   root=Path(temp);private=root/'private';public=root/'public';private.mkdir();public.mkdir();m,c,s,h=fixtures(1);rows=[dict(date=d,sku_code=sku,**r) for (d,sku),v in m.items() for r in v];dump(private/'market_test_PRIVATE.csv',rows);dump(private/'market_ALL_PRIVATE.csv',rows);dump(private/'calendar_ALL.csv',list(c.values()));dump(private/'baseline_development_FULL_SCORER_ONLY.csv',h);dump(public/'calendar_test.csv',list(c.values()));dump(public/'sku_master.csv',list(s.values()));dump(public/'history_seed_through_20220630.csv',h);dump(private/'weather_hourly_PRIVATE.csv',[dict(date='2022-06-14',precipitation=0,temperature_2m=28)])
   (public/'build_config.json').write_text(json.dumps({'default_price_response_strength':0}));tokenfile=root/'tokens.json'
   with socket.socket() as sk:sk.bind(('127.0.0.1',0));port=sk.getsockname()[1]
   proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('pos_server.py')),'--custodian-dir',str(private),'--runtime-dir',str(public),'--token-file',str(tokenfile),'--port',str(port),'--scorer-output',str(root/'scorer')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   try:
    for _ in range(240):
     if tokenfile.exists():break
     time.sleep(.025)
    tokens=json.loads(tokenfile.read_text());base=f'http://127.0.0.1:{port}'
    def call(path,role='manager',data=None):
     req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+tokens[role],'Content-Type':'application/json'})
     with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
    for _ in range(80):
     try:state=call('/api/state');break
     except (ConnectionError,urllib.error.URLError):time.sleep(.025)
    with self.assertRaises(urllib.error.HTTPError) as e:call('/api/context?branch=BASELINE','M1_ONLY')
    self.assertEqual(e.exception.code,403)
    with self.assertRaises(urllib.error.HTTPError) as e:call('/market_test_PRIVATE.csv','M1_ONLY')
    self.assertEqual(e.exception.code,403)
    while state['clock'][11:16]<'20:00':state=call('/api/advance',data={})
    proposal=call('/api/propose','JOINT_M1_M2',dict(branch='JOINT_M1_M2',sku_code=SKU,requested_discount_pct=20))
    with self.assertRaises(urllib.error.HTTPError) as e:call('/api/approve','JOINT_M1_M2',dict(proposal_id=proposal['id']))
    self.assertEqual(e.exception.code,403);call('/api/approve',data=dict(proposal_id=proposal['id']));after=call('/api/context?branch=JOINT_M1_M2','JOINT_M1_M2');self.assertEqual(after['items'][0]['current_unit_price_vnd'],28000)
    call('/api/advance',data={});after=call('/api/context?branch=JOINT_M1_M2','JOINT_M1_M2');latest=after['items'][0]['recent_transactions'][-1];self.assertEqual(latest['unit_price_vnd'],28000);self.assertEqual(latest['discount_pct'],20)
   finally:proc.terminate();proc.wait(timeout=5);proc.stderr.close()
if __name__=='__main__':unittest.main(verbosity=2)

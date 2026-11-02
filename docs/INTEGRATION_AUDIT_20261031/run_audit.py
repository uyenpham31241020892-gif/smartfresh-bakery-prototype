"""Independent source-POS comparison; requires original evaluated archive extracted.
No training. Source runtime is imported independently from prototype feature code.
"""
import sys,os,json,tempfile,csv,hashlib,copy
from pathlib import Path
from collections import defaultdict
BASE=Path(__file__).resolve().parents[1]
APP=BASE/'audit_app/SmartFresh_V4_Prototype'
ORIG=BASE/'audit_original/Data (evaluated)/TRAINED_TESTED/SmartFresh_V609_03_TEST_POS_RUNTIME/03_TEST_POS_RUNTIME/code'
os.environ['SMARTFRESH_DB']=tempfile.mktemp(suffix='.sqlite3');os.environ['SMARTFRESH_LEARNING_DIR']=tempfile.mkdtemp()
sys.path.insert(0,str(APP))
import app
sys.path.insert(0,str(ORIG))
import pos_core,model_features
from services.engine import clean,read_csv
from services.costs import estimate
from services.v4_market_worker import process
world=APP/'simulation_only/v4/validation_world.jsonl'
market=defaultdict(list)
for line in world.open():
 r=json.loads(line);market[r['date'],r['sku_code']].append(r)
for rows in market.values():rows.sort(key=lambda r:r['time'])
cal={r['date']:clean(r) for r in read_csv(BASE/'audit_original/Data (evaluated)/TRAINED_TESTED/calendar_ALL.csv')}

def source_session(day,plans):
 w=app.simulator.calendar[day]
 hist=[dict(r,refill_qty=r.get('refill_qty',0),waste_qty=r.get('waste_qty',0),stockout_day_flag=r.get('censored_demand_flag',0)) for r in app.engine.observed if r['date']<day]
 prev=w['weather_reference_date']
 session=pos_core.Session(market,{day:cal[day]},app.engine.master,hist,{prev:dict(rain_mm=w['prior_day_rain_mm'],temp_c=w['prior_day_temp_c'])},branches=('JOINT_M1_M2',),mode='FROZEN',response_strength=.6)
 for p in plans:session.prepare('JOINT_M1_M2',p['sku'],p['v4_plan'])
 session.advance();return session

results=[];checkpoints=[];feature_mismatch=[];market_errors=[];m2_errors=[]
# 3 cited days + 3 distributed days, independent day starts with same observed history.
for day in sorted(app.simulator.calendar):
 s=app.workflow.create(day,apply_closed_history=False)
 ref=source_session(day,s['plan'])
 for p,item in zip(s['plan'],ref.context('JOINT_M1_M2')['items']):
  # Feature and M2 result oracle built by original POS, not by app.
  old=app.engine.adapter._DAILY_CHANGE_TRACKER;app.engine.adapter._DAILY_CHANGE_TRACKER={}
  try:q=app.engine.adapter.prepare(item['morning_features'],item['completed_branch_history'])
  finally:app.engine.adapter._DAILY_CHANGE_TRACKER=old
  if q!=p['v4_plan']:m2_errors.append([day,p['sku'],'plan'])
  for k,v in item['morning_features'].items():
   if p['features'].get(k)!=v:m2_errors.append([day,p['sku'],k,p['features'].get(k),v])
 app.workflow.do_plan_approve(s,{});app.workflow.do_prepared(s,{})
 # Force identical APPROVED prices, using app recommendations, in both POS engines.
 # At 21:00 bypass ONLY the reference preapproved baseline rule in this controlled test.
 # Source original _enter_time still executes at all earlier times; patch local clone
 # to remove baseline reference at 21 by temporarily entering as 20:59 is NOT used.
 # Instead subclass method equivalent: original source WITHOUT the documented block.
 orig_enter=pos_core.Session._enter_time
 import inspect
 src=inspect.getsource(orig_enter);a=src.index("  # Baseline is a preapproved comparator rule");b=src.index('  for pid,p in list',a)
 scope={'CHECKPOINTS':pos_core.CHECKPOINTS,'deepcopy':copy.deepcopy,'minute':pos_core.minute}
 exec(src[1:a]+src[b:],scope)
 ref._enter_time=scope['_enter_time'].__get__(ref,type(ref))
 while s['minute']<1320:
  dest=next((v for v in [1170,1200,1230,1260,1290,1320] if v>s['minute']))
  app.workflow.do_advance(s,{'target':dest})
  while pos_core.minute(ref.time)<dest:ref.advance()
  for sku,p in s['products'].items():
   rs=ref.states['JOINT_M1_M2',sku]
   actual=[p['prepared'],p['sold'],p['stock'],p['revenue'],p['shelf_inventory'],p['backroom_inventory'],p['lost']]
   expected=[rs.produced,rs.sold,rs.inventory,rs.revenue,rs.shelf,rs.back,rs.lost_base+rs.lost_promo]
   if actual!=expected:market_errors.append([day,dest,sku,actual,expected])
  if dest==1320:break
  assert s['pending']['origin']=='AI_M1',(day,s['pending'])
  original_count=dict(s.get('v4_proposal_counts',{}))
  for row,item in zip(s['pending']['rows'],ref.context('JOINT_M1_M2')['items']):
   # No preapproved baseline in controlled price-sequence test; match None before21/zero thereafter.
   ctx=model_features.m1_features(item,ref.clock)
   if row['model_features']!=ctx:
    feature_mismatch.append([day,dest,row['sku'],{k:[row['model_features'].get(k),ctx.get(k)] for k in set(ctx)|set(row['model_features']) if row['model_features'].get(k)!=ctx.get(k)}])
   previous_count=original_count[row['sku']]-(1 if row['v4_action'] else 0)
   old=app.engine.adapter._DAILY_CHANGE_TRACKER;app.engine.adapter._DAILY_CHANGE_TRACKER={(day,row['sku']):previous_count}
   try:oracle=app.engine.adapter.markdown({'model_features':ctx,'price_context':{'current_discount_pct':item['current_discount_pct'],'list_price_vnd':item['list_price_vnd']}},ref.clock)
   finally:app.engine.adapter._DAILY_CHANGE_TRACKER=old
   checkpoints.append(dict(day=day,minute=dest,sku=row['sku'],stock=row['stock'],sales30=row['sales30'],discount=row['discount'],oracle_action=oracle,app_action=row['v4_action'],match=oracle==row['v4_action']))
   # source uses effective float discount, compare integer menu prices for this controlled test
   ref._apply('JOINT_M1_M2',row['sku'],pos_core.quote_price(item['list_price_vnd'],row['discount'],item['current_unit_price_vnd']),'AUDIT_CONTROLLED_PRICE')
  app.workflow.do_price_approve(s,{'proposal_id':s['pending']['id']});app.workflow.do_price_apply(s,{'proposal_id':s['pending']['id']})
 f=estimate(s['products'],True)
 results.append(dict(day=day,prepared=sum(p['prepared'] for p in s['products'].values()),sold=sum(p['sold'] for p in s['products'].values()),waste=sum(p['stock'] for p in s['products'].values()),lost=sum(p['lost'] for p in s['products'].values()),**{k:f[k] for k in ('revenue','preparation_cost','disposal_fee','markdown_cost','contribution_before_overhead')}))
 print(day,results[-1],flush=True)
report=dict(scope='60 independent Validation days; controlled identical approved prices; source 21:00 baseline block intentionally excluded ONLY in controlled test; NOT full evaluation protocol parity',results=results,m2_errors=m2_errors,market_errors=market_errors,feature_mismatch=feature_mismatch,checkpoint_count=len(checkpoints),action_mismatch=sum(not r['match'] for r in checkpoints),frozen_hashes=app.engine.require_integrity())
(BASE/'audit_evidence/audit_results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
with (BASE/'audit_evidence/checkpoints.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=checkpoints[0]);w.writeheader();w.writerows(checkpoints)
print('SUMMARY',json.dumps({k:v for k,v in report.items() if k!='results'}),flush=True)

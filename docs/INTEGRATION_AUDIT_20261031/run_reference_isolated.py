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


results=[];actions=[]
for day in sorted(app.simulator.calendar):
 plans=app.engine.plan(day,app.simulator.history_before(day),app.simulator.calendar[day],app.simulator.outcomes_before(day))
 w=app.simulator.calendar[day]
 hist=[dict(r,refill_qty=r.get('refill_qty',0),waste_qty=r.get('waste_qty',0),stockout_day_flag=r.get('censored_demand_flag',0)) for r in app.engine.observed if r['date']<day]
 for branch in pos_core.BRANCHES:
  ref=pos_core.Session(market,{day:cal[day]},app.engine.master,hist,{w['weather_reference_date']:dict(rain_mm=w['prior_day_rain_mm'],temp_c=w['prior_day_temp_c'])},branches=(branch,),mode='FROZEN',response_strength=.6)
  app.engine.adapter._DAILY_CHANGE_TRACKER={}
  if branch in ('M2_ONLY','JOINT_M1_M2'):
   for item in ref.context(branch)['items']:
    ref.prepare(branch,item['sku_code'],app.engine.adapter.prepare(item['morning_features'],item['completed_branch_history']))
  ref.advance()
  while ref.phase!='CLOSED':
   if ref.time in pos_core.CHECKPOINTS and branch in ('M1_ONLY','JOINT_M1_M2'):
    for item in ref.context(branch)['items']:
     if item['inventory_at_decision']<=0:continue
     f=model_features.m1_features(item,ref.clock)
     action=app.engine.adapter.markdown({'model_features':f,'price_context':{k:item[k] for k in ('list_price_vnd','current_unit_price_vnd','current_discount_pct','price_version')}},ref.clock)
     actions.append(dict(day=day,time=ref.time,branch=branch,sku=item['sku_code'],action=action,current=item['current_discount_pct'],floor=item['baseline_announced_2100_pct']))
     if action:
      prop=ref.propose_price(branch,item['sku_code'],requested=action,effective_time=ref.time)
      ref.approve(prop['id'])
   ref.advance()
  rows=ref.private_results
  results.append(dict(day=day,branch=branch,**{k:sum(r[k] for r in rows) for k in ('prepared_qty','sold_qty','waste_qty','revenue_vnd','production_cost_vnd_assumed','disposal_cost_vnd_assumed','markdown_operations_cost_vnd_assumed','contribution_vnd_assumed','lost_base_hidden_scenario','lost_promo_hidden_scenario')}))
 print(day,flush=True)
(BASE/'audit_evidence/reference_isolated_results.json').write_text(json.dumps(dict(scope='Original unmodified POS runtime; four isolated branches with independent adapter trackers; 60 independent Validation days with common prior observed history, NOT official 62-day rolling test',results=results,actions=actions),indent=2))

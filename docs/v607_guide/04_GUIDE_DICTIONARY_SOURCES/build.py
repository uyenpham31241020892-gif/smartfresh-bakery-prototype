"""Rebuild V607 from immutable V606 raw inputs; never train or run official test."""
from pathlib import Path
import csv,json,math,hashlib,shutil,sys,statistics
from collections import defaultdict
from datetime import date,timedelta
R=Path(__file__).resolve().parents[2];OLD=R/'deliverable/SmartFresh_V606';O=R/'deliverable/SmartFresh_V607'
B=O/'01_ORIGINAL_BASELINE_PRIVATE';T=O/'02_TRAIN_VALIDATION';E=O/'03_TEST_POS_RUNTIME';D=O/'04_GUIDE_DICTIONARY_SOURCES'
for p in (B,T,E,D):p.mkdir(parents=True,exist_ok=True)
def read(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def js(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def u(s):return int(hashlib.sha256(s.encode()).hexdigest()[:13],16)/16**13
def rounded(x,key):return int(x)+int(u(key)<x-int(x))
shutil.copytree(OLD/'03_TEST_POS_RUNTIME/code',E/'code',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for name in ['french_source_original_UNMODIFIED.csv','calendar_ALL.csv','weather_hourly_PRIVATE.csv']:
 shutil.copy2(OLD/'01_ORIGINAL_BASELINE_PRIVATE'/name,B/name)
for name in ['model_io_guard.py','censored_tools_DIAGNOSTIC_ONLY.py']:shutil.copy2(OLD/'02_TRAIN_VALIDATION'/name,T/name)
for name in ['SURVEY_SOURCE.csv','SOURCE_REPORT_VERBATIM.txt','sku_master_AEON_TanPhu_survey.csv','sku_master_AEON_TanPhu_survey.json']:
 shutil.copy2(OLD/'04_GUIDE_DICTIONARY_SOURCES'/name,D/name)
for name in ['run_pos_demo.sh','RUN_POS_DEMO_WINDOWS.bat','data_access_manifest.json']:
 shutil.copy2(OLD/'03_TEST_POS_RUNTIME'/name,E/name)
# Runtime: integer VND, continuous nominal percentages, exact effective 50% cap.
p=E/'code/pos_core.py';s=p.read_text().replace('V6.06','V6.07').replace('V606_SURVEY_PRICES_WITH_ASSUMED_POOLED_PROXY_DEMAND_NOT_AEON_POS','V607_SURVEY_PRICE_FAMILY_PROXY_ASSUMED_OPERATIONS_NOT_AEON_POS')
s=s.replace("or (cash!=p and cash%1000)","or False").replace('Discounted cash price must be whole1000VND; HOLD preserves list price','Cash price must be a positive integer no greater than list price').replace('price_quantum_vnd=1 if cash==p else 1000','price_quantum_vnd=1')
s=s.replace("requested not in MENU","not math.isfinite(float(requested)) or not 0<=float(requested)<=50")
s=s.replace("Decimal('.5')/1000","Decimal('.5')").replace("(1-floor/100)/1000","(1-floor/100)").replace('))*1000', '))')
s=s.replace("cash=min(hi,max(lo,round1000(Decimal(p)*(1-Decimal(str(requested))/100))))","cash=min(hi,max(lo,int((Decimal(p)*(1-Decimal(str(requested))/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))))")
s=s.replace("q['requested_discount_pct']=int(requested)","q['requested_discount_pct']=float(requested)")
s=s.replace('whole1000VND','integer VND').replace('whole1000','integer VND')
start=s.index(' def baseline_qty(');end=s.index(' def _validate_plan(',start)
s=s[:start]+''' def baseline_qty(self,b,sku):
  # Weekly committed plans: only history strictly before this week's Monday.
  today=date.fromisoformat(self.day);cutoff=str(today-timedelta(days=today.weekday()))
  h=[r for r in self.hist[b,sku] if r['date']<cutoff][-28:]
  if not h:h=[r for r in self.hist[b,sku] if r['date']<self.day][-7:]
  if not h:raise ValueError('No prior observed history')
  same=[r for r in h if date.fromisoformat(r['date']).weekday()==today.weekday()]
  z=same if len(same)>=2 else h
  values=[r['sold_qty']/event_factor(r['date']) for r in z]
  # Buffer is a declared assumption, not fitted to hidden demand or AI performance.
  q=(sum(values)/len(values)+.5*(statistics.pstdev(values) if len(values)>1 else 0))*event_factor(self.day)
  if sum(r['censored_demand_flag'] for r in z)/len(z)>=.5:q=max(q,sum(r['prepared_qty'] for r in z)/len(z))
  batch=int(self.master[sku]['batch_size_units_assumed']);cap=int(self.master[sku]['daily_capacity_units_assumed'])
  return min(cap,max(batch,math.ceil(q/batch)*batch))
''' +s[end:]
s=s.replace('import math,hashlib,csv,json','import math,hashlib,csv,json,statistics')
# Own-state cost decomposition; wasted production is a diagnostic subset, not another subtraction.
needle="   if row['inventory_balance_error']:"
s=s.replace(needle,"""   changes=sum(1 for e in self.price_events if e['date']==self.day and e['branch']==b and e['sku_code']==s and e['price_version']>0 and e['approved_unit_price_vnd']<spec['unit_price_vnd_reference'])
   changes=len({e['price_version'] for e in self.price_events if e['date']==self.day and e['branch']==b and e['sku_code']==s and e['price_version']>0})
   row['markdown_operations_cost_vnd_assumed']=changes*int(spec.get('markdown_action_cost_vnd_assumed',0))
   row['wasted_production_cost_vnd_assumed']=st.inventory*spec['unit_production_cost_vnd_assumed'] if spec['unit_production_cost_vnd_assumed'] is not None else None
   row['contribution_vnd_assumed']=row['revenue_vnd']-row['production_cost_vnd_assumed']-row['disposal_cost_vnd_assumed']-row['markdown_operations_cost_vnd_assumed'] if row['production_cost_vnd_assumed'] is not None and row['disposal_cost_vnd_assumed'] is not None else None
"""+needle)
p.write_text(s)
p=E/'code/pos_ui.html';p.write_text(p.read_text().replace('step="1000"','step="1"').replace('V6.06','V6.07'))
# Preserve 233 observed open dates, no synthesis of additional calendar days.
calendar={r['date']:r for r in read(B/'calendar_ALL.csv')}
for r in calendar.values():
 for k in ['weekday_iso','is_weekend','is_public_holiday','is_tet_run_up','is_vietnam_holiday_or_event_period','is_commercial_or_cultural_event']:r[k]=int(r[k])
dates=sorted(calendar);devdates=[d for d in dates if d<='2022-06-30'];testdates=[d for d in dates if d>'2022-06-30'];fitdates=[d for d in devdates if d<='2022-04-30']
master=read(OLD/'03_TEST_POS_RUNTIME/sku_master.csv');codes=[r['sku_code'] for r in master]
articles=['CROISSANT','PAIN AUX RAISINS','CHAUSSON AUX POMMES','CROISSANT AMANDES','PAIN AU CHOCOLAT','ECLAIR','TARTELETTE'];mapping=dict(zip(articles,codes))
raw=read(B/'french_source_original_UNMODIFIED.csv');source=[];totals=defaultdict(float)
for i,r in enumerate(raw):
 try:n=float(r['Quantity'])
 except ValueError:continue
 if r['article'] not in mapping or n<=0 or r['date']<'2021-12-01' or r['date']>'2022-08-31':continue
 source.append((i,r,n));totals[r['date'],r['article']]+=n
warmdates=sorted({r['date'] for _,r,n in source if r['date']<'2022-01-01'})
# Pre-period weekday normalization avoids learning French weekday effects from test.
weekday_ratio={};crosswalk=[]
for article,sku in mapping.items():
 vals=[totals[d,article] for d in warmdates];mean=statistics.mean(vals)
 for dow in range(7):
  vv=[totals[d,article] for d in warmdates if date.fromisoformat(d).weekday()==dow]
  # Shrink noisy 4-5 observations toward one; do not claim local effect estimated.
  ratio=(sum(vv)+4*mean)/(len(vv)+4)/max(mean,.1);weekday_ratio[article,dow]=ratio
 crosswalk.append(dict(source_article=article,target_sku=sku,mapping_kind='PASTRY_FAMILY_TEMPORAL_PROXY_NOT_PRODUCT_IDENTITY',confidence='LOW',volume_multiplier=1,source_price_used=False))
write(D/'sku_proxy_crosswalk.csv',crosswalk)
localweek=[1,1,1,1.05,1.10,1.35,1.40]
wx=defaultdict(list)
for r in read(B/'weather_hourly_PRIVATE.csv'):wx[r['date']].append((float(r['precipitation']),float(r['temperature_2m'])))
weather={d:dict(rain_mm=sum(v[0] for v in vs),temp_c=statistics.mean(v[1] for v in vs)) for d,vs in wx.items()}
sys.path.insert(0,str(E/'code'));from pos_core import Session,stamp,minute,quote_price
market={(d,s):[dict(time=f'{8+i//4:02d}:{15*(i%4):02d}',base_intent_qty=0,discount_sensitive_pool_qty=0) for i in range(56)] for d in dates for s in codes};lineage=[];warmcount=defaultdict(int)
for i,r,n in source:
 d=r['date'];sku=mapping[r['article']];dow=date.fromisoformat(d).weekday()
 local=localweek[dow]/weekday_ratio[r['article'],dow]
 c=calendar.get(d,{});event=1.15 if c.get('is_tet_run_up') else 1.1 if c.get('is_public_holiday') else 1
 rain=.95 if weather.get(d,{}).get('rain_mm',0)>=10 else 1
 qty=rounded(n*local*event*rain,f'V607Q|{i}')
 if d<'2022-01-01':warmcount[d,sku]+=qty;continue
 if d not in calendar:continue
 # Preserve transaction order within SKU/day, compress 75% source-time quantile to 17-22.
 t=r['time'];m=int(t[:2])*60+int(t[3:5]);x=min(.9999,max(0,(m-360)/900));mapped=480+int(540*x/.25) if x<.25 else 1020+int(300*(x-.25)/.75)
 # Actual 75% late routing is deterministic per source unit, avoiding an unsupported French clock fit.
 alloc=defaultdict(int)
 for j in range(qty):
  v=u(f'V607TIME|{i}|{j}');slot=36+int((v/.75)*20) if v<.75 else int(((v-.75)/.25)*36);alloc[slot]+=1
 for slot,count in alloc.items():market[d,sku][slot]['base_intent_qty']+=count
 lineage.append(dict(source_row_id=i,source_date=d,source_time=t,source_article=r['article'],source_qty=n,sku_code=sku,scenario_qty=qty,weekday_factor_assumed=local,event_factor_assumed=event,rain_factor_assumed=rain,time_mapping='DETERMINISTIC_UNIT_ROUTING_75PCT_AFTER17_ASSUMED'))
for vs in market.values():
 for v in vs:v['discount_sensitive_pool_qty']=v['base_intent_qty'] # potential browsers, not purchases or true counted visitors
warm=[dict(date=d,sku_code=s,prepared_qty=warmcount[d,s],sold_qty=warmcount[d,s],refill_qty=0,waste_qty=0,stockout_day_flag=0,censored_demand_flag=0) for d in warmdates for s in codes]
write(B/'warmup_assumed_history.csv',warm);write(B/'source_lineage_ALL_PRIVATE.csv',lineage)
mk=[dict(date=d,sku_code=s,**v) for (d,s),vs in market.items() for v in vs];write(B/'market_ALL_PRIVATE.csv',mk);write(B/'market_test_PRIVATE.csv',[r for r in mk if r['date'] in testdates])
# Costs are transparent engineering scenarios; quoted inputs do not establish AEON BOM.
costs=[]
for idx,r in enumerate(master):
 sku=r['sku_code'];vals=sorted(warmcount[d,sku] for d in warmdates);cap=max(12,math.ceil(vals[math.ceil(.95*len(vals))-1]*1.5/4)*4)
 for k in ['unit_price_vnd_reference','batch_size_units_assumed']:r[k]=int(r[k])
 r['markdown_price_vnd_reference']=int(r['markdown_price_vnd_reference']) if r['markdown_price_vnd_reference'] else None
 flour_g=[40,40,40,40,40,10,15][idx];butter_g=[16,16,16,16,16,4,5][idx];cheese_g=[15,15,15,15,0,8,12][idx]
 anchors=flour_g*23+butter_g*310+cheese_g*249
 filling=[1800,1200,1200,1400,2500,3500,2200][idx]
 materials=(anchors+filling)/.95;labor=1.5*35000/60;energy=.06*3152;package=450
 central=round(materials+labor+energy+package);low=round((anchors+filling*.7)/.98+1*25500/60+.03*1918+250);high=round((anchors+filling*1.5)/.90+3*50000/60+.10*5422+800)
 costs.append(dict(sku_code=sku,flour_g_assumed=flour_g,butter_g_assumed=butter_g,cream_cheese_g_assumed=cheese_g,other_ingredients_vnd_assumed=filling,yield_assumed=.95,labor_min_assumed=1.5,labor_vnd_hour_assumed=35000,energy_kwh_assumed=.06,energy_rate_benchmark_2025=3152,packaging_vnd_assumed=package,production_low_vnd_assumed=low,production_central_vnd_assumed=central,production_high_vnd_assumed=high,disposal_low_vnd_assumed=50,disposal_central_vnd_assumed=150,disposal_high_vnd_assumed=400,disposal_basis='ASSUMED_HANDLING_TRANSPORT_NOT_VERIFIED_CONTRACT',recipe_status='ILLUSTRATIVE_NOT_AEON_RECIPE',procurement_status='UNKNOWN_SUPPLIER_COST_ESPECIALLY_CREPE_REDVELVET'))
 r.update(unit_production_cost_vnd_assumed=central,unit_disposal_cost_vnd_assumed=150,cost_status='PUBLIC_INPUT_PRICES_WITH_ASSUMED_RECIPE_AND_OPERATIONS_NOT_AEON_COST',markdown_action_cost_vnd_assumed=350,daily_capacity_units_assumed=cap,max_batch_units_assumed=max(4,math.ceil(cap/16)*4),production_lead_time_minutes_assumed=120,last_production_ready_time_assumed='19:30',shelf_capacity_units_assumed=min(48,max(8,math.ceil(cap/12)*4)),shelf_refill_threshold_units_assumed=4,demand_status='ONE_TO_ONE_PASTRY_FAMILY_PROXY_WITH_ASSUMED_LOCAL_WEEKDAY_PROFILE',operating_limits_status='PREPERIOD_CAP_PROXY_NOT_VERIFIED_OVEN_LIMIT')
write(D/'cost_components_ASSUMED.csv',costs);masters={r['sku_code']:r for r in master}
config=dict(release='V6.07',source_days=233,sku_count=7,no_model_training=True,official_test_not_executed=True,price_cap_pct=50,price_quantum_vnd=1,baseline_order_policy='WEEKLY_COMMITTED_PRIOR28_SAME_WEEKDAY_MEAN_PLUS_HALF_SD_BATCH_ROUNDING',baseline_markdown='SELECTIVE_SURVEY_REFERENCE_AT21_HOLD_UNTIL22',weekday_target_profile_assumed=localweek,weekday_normalization='DEC2021_SHRUNK_SOURCE_PROFILE',after17_probability_assumed=.75,price_response_scenarios_assumed={'null':0,'weak':.25,'central':.6,'strong':1},browser_pool_per_base_intent_assumed=1,default_price_response_strength=.6,early_markdown_evidence='SIMULATION_EXPLORATION_ONLY_NOT_AEON_CAUSAL_DATA',cost_status='BENCHMARK_INPUTS_ASSUMED_RECIPES_NOT_ACTUAL_AEON',holdout_status='ISOLATED_SIMULATED_EVALUATION_NOT_NEW_UNSEEN_REAL_AEON_HOLDOUT',weather='PRIOR_DAY_REANALYSIS_NOT_ISSUED_FORECAST',overnight='SAME_DAY_EXPIRY_ASSUMED_UNVERIFIED_FOR_PACKAGED_SKUS')
for folder in (B,T,E):write(folder/'sku_master.csv',master);js(folder/'build_config.json',config)
contract=json.loads((OLD/'02_TRAIN_VALIDATION/feature_contract.json').read_text());contract.update(version='V6.07',price_actions='Any finite0..50 percent OR exact integer VND cash price; actual cap50%; pending approval',exploration='Separate assumed scenarios, grouped by source date, never count replicas as independent days')
for folder in (B,T,E):js(folder/'feature_contract.json',contract)
session=Session(market,{d:calendar[d] for d in devdates},masters,warm,weather,branches=('BASELINE',),mode='DATA_BUILD',response_strength=.6)
features=[]
while True:
 if session.phase=='PREPARE':features.extend(i['morning_features'] for i in session.context('BASELINE')['items'])
 if session.phase=='CLOSED' and session.day_index+1==len(devdates):break
 session.advance()
daily=session.observed_daily;slots=session.closed_intervals;pos=session.closed_pos;cp=session.checkpoints
write(B/'baseline_development_OBSERVED.csv',daily);write(B/'development_scoring_PRIVATE.csv',session.private_results);write(B/'baseline_development_price_approvals.csv',session.price_events)
groups=defaultdict(list)
for r in slots:groups[r['date'],r['sku_code']].append(r)
labels=[]
for (d,s),vs in groups.items():
 for horizon,end in [('day','22:00'),('to_1930','19:30'),('to_2130','21:30')]:
  z=[r for r in vs if r['time']<end];c=int(any(r['observed_censored_interval_flag'] for r in z));lb=sum(r['sold_qty'] for r in z)
  labels.append(dict(date=d,sku_code=s,target_horizon=horizon,served_sales_lower_bound=lb,demand_right_censored=c,demand_exact_observed_if_uncensored=None if c else lb,true_demand_upper_bound=None if c else lb,label_available_at=stamp(d,end)))
for split,ds in [('fit',fitdates),('validation',[d for d in devdates if d not in fitdates])]:
 target=T/split;target.mkdir(exist_ok=True)
 for name,data in [('m2_morning_features.csv',features),('baseline_daily_OBSERVED.csv',daily),('observed_15min.csv',slots),('simulated_POS.csv',pos),('m2_censor_aware_targets.csv',labels)]:write(target/name,[r for r in data if r['date'] in ds])
 selected=[r for r in cp if r['date'] in ds];write(target/'m1_checkpoint_features.csv',[{k:v for k,v in r.items() if not k.startswith('logged_')} for r in selected]);write(target/'m1_logged_actions_TREATMENT_ONLY.csv',[{k:r[k] for k in ['date','sku_code','time','logged_requested_discount_pct','logged_action_discount_pct','logged_unit_price_vnd']} for r in selected])
 rewards=[]
 for r in selected:
  z=[v for v in groups[r['date'],r['sku_code']] if minute(r['time'])<=minute(v['time'])<minute(r['time'])+30];end=minute(r['time'])+30
  rewards.append(dict(date=r['date'],sku_code=r['sku_code'],time=r['time'],sold_next30_observed=sum(v['sold_qty'] for v in z),revenue_next30_observed_vnd=sum(v['revenue_vnd'] for v in z),reward_available_at=stamp(r['date'],f'{end//60:02d}:{end%60:02d}'),label_status='LOGGED_SIMULATED_BASELINE_NOT_CAUSAL_AEON'))
 write(target/'m1_outcomes_LABELS_ONLY.csv',rewards)
write(E/'history_seed_through_20220630.csv',[{k:r[k] for k in warm[0]} for r in daily if r['date']>='2022-06-01']);write(E/'calendar_test.csv',[calendar[d] for d in testdates]);write(E/'prior_weather_through_20220630.csv',[dict(date=d,**r) for d,r in sorted(weather.items()) if d<='2022-06-30'])
write(E/'TEST_market_commitment.csv',[dict(private_file='market_test_PRIVATE.csv',sha256=hashlib.sha256((B/'market_test_PRIVATE.csv').read_bytes()).hexdigest())])
# Randomized behavioral rollouts, fit dates only. All branches see their OWN history.
explore=[];explore_labels=[]
for scenario,strength in config['price_response_scenarios_assumed'].items():
 se=Session(market,{d:calendar[d] for d in fitdates},masters,warm,weather,branches=('M1_ONLY',),mode='DATA_BUILD',response_strength=strength)
 decisions=[]
 while True:
  if se.phase=='OPEN' and se.time in ('19:30','20:00','20:30','21:00','21:30'):
   for item in se.context('M1_ONLY')['items']:
    sku=item['sku_code'];st=se.states['M1_ONLY',sku];pace=max(item['sold_last_30min']/30,item['sold_last_60min']/60);risk=max(0,st.inventory-pace*(1320-minute(se.time)))
    choices={st.price['approved_unit_price_vnd']}
    if risk>0 and st.inventory>0 and (not st.last_change or minute(se.time)-minute(st.last_change)>=30):
     for discount in (5,10,15,20,25,30,40,50):
      try:choices.add(quote_price(masters[sku]['unit_price_vnd_reference'],discount,st.price['approved_unit_price_vnd'],st.floor)['approved_unit_price_vnd'])
      except ValueError:pass
    choices=sorted(choices,reverse=True);ix=min(len(choices)-1,int(u(f'ACTION|{scenario}|{se.day}|{sku}|{se.time}')*len(choices)));cash=choices[ix]
    if cash!=st.price['approved_unit_price_vnd']:
     prop=se.propose_price('M1_ONLY',sku,approved_cash_price_vnd=cash);se.approve(prop['id'])
    key=f'{scenario}|{se.day}|{sku}|{se.time}'
    row=dict(sample_id=key,scenario_id=scenario,source_date_group=se.day,date=se.day,sku_code=sku,time=se.time,decision_at=se.clock,prepared_qty=item['prepared_qty'],inventory_at_decision=item['inventory_at_decision'],sold_last_30min=item['sold_last_30min'],sold_last_60min=item['sold_last_60min'],shelf_inventory=item['shelf_inventory'],backroom_inventory=item['backroom_inventory'],previous_discount_pct=item['current_discount_pct'],baseline_announced_2100_pct=item['baseline_announced_2100_pct'],action_price_vnd=cash,action_discount_pct=se.states['M1_ONLY',sku].price['approved_discount_pct'],behavior_propensity=1/len(choices),feasible_price_set_json=json.dumps(choices),evidence_status='ASSUMED_RANDOMIZED_SIMULATOR_NOT_REAL_PRICE_EXPERIMENT')
    decisions.append(row)
  if se.phase=='CLOSED' and se.day_index+1==len(fitdates):break
  se.advance()
 by=defaultdict(list)
 for r in se.closed_intervals:by[r['date'],r['sku_code']].append(r)
 for row in decisions:
  end=minute(row['time'])+30;vs=[r for r in by[row['date'],row['sku_code']] if minute(row['time'])<=minute(r['time'])<end]
  explore.append(row);explore_labels.append(dict(sample_id=row['sample_id'],sold_next30_observed=sum(r['sold_qty'] for r in vs),revenue_next30_observed_vnd=sum(r['revenue_vnd'] for r in vs),censored_next30=int(any(r['observed_censored_interval_flag'] for r in vs)),label_available_at=stamp(row['date'],f'{end//60:02d}:{end%60:02d}')))
xp=T/'fit/EXPLORATION_ASSUMED';xp.mkdir(exist_ok=True)
actionkeys={'action_price_vnd','action_discount_pct','behavior_propensity','feasible_price_set_json'}
write(xp/'features_PRE_ACTION.csv',[{k:v for k,v in r.items() if k not in actionkeys} for r in explore]);write(xp/'actions_TREATMENT.csv',[{k:v for k,v in r.items() if k in actionkeys or k=='sample_id'} for r in explore]);write(xp/'outcomes_LABELS_ONLY.csv',explore_labels)
summary=[]
for split,ds in [('fit',fitdates),('validation',[d for d in devdates if d not in fitdates])]:
 z=[r for r in daily if r['date'] in ds];summary.append(dict(split=split,sku_days=len(z),prepared=sum(r['prepared_qty'] for r in z),sold=sum(r['sold_qty'] for r in z),waste=sum(r['waste_qty'] for r in z),censored_days=sum(r['censored_demand_flag'] for r in z),revenue_vnd=sum(r['revenue_vnd'] for r in z),wasted_production_cost_vnd_assumed=sum(r['wasted_production_cost_vnd_assumed'] for r in z),disposal_cost_vnd_assumed=sum(r['disposal_cost_vnd_assumed'] for r in z),contribution_vnd_assumed=sum(r['contribution_vnd_assumed'] for r in z)))
write(D/'baseline_development_cost_summary.csv',summary)
week=[]
for dow in range(7):
 ds=[d for d in devdates if date.fromisoformat(d).weekday()==dow];z=[r for r in daily if r['date'] in ds];week.append(dict(weekday_iso=dow+1,development_days=len(ds),sold_daily_mean=sum(r['sold_qty'] for r in z)/len(ds),scenario_base_intent_daily_mean=sum(v['base_intent_qty'] for (d,s),vs in market.items() if d in ds for v in vs)/len(ds),target_relative_profile_assumed=localweek[dow]))
write(D/'weekday_development_audit.csv',week)
js(D/'BUILD_STATS.json',dict(source_days=len(dates),fit_days=len(fitdates),validation_days=len(devdates)-len(fitdates),test_days=len(testdates),exploration_rows=len(explore),exploration_early_nonhold=sum(r['time']<'21:00' and r['action_discount_pct']>r['previous_discount_pct'] for r in explore),baseline_development=summary,official_test_executed=False))
print((D/'BUILD_STATS.json').read_text())

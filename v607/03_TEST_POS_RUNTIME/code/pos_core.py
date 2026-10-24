"""V6.07 source-anchored POS. Public context contains ONLY observed as-of state.
Market/customer-response information belongs to the custodian process.
"""
from dataclasses import dataclass,field
from datetime import datetime,timedelta,date
from copy import deepcopy
from decimal import Decimal,ROUND_HALF_UP,ROUND_CEILING,ROUND_FLOOR
import math,hashlib,csv,json,statistics
from context_tools import event_context
from features_asof import m2_features
BRANCHES=('BASELINE','M1_ONLY','M2_ONLY','JOINT_M1_M2')
CHECKPOINTS=('19:30','20:00','20:30','21:00','21:30')
MENU=(0,10,15,20,25,30,35,40,45,50)
HISTORY_FIELDS=('date','sku_code','prepared_qty','sold_qty','refill_qty','waste_qty','stockout_day_flag','censored_demand_flag')
def minute(t):h,m=map(int,t.split(':'));return h*60+m
def stamp(d,t):return d+'T'+t+':00+07:00'
def integer(v):
 if isinstance(v,bool) or not math.isfinite(float(v)) or int(float(v))!=float(v):raise ValueError('Quantity must be a finite integer')
 return int(float(v))
def quote_cash_price(list_price,cash,current_price=None,floor_discount=0):
 """Exact approved cash price; HOLD retains surveyed list price, including hundreds.
 Discounted action prices are integer VND. Bounds use exact Decimal arithmetic.
 """
 p=integer(list_price);cash=integer(cash);floor=Decimal(str(floor_discount))
 if p<=0 or not 0<=floor<=50:raise ValueError('Invalid list price or published floor')
 if cash<=0 or cash>p:raise ValueError('Cash price must be a positive integer no greater than list price')
 eff=(Decimal(p)-cash)*100/Decimal(p)
 if eff>50 or eff+Decimal('0.000000001')<floor:raise ValueError('Cash price violates maximum discount or published floor')
 if current_price is not None and cash>integer(current_price):raise ValueError('Cash price increase is forbidden')
 return dict(list_price_vnd=p,requested_discount_pct=None,approved_unit_price_vnd=cash,approved_discount_pct=float(eff),discount_amount_vnd=p-cash,price_quantum_vnd=1,rounding_status='EXACT_CASH_PRICE_AND_EFFECTIVE_DISCOUNT_REQUIRE_JOINT_APPROVAL')
def quote_price(list_price,requested,current_price=None,floor_discount=0):
 """Nominal-menu compatibility; exact HOLD, integer VND discounted prices."""
 p=integer(list_price);floor=Decimal(str(floor_discount))
 if p<=0 or isinstance(requested,bool) or not math.isfinite(float(requested)) or not 0<=float(requested)<=50:raise ValueError('Invalid list price or requested discount menu')
 if not 0<=floor<=50:raise ValueError('Invalid published floor')
 if requested==0:
  cash=integer(current_price) if current_price is not None else p
  try:
   q=quote_cash_price(p,cash,current_price,floor);q['requested_discount_pct']=0;return q
  except ValueError:pass
 lo=int((Decimal(p)*Decimal('.5')).to_integral_value(rounding=ROUND_CEILING))
 hi=int((Decimal(p)*(1-floor/100)).to_integral_value(rounding=ROUND_FLOOR))
 if current_price is not None:hi=min(hi,integer(current_price))
 if lo>hi:raise ValueError('No integer VND price satisfies published bounds')
 cash=min(hi,max(lo,int((Decimal(p)*(1-Decimal(str(requested))/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))))
 q=quote_cash_price(p,cash,current_price,floor);q['requested_discount_pct']=float(requested);return q
def event_factor(d):
 if d<'2022-01-01':return 1.
 c=event_context(d)
 return 1.15 if c['event_stratum']=='tet_run_up' else 1.10 if c['event_stratum'] in ('tet_official','public_holiday') else 1.
def manual_discount(st,t):
 if t<'21:00' or st.inventory<=0:return 0
 pace=max(sum(n for m,n in st.sales if minute(t)-30<=m<minute(t))/30,sum(n for m,n in st.sales if minute(t)-60<=m<minute(t))/60)
 residual=max(0,st.inventory-pace*(1320-minute(t)));ratio=residual/max(1,st.produced)
 for threshold,d in zip((.08,.20,.35,.50),(0,20,30,40)):
  if ratio<=threshold:return d
 return 50
@dataclass
class State:
 plan:dict;price:dict;shelf:int=0;back:int=0;produced:int=0;sold:int=0;refill:int=0;revenue:int=0
 sales:list=field(default_factory=list);pos:list=field(default_factory=list);intervals:list=field(default_factory=list)
 lost_base:int=0;lost_promo:int=0;first_unserved:str='';censored:int=0;floor:float=0.;price_version:int=0;last_change:str='';batches:list=field(default_factory=list)
 @property
 def inventory(self):return self.shelf+self.back
class Session:
 def __init__(self,market,calendar,master,history,weather=None,branches=BRANCHES,mode='DEMO',response_strength=0.):
  if mode not in ('DEMO','FROZEN','DATA_BUILD'):raise ValueError('Unknown mode')
  self._market=market;self.calendar=calendar;self.master=master;self.weather=weather or {};self.branches=tuple(branches);self.mode=mode;self._response=float(response_strength)
  if not 0<=self._response<=1:raise ValueError('Invalid private scenario response')
  self.dates=sorted(calendar);self.day_index=0;self.hist={(b,s):[{k:deepcopy(r[k]) for k in HISTORY_FIELDS} for r in history if r['sku_code']==s] for b in branches for s in master}
  for h in self.hist.values():
   h.sort(key=lambda r:r['date'])
   if any(r['date']>=self.dates[0] for r in h):raise ValueError('Initial history includes target/future date')
  self.private_results=[];self.observed_daily=[];self.checkpoints=[];self.closed_pos=[];self.closed_intervals=[];self.audit=[];self.proposals={};self.price_events=[];self.states={};self._new_day()
 @property
 def day(self):return self.dates[self.day_index]
 @property
 def clock(self):return stamp(self.day,self.time)
 def _new_day(self):
  self.phase='PREPARE';self.time='06:00';self.slot=0;self.states={};self.plans={};self.proposals={}
  for b in self.branches:
   for sku in self.master:
    if b in ('BASELINE','M1_ONLY') or self.mode in ('DEMO','DATA_BUILD'):
     self.plans[b,sku]={'initial_qty':self.baseline_qty(b,sku),'production_batches':[],'policy_status':'ASSUMED_BASELINE' if b in ('BASELINE','M1_ONLY') else 'DEMO_PLACEHOLDER_NOT_TRAINED_M2'}
 def baseline_qty(self,b,sku):
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
 def _validate_plan(self,sku,plan):
  spec=self.master[sku];batch=int(spec['batch_size_units_assumed']);initial=integer(plan['initial_qty']);bs=deepcopy(plan.get('production_batches',[]));total=initial
  if initial<0 or initial%batch:raise ValueError('Plan quantities must be nonnegative batch multiples')
  for r in bs:
   r['qty']=integer(r['qty']);total+=r['qty']
   if r['qty']<=0 or r['qty']%batch or r['qty']>int(spec['max_batch_units_assumed']):raise ValueError('Invalid production batch')
   if minute(r['ready_time'])-minute(r['order_time'])<int(spec['production_lead_time_minutes_assumed']):raise ValueError('Production leadtime not satisfied')
   if r['ready_time']<'08:00' or r['ready_time']>spec['last_production_ready_time_assumed'] or minute(r['ready_time'])%15:raise ValueError('Invalid ready time')
  if total>int(spec['daily_capacity_units_assumed']):raise ValueError('Declared scenario daily capacity exceeded')
  return dict(initial_qty=initial,production_batches=bs,policy_status=plan.get('policy_status','EXTERNAL_POLICY_OR_MANAGER'))
 def prepare(self,b,sku,plan):
  if self.phase!='PREPARE':raise ValueError('Preparation plan can only be submitted before opening')
  if self.mode=='FROZEN' and b in ('BASELINE','M1_ONLY'):raise ValueError('Frozen baseline-preparation branches cannot be overridden')
  if b not in self.branches or sku not in self.master:raise ValueError('Unknown branch/SKU')
  self.plans[b,sku]=self._validate_plan(sku,plan);self.audit.append(dict(event='PREPARATION_PLAN_COMMITTED',date=self.day,time=self.time,branch=b,sku_code=sku,plan=deepcopy(self.plans[b,sku])))
 def schedule_batch(self,b,sku,qty,ready_time):
  if self.phase!='OPEN' or b not in ('M2_ONLY','JOINT_M1_M2'):raise ValueError('Only open M2 branches can schedule adaptive production')
  if sku not in self.master:raise ValueError('Unknown SKU')
  st=self.states[b,sku]
  batch=dict(qty=integer(qty),order_time=self.time,ready_time=ready_time)
  plan=deepcopy(st.plan);plan['production_batches'].append(batch)
  checked=self._validate_plan(sku,plan)
  st.plan=checked;st.batches.append(batch);self.plans[b,sku]=deepcopy(checked)
  self.audit.append(dict(event='ADAPTIVE_BATCH_COMMITTED',date=self.day,time=self.time,branch=b,sku_code=sku,production_batch=deepcopy(batch)))
  return deepcopy(batch)
 def _open(self):
  missing=[f'{b}/{s}' for b in self.branches for s in self.master if (b,s) not in self.plans]
  if missing:raise ValueError('Missing frozen M2 plans: '+','.join(missing))
  for (b,s),p in self.plans.items():
   p=self._validate_plan(s,p);spec=self.master[s];n=p['initial_qty'];q=quote_price(spec['unit_price_vnd_reference'],0)
   self.states[b,s]=State(p,q,shelf=min(n,int(spec['shelf_capacity_units_assumed'])),back=max(0,n-int(spec['shelf_capacity_units_assumed'])),produced=n,batches=deepcopy(p['production_batches']))
  self.phase='OPEN';self.time='08:00';self._enter_time()
 def _apply(self,b,s,quote,source,proposal_id=''):
  st=self.states[b,s]
  if quote['approved_unit_price_vnd']>st.price['approved_unit_price_vnd'] or quote['approved_discount_pct']+1e-9<st.floor:raise ValueError('Price increase or published floor violation')
  if quote['approved_unit_price_vnd']!=st.price['approved_unit_price_vnd']:
   if st.last_change and minute(self.time)-minute(st.last_change)<30:raise ValueError('RuleC: price changed within30minutes')
   st.price_version+=1;st.last_change=self.time
  st.price=deepcopy(quote)
  e=dict(date=self.day,branch=b,sku_code=s,approved_at=self.clock,effective_at=self.clock,price_version=st.price_version,approval_source=source,proposal_id=proposal_id,**quote);self.price_events.append(e);self.audit.append(dict(event='PRICE_APPROVAL_APPLIED',**e))
 def _enter_time(self):
  # Ready production becomes observed stock BEFORE pricing/manager contexts at this timestamp.
  for st in self.states.values():
   for r in [r for r in st.batches if r['ready_time']<=self.time]:
    st.back+=r['qty'];st.produced+=r['qty'];st.batches.remove(r)
  if self.time in CHECKPOINTS:
   for (b,s),st in self.states.items():
    self.checkpoints.append(dict(date=self.day,branch=b,sku_code=s,time=self.time,decision_at=self.clock,prepared_qty=st.plan['initial_qty']+sum(r['qty'] for r in st.plan['production_batches']),inventory_at_decision=st.inventory,shelf_inventory=st.shelf,backroom_inventory=st.back,sold_last_30min=sum(n for m,n in st.sales if minute(self.time)-30<=m<minute(self.time)),sold_last_60min=sum(n for m,n in st.sales if minute(self.time)-60<=m<minute(self.time)),previous_discount_pct=st.price['approved_discount_pct'],previous_unit_price_vnd=st.price['approved_unit_price_vnd'],baseline_announced_2100_pct=None))
  # Baseline is a preapproved comparator rule, not an AI model recommendation.
  if self.time=='21:00':
   for b in self.branches:
    for s,spec in self.master.items():
     st=self.states[b,s]
     if not st.inventory:continue
     if 'markdown_price_vnd_reference' not in spec:
      q=quote_price(spec['unit_price_vnd_reference'],manual_discount(st,self.time),st.price['approved_unit_price_vnd'])
     else:
      ref=spec.get('markdown_price_vnd_reference')
      selective_surplus=manual_discount(st,self.time)>0
      # Missing reference prices mean HOLD in this declared scenario, not a universal ban.
      q=quote_cash_price(spec['unit_price_vnd_reference'],min(st.price['approved_unit_price_vnd'],int(ref)),st.price['approved_unit_price_vnd']) if ref and selective_surplus else quote_price(spec['unit_price_vnd_reference'],0,st.price['approved_unit_price_vnd'])
     st.floor=q['approved_discount_pct']
     next(r for r in reversed(self.checkpoints) if r['branch']==b and r['sku_code']==s and r['date']==self.day and r['time']==self.time)['baseline_announced_2100_pct']=st.floor
     self._apply(b,s,q,'SIMULATED_PREAPPROVED_SELECTIVE_BASELINE_2100')
  for pid,p in list(self.proposals.items()):
   if p['status']=='APPROVED_SCHEDULED' and p['effective_at']==self.clock:
    b,s=p['branch'],p['sku_code'];st=self.states[b,s]
    try:
     if st.inventory<=0:raise ValueError('Sold-out SKU; scheduled markdown invalidated')
     if p['base_price_version']!=st.price_version:raise ValueError('Stale priceversion; requote')
     self._apply(b,s,p['quote'],'MANAGER_APPROVAL',pid);p['status']='APPLIED'
    except ValueError as e:p['status']='INVALIDATED_REQUOTE_REQUIRED';p['reason']=str(e)
 def propose_price(self,b,s,requested=None,effective_time=None,approved_cash_price_vnd=None):
  if self.phase!='OPEN' or b not in ('M1_ONLY','JOINT_M1_M2'):raise ValueError('Only open AI-pricing branches accept proposals')
  st=self.states[b,s]
  if st.inventory<=0:raise ValueError('Sold-out SKU: no new markdown sticker')
  t=effective_time or next((t for t in CHECKPOINTS if t>=self.time),None)
  if t not in CHECKPOINTS or t<self.time:raise ValueError('Choose a current/future30mincheckpoint')
  if t>='21:00' and self.time<'21:00':raise ValueError('21:00floor not known yet; propose again at21:00')
  if (requested is None)==(approved_cash_price_vnd is None):raise ValueError('Supply exactly one nominal discount or cash price')
  q=quote_cash_price(self.master[s]['unit_price_vnd_reference'],approved_cash_price_vnd,st.price['approved_unit_price_vnd'],st.floor) if approved_cash_price_vnd is not None else quote_price(self.master[s]['unit_price_vnd_reference'],requested,st.price['approved_unit_price_vnd'],st.floor)
  pid=f'{self.day}:{b}:{s}:{len(self.audit)}';p=dict(id=pid,date=self.day,branch=b,sku_code=s,proposed_at=self.clock,effective_at=stamp(self.day,t),base_price_version=st.price_version,status='PENDING',quote=q)
  self.proposals[pid]=p;self.audit.append(dict(event='PRICE_PROPOSED_NOT_APPLIED',**deepcopy(p)));return deepcopy(p)
 def approve(self,pid,accepted=True):
  if pid not in self.proposals:raise ValueError('Unknown proposal')
  p=self.proposals[pid]
  if p['status']!='PENDING':raise ValueError('Proposal is not pending')
  if not accepted:p['status']='REJECTED';self.audit.append(dict(event='PRICE_REJECTED',proposal_id=pid,at=self.clock));return deepcopy(p)
  b,s=p['branch'],p['sku_code'];st=self.states[b,s]
  if p['effective_at']<self.clock or p['base_price_version']!=st.price_version:raise ValueError('Stale proposal; request a new quote')
  if st.inventory<=0:raise ValueError('SKU is sold out')
  p['approved_at']=self.clock
  if p['effective_at']==self.clock:self._apply(b,s,p['quote'],'MANAGER_APPROVAL',pid);p['status']='APPLIED'
  else:p['status']='APPROVED_SCHEDULED'
  return deepcopy(p)
 def advance(self):
  if self.phase=='PREPARE':self._open();return
  if self.phase=='CLOSED':
   if self.day_index+1>=len(self.dates):raise ValueError('End of source-supported dates')
   self.day_index+=1;self._new_day();return
  t=self.time
  if t in CHECKPOINTS:
   for r in reversed(self.checkpoints):
    if r['date']!=self.day or r['time']!=t:break
    st=self.states[r['branch'],r['sku_code']];r['logged_requested_discount_pct']=st.price['requested_discount_pct'];r['logged_action_discount_pct']=st.price['approved_discount_pct'];r['logged_unit_price_vnd']=st.price['approved_unit_price_vnd']
  for b in self.branches:
   for s,spec in self.master.items():
    st=self.states[b,s];ev=self._market[self.day,s][self.slot];base=int(ev['base_intent_qty']);pool=int(ev.get('discount_sensitive_pool_qty',0));effective=st.price['approved_discount_pct']
    done=[r for r in st.batches if r['ready_time']<=t]
    for r in done:st.back+=r['qty'];st.produced+=r['qty'];st.batches.remove(r)
    before=st.inventory;refill=0;sold=0;lb=lp=0
    for j in range(base+pool):
     # Stable potential-customer timestamp/U across branches, never shown before occurrence.
     token=f'V604|{self.day}|{s}|{t}|{j}';u=int(hashlib.sha256(token.encode()).hexdigest()[:13],16)/16**13
     promo=j>=base
     if promo and u>=self._response*effective/100:continue
     if st.shelf<=int(spec['shelf_refill_threshold_units_assumed']) and st.back:
      n=min(st.back,int(spec['shelf_capacity_units_assumed'])-st.shelf);st.shelf+=n;st.back-=n;refill+=n
     second=max(1,int((j+1)*900/(base+pool+1)));at=(datetime.fromisoformat(self.day+'T'+t)+timedelta(seconds=second)).isoformat()+'+07:00'
     if st.shelf:
      st.shelf-=1;st.sold+=1;sold+=1;price=st.price['approved_unit_price_vnd'];st.revenue+=price
      st.pos.append(dict(date=self.day,branch=b,sku_code=s,transaction_at=at,available_at=at,quantity=1,list_price_vnd=spec['unit_price_vnd_reference'],unit_price_vnd=price,discount_pct=effective,requested_discount_pct=st.price['requested_discount_pct'],discount_amount_vnd=st.price['discount_amount_vnd'],amount_vnd=price,price_version=st.price_version,source_status='SIMULATED_NOT_AEON_POS'))
     else:
      if promo:lp+=1
      else:lb+=1
      if not st.first_unserved:st.first_unserved=at
    end=(datetime.fromisoformat(self.day+'T'+t)+timedelta(minutes=15)).isoformat()+'+07:00';c=int(st.inventory==0)
    st.refill+=refill;st.sales.append((minute(t),sold));st.lost_base+=lb;st.lost_promo+=lp;st.censored=max(st.censored,c)
    st.intervals.append(dict(date=self.day,branch=b,sku_code=s,time=t,interval_start=stamp(self.day,t),available_at=end,inventory_start=before,produced_qty_so_far=st.produced,sold_qty=sold,shelf_stock_end=st.shelf,backroom_stock_end=st.back,inventory_end=st.inventory,refill_transfer_qty=refill,discount_pct=effective,unit_price_vnd=st.price['approved_unit_price_vnd'],revenue_vnd=sold*st.price['approved_unit_price_vnd'],observed_censored_interval_flag=c))
  self.slot+=1
  if self.slot==56:self.time='22:00';self.phase='CLOSED';self._close()
  else:self.time=f'{8+self.slot//4:02d}:{15*(self.slot%4):02d}';self._enter_time()
 def _close(self):
  for (b,s),st in self.states.items():
   if st.batches:raise AssertionError('Production batch not ready byclose')
   spec=self.master[s];row=dict(date=self.day,branch=b,sku_code=s,prepared_qty=st.produced,sold_qty=st.sold,refill_qty=st.refill,waste_qty=st.inventory,stockout_day_flag=st.censored,censored_demand_flag=st.censored,revenue_vnd=st.revenue,production_cost_vnd_assumed=st.produced*spec['unit_production_cost_vnd_assumed'] if spec['unit_production_cost_vnd_assumed'] is not None else None,disposal_cost_vnd_assumed=st.inventory*spec['unit_disposal_cost_vnd_assumed'] if spec['unit_disposal_cost_vnd_assumed'] is not None else None,inventory_balance_error=st.produced-st.sold-st.inventory,observed_at=self.clock,data_status='V607_SURVEY_PRICE_FAMILY_PROXY_ASSUMED_OPERATIONS_NOT_AEON_POS')
   changes=len({e['price_version'] for e in self.price_events if e['date']==self.day and e['branch']==b and e['sku_code']==s and e['price_version']>0})
   row['markdown_operations_cost_vnd_assumed']=changes*int(spec.get('markdown_action_cost_vnd_assumed',0))
   row['wasted_production_cost_vnd_assumed']=st.inventory*spec['unit_production_cost_vnd_assumed'] if spec['unit_production_cost_vnd_assumed'] is not None else None
   row['contribution_vnd_assumed']=row['revenue_vnd']-row['production_cost_vnd_assumed']-row['disposal_cost_vnd_assumed']-row['markdown_operations_cost_vnd_assumed'] if row['production_cost_vnd_assumed'] is not None and row['disposal_cost_vnd_assumed'] is not None else None
   if row['inventory_balance_error']:raise AssertionError('Inventory failed conservation')
   self.closed_pos.extend(st.pos);self.closed_intervals.extend(st.intervals);self.observed_daily.append(row);self.hist[b,s].append({k:row[k] for k in HISTORY_FIELDS});self.private_results.append(dict(**row,lost_base_hidden_scenario=st.lost_base,lost_promo_hidden_scenario=st.lost_promo,first_unserved_hidden=st.first_unserved))
 def context(self,b):
  if b not in self.branches:raise ValueError('Unknown branch')
  c=self.calendar[self.day];items=[];prev=str(date.fromisoformat(self.day)-timedelta(days=1));w=self.weather.get(prev,{})
  for s,spec in self.master.items():
   h=deepcopy([r for r in self.hist[b,s] if r['date']<self.day]);ctx={**c,'date':self.day,'sku_code':s,'sku_master':deepcopy(spec),'completed_branch_history':h,'decision_at':stamp(self.day,'06:00'),'weather_prior_day':w}
   f=m2_features(ctx);st=self.states.get((b,s));d=dict(sku_code=s,product_name=spec['product_name_reference'],list_price_vnd=spec['unit_price_vnd_reference'],markdown_price_vnd_reference=spec.get('markdown_price_vnd_reference'),price_evidence_status='USER_FIELD_SURVEY',morning_features=f,completed_branch_history=h,preparation_plan=deepcopy(self.plans.get((b,s))))
   if st:
    d.update(prepared_qty=st.plan['initial_qty']+sum(r['qty'] for r in st.plan['production_batches']),produced_qty_so_far=st.produced,inventory_at_decision=st.inventory,shelf_inventory=st.shelf,backroom_inventory=st.back,sold_last_30min=sum(n for m,n in st.sales if minute(self.time)-30<=m<minute(self.time)),sold_last_60min=sum(n for m,n in st.sales if minute(self.time)-60<=m<minute(self.time)),current_discount_pct=st.price['approved_discount_pct'],current_unit_price_vnd=st.price['approved_unit_price_vnd'],current_discount_amount_vnd=st.price['discount_amount_vnd'],baseline_announced_2100_pct=st.floor if self.time>='21:00' else None,price_version=st.price_version,observed_intervals=deepcopy(st.intervals[-4:]),recent_transactions=deepcopy(st.pos[-10:]))
   items.append(d)
  return dict(date=self.day,as_of=self.clock,time=self.time,phase=self.phase,branch=b,mode=self.mode,items=items)
 def manager_state(self):return dict(clock=self.clock,phase=self.phase,mode=self.mode,branches={b:self.context(b) for b in self.branches},proposals=deepcopy(list(self.proposals.values())),price_events=deepcopy(self.price_events[-30:]),audit=deepcopy(self.audit[-50:]))

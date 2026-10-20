#!/usr/bin/env python3
"""JSON-lines protocol: only released forecast, past sales and current stock."""
import sys,json,os,io,builtins
from pathlib import Path
MODEL = Path(__file__).resolve().parent
PROJECT = MODEL.parent
ALLOWED = {MODEL/'policy.py', MODEL/'worker.py', MODEL/'selection_manifest.json', PROJECT/'01_Dataset_moi/history_through_aug15_synthetic.csv', *list((MODEL/'models').glob('*.joblib'))}
READS=set()
def check_path(file, writing=False):
 if isinstance(file, int):return
 p=Path(file).resolve()
 if PROJECT == p or PROJECT in p.parents or Path('/workspace') in p.parents:
  if writing or p not in ALLOWED:raise PermissionError('Model process cannot access project file: '+str(p))
  READS.add(p.relative_to(PROJECT).as_posix())
original_open=builtins.open
def guarded_open(file,mode='r',*a,**k):
 check_path(file, any(c in mode for c in 'wax+'));return original_open(file,mode,*a,**k)
original_io_open=io.open
def guarded_io_open(file,mode='r',*a,**k):
 check_path(file,any(c in mode for c in 'wax+'));return original_io_open(file,mode,*a,**k)
original_os_open=os.open
def guarded_os_open(file,flags,*a,**k):
 check_path(file,bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)));return original_os_open(file,flags,*a,**k)
builtins.open=guarded_open;io.open=guarded_io_open;os.open=guarded_os_open
import pandas as pd
import policy as p
selection=json.loads((p.ROOT/'selection_manifest.json').read_text())
history=pd.read_csv(p.ROOT.parent/'01_Dataset_moi/history_through_aug15_synthetic.csv')
visible={(r.date,r.sku_code):float(r.sold_qty) for r in history.itertuples()}
plans={};system=None; current_date=None; last_slot={};closed=set()
for line in sys.stdin:
 try:
  req=json.loads(line);op=req['op']
  if op=='init':
   assert system is None and req['system'] in ['M1_M2_SELECTED','BASELINE']
   system=req['system'];result={'ok':True}
  elif op=='morning':
   assert system is not None
   day=req['forecast'];d=day['date'];s=req['sku_code']
   expected={'date','weekday_iso','is_weekend','month','day_of_year','is_public_holiday','public_holiday_name','is_festival_non_public','forecast_rain_mm_previous_day1','forecast_temperature_max_c_previous_day1','forecast_source','forecast_known_by_local','holiday_source'}
   assert set(day)==expected,'Unexpected feature column'
   assert s in p.SKU and (d,s) not in plans
   assert current_date is None or d>=current_date,'Nonchronological observation'
   if current_date is not None and d>current_date:
    assert all((current_date,x) in closed for x in p.SKU),'Previous day incomplete'
   current_date=d
   assert not any(k[0]>d for k in visible),'Future historical sales'
   p.calendar=pd.DataFrame([day]).set_index('date');p.expected_promo.cache_clear()
   if system=='BASELINE':prepared=p.prep_baseline(d,s,visible);forecast=p.means[s]
   else:
    prepared,forecast=p.prepare_predict(d,s,visible,p.m2final,selection['selected_q'])
    guard=p.prep_baseline(d,s,visible)
    prepared=max(prepared,int(p.BATCH*p.math.ceil(selection['selected_prep_floor']*guard/p.BATCH)))
   plans[(d,s)]=(prepared,forecast);last_slot[(d,s)]=-1
   result={'prepared_qty':int(prepared),'forecast':float(forecast)}
  elif op=='slot':
   d=req['date'];s=req['sku_code'];j=int(req['slot']);stock=int(req['stock']);prev=int(req['previous_discount'])
   assert (d,s) not in closed and j==last_slot[(d,s)]+1 and 0<=j<5
   prepared,forecast=plans[(d,s)];assert 0<=stock<=prepared
   if system=='BASELINE':act,reason=p.base_discount(1170+30*j,j,s,stock,prepared,prev,None,None,None,None,None,None)
   else:
    act,reason=p.price_optimizer(1170+30*j,j,s,stock,prepared,prev,int(req['sales_last30']),int(req['sales_last60']),prepared-stock,forecast,p.expected_promo(d,s),p.organic_fracs)
   assert act in p.LADDER and max(prev,p.FLOORS[j])<=act<=p.CAPS[j]
   last_slot[(d,s)]=j;result={'discount_pct':int(act),'reason':reason}
  elif op=='close':
   d=req['date'];s=req['sku_code'];sold=int(req['sold_qty']);prepared,_=plans[(d,s)]
   assert (d,s) not in closed and last_slot[(d,s)]==4 and 0<=sold<=prepared
   visible[(d,s)]=sold;closed.add((d,s));result={'ok':True}
  elif op=='finish':
   result={'files_read':sorted(READS),'ok':True}
  else:raise ValueError('Unknown operation')
  print(json.dumps(result),flush=True)
  if op=='finish':break
 except Exception as ex:
  print(json.dumps({'error':type(ex).__name__+': '+str(ex)}),flush=True)
  sys.exit(1)

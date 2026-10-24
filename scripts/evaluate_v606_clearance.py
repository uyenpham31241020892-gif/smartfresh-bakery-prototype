"""Prospective sensitivity check on validation calendar, not a causal backtest.

Fixed assumptions, FIT-only purchase intensity, common random requests across branches.
Checks zero/weak/declared response; never selects elasticity using resulting revenue.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.clearance import DIRECTORY,SCENARIO,artifacts,predict,recommend


def evaluate(source,policy='v7'):
 if policy=='v8':
  from services.cautious_pricing import recommend as recommend_policy
 else:recommend_policy=recommend
 report=json.loads((DIRECTORY/'training_report.json').read_text())
 for name in ['fit/baseline_daily_OBSERVED.csv','sku_master.csv','validation/m1_checkpoint_features.csv']:
  assert hashlib.sha256((source/name).read_bytes()).hexdigest()==report['source_hashes'][name]
 fit=pd.read_csv(source/'fit/baseline_daily_OBSERVED.csv');assert fit.date.max()<='2022-04-30'
 means=fit.groupby('sku_code').sold_qty.mean().to_dict()
 master=pd.read_csv(source/'sku_master.csv').set_index('sku_code').to_dict('index')
 dates=sorted(pd.read_csv(source/'validation/m1_checkpoint_features.csv').date.unique())
 assert dates[0]>='2022-05-01' and dates[-1]<='2022-06-30'
 columns=report['columns'];results=[]
 for coefficient in [0,1,2]:
  totals={b:dict(revenue=0,sold=0,stock=0,prepared=0,lost=0,days_with_stockout_before_2130=0,changed_sku_checkpoints=0) for b in ['HOLD','POLICY']}
  for day in dates:
   rng=np.random.default_rng(int.from_bytes(hashlib.sha256(f'validation-clearance-v7:{day}:607'.encode()).digest()[:8],'little'))
   events=[];prepared={}
   for sku,mean in means.items():
    base=mean*4;prepared[sku]=4*math.ceil((base+1.64*math.sqrt(base)+4)/4)
    count=int(rng.poisson(base));early=int(rng.binomial(count,.25))
    times=np.concatenate([rng.integers(480,1020,early),rng.integers(1020,1320,count-early)])
    events.extend((int(t),sku,0,0) for t in times)
    for _ in range(int(rng.poisson(base*.375))):
     events.append((int(rng.integers(1170,1320)),sku,float(rng.uniform(0,50)),float(rng.random())))
   events.sort(key=lambda e:e[0])
   for branch in totals:
    stock=dict(prepared);discount={s:0 for s in means};sales={s:[] for s in means};sku_revenue={s:0 for s in means};revenue=lost=0;early_stockout=False
    byminute={}
    for ev in events:byminute.setdefault(ev[0],[]).append(ev)
    for minute in range(480,1320):
     if minute==1290:early_stockout=any(n<=0 for n in stock.values())
     if branch=='POLICY' and minute in [1170,1200,1230,1260,1290]:
      rows=[];counts={}
      for sku in means:
       s30=sum(t>=minute-30 for t in sales[sku]);s60=sum(t>=minute-60 for t in sales[sku]);counts[sku]=(s30,s60)
       shelf=min(stock[sku],int(master[sku]['shelf_capacity_units_assumed'])*4)
       rows.append(dict(sku_code=sku,time=f'{minute//60:02}:{minute%60:02}',prepared_qty=prepared[sku]/4,
        inventory_at_decision=stock[sku]/4,sold_last_30min=s30/4,sold_last_60min=s60/4,
        shelf_inventory=shelf/4,backroom_inventory=(stock[sku]-shelf)/4,previous_discount_pct=discount[sku],baseline_announced_2100_pct=None))
      # Batched predictions, identical pre-action contract to runtime.
      pre,models,_=artifacts();import xgboost as xgb
      dm=xgb.DMatrix(pre['preprocessor'].transform(pd.DataFrame(rows)[columns]))
      estimates={h:np.maximum(0,m.predict(dm))*4 for h,m in models.items()}
      for i,sku in enumerate(means):
       kwargs=dict(scenario=SCENARIO)
       if policy=='v8':kwargs['history']=dict(sold_today=len(sales[sku]),past_discount_value=int(master[sku]['unit_price_vnd_reference'])*len(sales[sku])-sku_revenue[sku])
       q=recommend_policy(dict(sku=sku,price=int(master[sku]['unit_price_vnd_reference']),minute=minute,stock=stock[sku],previous=discount[sku],sales30=counts[sku][0],sales60=counts[sku][1]),
                   prepared[sku],float(estimates['close'][i]),float(estimates['to2130'][i]),**kwargs)
       totals[branch]['changed_sku_checkpoints']+=q['discount']>discount[sku];discount[sku]=q['discount']
     for _,sku,required,draw in byminute.get(minute,[]):
      if required and (required>discount[sku] or draw>coefficient/2):continue
      if stock[sku]>0:
       stock[sku]-=1;sales[sku].append(minute);cash=round(int(master[sku]['unit_price_vnd_reference'])*(1-discount[sku]/100));revenue+=cash;sku_revenue[sku]+=cash
      else:lost+=1
    t=totals[branch];t['revenue']+=revenue;t['sold']+=sum(map(len,sales.values()));t['stock']+=sum(stock.values());t['prepared']+=sum(prepared.values());t['lost']+=lost;t['days_with_stockout_before_2130']+=early_stockout
  base=totals['HOLD'];p=totals['POLICY']
  results.append(dict(actual_response_coefficient=coefficient,branches=totals,revenue_change=p['revenue']-base['revenue'],
    revenue_change_pct=100*(p['revenue']-base['revenue'])/base['revenue'],closing_stock_change=p['stock']-base['stock']))
 result=dict(scope='DEVELOPMENT_SENSITIVITY_NOT_CAUSAL_OR_OFFICIAL_TEST',calendar='2022-05-01/2022-06-30',days=len(dates),seed=607,
  intensity='FIT Jan-Apr observed lower-bound means only, fixed 4x and 75% evening assumptions',
  model_assumes_response_coefficient=2,automatic_approval='OFFLINE_EVALUATION_ONLY; runtime requires manager',
  model_selection='Forecast trees selected by validation loss; response coefficient is declared, not fitted',
  policy_development='Service uncertainty guard added after development sensitivity exposed early stockouts. Validation reused; NOT an independent policy evaluation.',results=results)
 result['pricing_policy_version']=policy
 result['policy_development']='Validation reused for model selection and policy development, not an independent policy evaluation.'
 path=DIRECTORY/('late_first_sensitivity_report.json' if policy=='v8' else 'sensitivity_report.json')
 path.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--policy',choices=['v7','v8'],default='v7');args=parser.parse_args();evaluate(args.source,args.policy)

"""Train/evaluate M1 from logged synthetic POS under the actual arrival profile.

Split by calendar date before generating experiments. No July/August test events
are exposed to fitting or validation. Candidate labels are synthetic interventions,
not independently observed AEON customers or causal claims about a real store.
"""
from collections import defaultdict
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from services.volume_scenario import SCALE,arrival_second,uniform
from services.v4_features.model_features import m1_features


def build(root,preprocessor,lookup,validation=False):
    split='validation' if validation else 'fit'
    start,end=('2022-05-01','2022-06-30') if validation else ('2022-01-02','2022-04-30')
    morning=pd.read_csv(root/f'TRAINED_TESTED/02_TRAIN_VALIDATION/{split}/m2_morning_features.csv')
    morning={(r['date'],r['sku_code']):r for r in morning.to_dict('records')}
    source=root/'ORIGINAL_BASELINE_PRIVATE/customer_events_ALL_PRIVATE.jsonl'
    groups=defaultdict(list)
    extracted=root/f'data/joint/{split}_world.jsonl';extracted.parent.mkdir(parents=True,exist_ok=True)
    with source.open(encoding='utf-8') as stream,extracted.open('w',encoding='utf-8',newline='\n') as target:
        for line in stream:
            r=json.loads(line)
            if not start<=r['date']<=end or (r['date'],r['sku_code']) not in morning:continue
            target.write(line.rstrip()+'\n');groups[(r['date'],r['sku_code'])].append(r)
    rows,labels,dates,actions,censored=[],[],[],[],[]
    for (day,sku),source_rows in sorted(groups.items()):
        f=morning[(day,sku)];spec=lookup[sku]
        for scenario,ratio in enumerate((.85,1.25,1.8)):
            seed=(161 if validation else 101)+scenario
            events=[]
            for r in source_rows:
                for event in r['unit_events']:
                    for replica in range(SCALE):
                        promo=bool(event['promo']);ident=f"{event['event_id']}|x10:{replica}"
                        second=arrival_second(day,event['customer_id'],replica,seed,bool(f['is_public_holiday']),promo)
                        draw=uniform(f'{ident}|{seed}|response')
                        events.append((second//60,promo,draw,.6*float(r.get('response_multiplier_assumed',1))))
            events.sort()
            lag=f.get('sold_calendar_lag1');lag=lag if pd.notna(lag) else f['sold_last7_observed_mean']
            prepared=max(4,min(int(spec['daily_capacity_units_assumed']),math.ceil(max(lag,f['sold_last7_observed_mean'])*SCALE*ratio/4)*4))
            initial=min(prepared,math.ceil(prepared*.4/4)*4);first=(prepared-initial)//8*4
            inventory=initial;ledger=[];received=set();previous=0
            def requests(start,end,tier):
                return [m for m,p,u,response in events if start<=m<end and (not p or u<min(1.,response*(tier/50)**.9))]
            for minute in requests(480,1170,0):
                for at,amount in [(840,first),(1020,prepared-initial-first)]:
                    if minute>=at and at not in received:inventory+=amount;received.add(at)
                if inventory>0:inventory-=1;ledger.append(minute)
            for at,amount in [(840,first),(1020,prepared-initial-first)]:
                if at not in received:inventory+=amount
            for minute in (1170,1200,1230,1260,1290):
                s30=sum(minute-30<=t<minute for t in ledger);s60=sum(minute-60<=t<minute for t in ledger)
                shelf=min(inventory,spec['shelf_capacity_units_assumed'])
                item=dict(sku_code=sku,prepared_qty=prepared,inventory_at_decision=inventory,
                    sold_last_30min=s30,sold_last_60min=s60,shelf_inventory=shelf,backroom_inventory=inventory-shelf,
                    current_discount_pct=previous,baseline_announced_2100_pct=0 if minute>=1260 else None,
                    list_price_vnd=spec['unit_price_vnd_reference'],current_unit_price_vnd=round(spec['unit_price_vnd_reference']*(1-previous/100)),
                    morning_features=f,unit_production_cost_vnd_assumed=spec['unit_production_cost_vnd_assumed'],
                    unit_disposal_cost_vnd_assumed=spec['unit_disposal_cost_vnd_assumed'],markdown_action_cost_vnd_assumed=350,
                    qualitative_hot_sku_user_report=spec['qualitative_hot_sku_user_report'],observed_buyers_last30=s30,
                    observed_stockout_last60_minutes=60 if inventory==0 else 0)
                features=m1_features(item,day+f'T{minute//60:02}:{minute%60:02}:00+07:00')
                cap=40 if minute<1230 else 50
                menu=[t for t in (0,10,15,20,25,30,35,40,45,50) if previous<=t<=cap]
                for tier in menu:
                    demand=requests(minute,minute+30,tier);sold=min(inventory,len(demand))
                    rows.append(preprocessor.transform_row(features,tier,sku,spec));labels.append(sold)
                    dates.append(day);actions.append(tier);censored.append(len(demand)>=inventory)
                chosen=menu[int(uniform(f'{day}|{sku}|{scenario}|{minute}|policy')*len(menu))]
                accepted=requests(minute,minute+30,chosen)[:inventory]
                inventory-=len(accepted);ledger.extend(accepted);previous=chosen
    return np.asarray(rows,float),np.asarray(labels,float),dict(dates=dates,actions=actions,censored=censored,
        rows=len(rows),source=str(extracted.relative_to(root)).replace('\\','/'),
        first=min(dates),last=max(dates),independent_days=len(set(dates)),
        method='PAIRED_SYNTHETIC_ACTION_EXPERIMENTS_WITH_OBSERVED_POS_STATE')

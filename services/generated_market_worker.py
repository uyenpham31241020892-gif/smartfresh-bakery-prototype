"""Deterministic synthetic customer requests from past-only baseline estimates.

The worker receives a frozen morning market context and exposes only the elapsed
window. It never reads the model's plan or the day's outcomes to set base demand.
"""
import hashlib
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.volume_scenario import VERSION, arrival_second, uniform


def _count(day, sku, mean, seed):
    key=f'{VERSION}|{day}|{sku}|{seed}|base-count'
    rng=random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16],16))
    # Day-to-day variation must remain visible at the ×10 scale. Poisson-only
    # noise made every Saturday and Sunday look almost identical.
    return max(0, round(rng.gauss(mean, math.hypot(math.sqrt(max(mean,1))*1.25,.055*mean))))


def process(request, source=None):
    operation,day=request['operation'],request['day']
    if operation not in ('consume','closed_evaluation'):
        raise ValueError('Invalid custodian operation')
    start,end=request.get('start',480),request.get('end',1320)
    if type(start) is not int or type(end) is not int or not 480<=start<end<=1320:
        raise ValueError('Invalid elapsed window')
    discounts=request.get('discounts',{})
    if any(type(v) not in (int,float) or not 0<=v<=50 for v in discounts.values()):
        raise ValueError('Invalid approved price')
    context=request['market_context']
    if context['day']!=day or context['version']!=VERSION:
        raise ValueError('Market context mismatch')
    seed=request.get('seed',42)
    counts={sku:_count(day,sku,float(mean),seed) for sku,mean in context['mean_by_sku'].items()}
    if operation=='closed_evaluation':return {'counts':counts}
    events=[]
    for sku,base in counts.items():
        opportunity_count=round(base*.22)
        for index in range(base+opportunity_count):
            promo=index>=base
            customer=f'{sku}|{index}'
            second=arrival_second(day,customer,0,seed,request.get('holiday',False),promo)
            minute=second//60
            if not start<=minute<end:continue
            event_id=f'{VERSION}|{day}|{customer}|{seed}'
            if promo:
                probability=min(1.,.6*(discounts.get(sku,0)/50)**.9)
                if uniform(event_id+'|response')>=probability:continue
            events.append(dict(sku=sku,minute=minute,second=second,event_id=event_id,
                customer_id=customer,quantity=1,origin=VERSION,
                transaction_at=day+f'T{minute//60:02}:{minute%60:02}:{second%60:02}+07:00'))
    return {'requests':sorted(events,key=lambda e:(e['second'],e['event_id']))}


if __name__=='__main__':
    try:print(json.dumps(process(json.load(sys.stdin)),allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':str(exc)}));sys.exit(1)

"""Simulation-only custodian worker. Never imported by the model interface.

Source: V4 Validation customer events and the supplied pos_core response rule.
Consumes one time window; returns only eligible requests in that elapsed window.
The evaluation-only operation returns daily organic counts after close/sandbox.
"""
import hashlib,json,math,sys
from pathlib import Path

def process(request,source):
    day=request['day'];operation=request['operation']
    if operation not in ['consume','closed_evaluation']:raise ValueError('Invalid custodian operation')
    counts={};events=[]
    if operation=='consume':
        start,end=request['start'],request['end'];prices=request['discounts']
        if type(start) is not int or type(end) is not int or not 480<=start<end<=1320:raise ValueError('Invalid elapsed window')
        if any(type(v) not in [int,float] or not math.isfinite(v) or not 0<=v<=50 for v in prices.values()):raise ValueError('Invalid approved price')
    with Path(source).open(encoding='utf-8') as f:
        for line in f:
            row=json.loads(line)
            if row['date']!=day:continue
            sku=row['sku_code']
            if operation=='closed_evaluation':counts[sku]=counts.get(sku,0)+int(row['base_intent_qty']);continue
            h,m=map(int,row['time'].split(':'));slot=h*60+m
            for event in row['unit_events']:
                minute=slot+int(event['second'])//60
                if not start<=minute<end:continue
                promo=bool(event['promo'])
                if promo:
                    u=int(hashlib.sha256(('V608_RESPONSE|'+event['event_id']).encode()).hexdigest()[:13],16)/16**13
                    probability=min(1.,.6*float(row.get('response_multiplier_assumed',1))*(prices.get(sku,0)/50)**.9)
                    if u>=probability:continue
                events.append(dict(sku=sku,minute=minute,second=slot*60+int(event['second']),event_id=event['event_id'],customer_id=event['customer_id'],transaction_at=day+'T'+f'{minute//60:02}:{minute%60:02}:{int(event["second"])%60:02}'+ '+07:00',quantity=1,origin='V4_MARKET_SIMULATION'))
    return {'counts':counts} if operation=='closed_evaluation' else {'requests':sorted(events,key=lambda e:(e['second'],e['event_id']))}

if __name__=='__main__':
    try:print(json.dumps(process(json.load(sys.stdin),sys.argv[1]),allow_nan=False))
    except Exception as exc:print(json.dumps({'error':str(exc)}));sys.exit(1)

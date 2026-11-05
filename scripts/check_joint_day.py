"""Reproducible full-day JOINT evidence in an isolated store."""
import os
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import json
import sys
import tempfile
from datetime import date,timedelta

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.engine import Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow


def step(flow,s,action,payload=None):
    return flow.mutate(s['id'],s['revision'],action,payload or {})


def main():
    base=Engine();sim=Simulator(base);report=[]
    with tempfile.TemporaryDirectory(prefix='joint-day-') as directory:
        for day in ['2022-05-02','2022-05-03','2022-05-06','2022-05-07']:
            flow=Workflow(base,sim,Store(Path(directory)/(day+'.sqlite3')))
            s=flow.create(day=day);plans=s['plan'];s=step(flow,s,'plan_approve');s=step(flow,s,'prepared')
            while s['phase']!='close_pending':
                if s['phase']=='price_pending':s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id']})
                elif s['phase']=='price_approved':s=step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
                else:s=step(flow,s,'advance',{'target':1320})
            s=step(flow,s,'close')
            next_date=str(date.fromisoformat(day)+timedelta(days=1))
            n=flow.next_day(s['id']) if next_date in sim.calendar else None
            assert all(p['prepared']==p['sold']+p['stock'] for p in s['products'].values())
            for row in n['plan'] if n else []:
                p=s['products'][row['sku']]
                assert abs(row['features']['sold_calendar_lag1']-(p['sold']-p['incremental_promo_qty_estimated']))<1e-7
            decisions=[dict(minute=d['minute'],status=d['status'],rows=[{k:r[k] for k in ['sku','stock','sales30','previous','discount','decision_reason','pricing_policy']} for r in d['rows']]) for d in s['decisions']]
            report.append(dict(day=day,model_version=s['model_version'],model_hashes=s['model_hashes'],
                prepared=sum(p['prepared'] for p in s['products'].values()),sold=sum(p['sold'] for p in s['products'].values()),
                waste=sum(p['stock'] for p in s['products'].values()),
                incremental_promo_estimate=sum(p['incremental_promo_qty_estimated'] for p in s['products'].values()),
                selected_quantiles={r['sku']:r['quantile'] for r in plans},next_day_depromo_checked=bool(n),rows=decisions))
    (ROOT/'docs/JOINT_AFTER_PRICING.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for day in report:
        print(json.dumps({k:day[k] for k in ['day','prepared','sold','waste','incremental_promo_estimate']}))
        for decision in day['rows']:
            changes=[f"{r['sku']}: {r['previous']} -> {r['discount']}" for r in decision['rows'] if r['discount']>r['previous']]
            print(decision['minute'],', '.join(changes) or 'HOLD')


if __name__=='__main__':main()

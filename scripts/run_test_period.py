"""Run the complete July-August 2022 synthetic operating period in an isolated DB."""
import argparse
import json
import os
from datetime import date,timedelta
from pathlib import Path
import sys

os.environ.setdefault('OMP_NUM_THREADS','1')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import httpx
from services.engine import Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow
from services.business_reports import totals
from services.weather_api import fetch_weather,PREVIOUS_RUNS_URL
from scripts.audit_joint_test_month import close_day,LATITUDE,LONGITUDE

START=date(2022,7,1)
LAST=date(2022,8,31)


def weather_period(last=LAST):
    cache=ROOT/'runtime/jma_weather_2022_07_01_2022_09_01.json'
    if cache.exists():
        values=json.loads(cache.read_text(encoding='utf-8'))
        days=[(START+timedelta(days=i)).isoformat() for i in range((last-START).days+2)]
        if all(day in values and values[day].get('forecast_source')=='OPEN_METEO_JMA_GSM_PREVIOUS_DAY1' for day in days):
            return {day:values[day] for day in days}
    first=START-timedelta(days=1)
    end=last+timedelta(days=1)
    params=dict(latitude=LATITUDE,longitude=LONGITUDE,timezone='Asia/Ho_Chi_Minh',
                hourly='precipitation_previous_day1,temperature_2m_previous_day1',models='jma_gsm',
                start_date=first.isoformat(),end_date=end.isoformat())
    response=httpx.get(PREVIOUS_RUNS_URL,params=params,timeout=30)
    response.raise_for_status()
    hourly=response.json()['hourly']
    by_day={(first+timedelta(days=i)).isoformat():[] for i in range((end-first).days+1)}
    for i,stamp in enumerate(hourly['time']):
        if stamp[:10] in by_day:
            by_day[stamp[:10]].append((stamp,hourly['precipitation_previous_day1'][i],
                                      hourly['temperature_2m_previous_day1'][i]))
    if any(len(values)!=24 or any(rain is None or temp is None for _,rain,temp in values)
           for values in by_day.values()):
        raise ValueError('JMA Previous Runs chưa trả đủ thời tiết giai đoạn test.')
    class CachedClient:
        def get(self,url,params):
            days=(params['start_date'],params['end_date'])
            values=[row for day in days for row in by_day[day]]
            payload={'hourly':{'time':[x[0] for x in values],
                               'precipitation_previous_day1':[x[1] for x in values],
                               'temperature_2m_previous_day1':[x[2] for x in values]}}
            return httpx.Response(200,json=payload,request=httpx.Request('GET',url,params=params))
    client=CachedClient()
    return {(START+timedelta(days=i)).isoformat():
            fetch_weather((START+timedelta(days=i)).isoformat(),LATITUDE,LONGITUDE,client=client)
            for i in range((end-START).days+1)}


def run(branch,last=LAST,tag=''):
    suffix=f'_{tag}' if tag else ''
    path=ROOT/'runtime'/f'test_period_{branch}_2022_07_08{suffix}.sqlite3'
    if path.exists():raise ValueError('Database kiểm tra đã tồn tại: '+str(path))
    weather=weather_period(last)
    engine=Engine();simulator=Simulator(engine)
    flow=Workflow(engine,simulator,Store(path))
    state=flow.create(day=START.isoformat(),seed=42,auto_run=False,weather=weather[START.isoformat()],
                      identifier=f'test-{branch}-{START.isoformat()}')
    rows=[]
    for i in range((last-START).days+1):
        day=state['day'];intents=simulator.evaluation_counts(day,simulator.version,state['market_context'],state['seed'])
        planned={p['sku']:p for p in state['plan']}
        state=close_day(flow,state,baseline=branch!='joint')
        metrics=totals(state)
        rows.append(dict(day=day,session_id=state['id'],policy=branch,
                         prepared=metrics['prepared'],sold=metrics['sold'],stock=metrics['stock'],
                         revenue_vnd=metrics['revenue'],contribution_vnd=metrics['contribution_before_overhead'],
                         sell_through_pct=metrics['sell_through_pct'],base_intent=sum(intents.values()),
                         stockout_skus=sum(bool(p.get('stockout_intervals') or p.get('stockout_since') is not None)
                                           for p in state['products'].values()),
                         market_context=state['market_context'],
                         weather={'source':state['weather']['forecast_source'],
                                  'prior_day_rain_mm':state['weather']['forecast_rain_mm_previous_day1'],
                                  'prior_day_temp_c':state['weather']['forecast_temperature_max_c_previous_day1'],
                                  'issued_at':state['weather'].get('issued_at')},
                         skus=[dict(sku=sku,prepared=p['prepared'],sold=p['sold'],stock=p['stock'],
                                    revenue_vnd=p['revenue'],base_intent=intents.get(sku,0),
                                    selected_forecast=planned[sku].get('v4_plan',{}).get('selected_forecast'),
                                    online=planned[sku].get('v4_plan',{}).get('calibration',{}))
                               for sku,p in state['products'].items()]))
        print(branch,day,'prepared',metrics['prepared'],'sold',metrics['sold'],
              'stock',metrics['stock'],'base',sum(intents.values()),flush=True)
        if i<(last-START).days:
            tomorrow=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
            state=flow.next_day(state['id'],weather=weather[tomorrow])
    if branch=='joint' and last==LAST:
        state=flow.next_day(state['id'],weather=weather['2022-09-01'])
        assert state['day']=='2022-09-01' and state['phase']=='plan_pending'
        print('next_session',state['id'],state['day'],flush=True)
    report=dict(period=f'{START.isoformat()}..{last.isoformat()}',branch=branch,seed=42,
                model_version=state['model_version'],simulator_version=simulator.version,
                policy_revision=json.loads((ROOT/'models/joint/manifest.json').read_text(encoding='utf-8'))['policy_revision'],
                weather_source='OPEN_METEO_JMA_GSM_PREVIOUS_DAY1',
                weather_coordinates={'latitude':LATITUDE,'longitude':LONGITUDE},
                rows=rows,db_path=str(path),next_session_id=state['id'] if branch=='joint' else None)
    artifact=ROOT/'docs'/f'JOINT_TWO_MONTH_{branch.upper()}{suffix.upper()}.json'
    artifact.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('report',artifact,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--branch',choices=('joint','rolling7','seasonal'),required=True)
    parser.add_argument('--last',type=date.fromisoformat,default=LAST)
    parser.add_argument('--tag',default='')
    args=parser.parse_args()
    if args.last<START or args.last>LAST or not all(c.isalnum() or c=='_' for c in args.tag):
        parser.error('Invalid test period or tag.')
    run(args.branch,args.last,args.tag)

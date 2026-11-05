"""Closed-loop July test-month comparison on one generated POS world per seed."""
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date, timedelta
import httpx

os.environ.setdefault('OMP_NUM_THREADS', '1')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from services.engine import Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow
from services.business_reports import totals
from services.weather_api import fetch_weather, PREVIOUS_RUNS_URL

LATITUDE,LONGITUDE=10.7769,106.7009  # Illustrative HCMC location, not a verified AEON branch.


def api_weather_month():
    params=dict(latitude=LATITUDE,longitude=LONGITUDE,timezone='Asia/Ho_Chi_Minh',
                hourly='precipitation_previous_day1,temperature_2m_previous_day1',models='jma_gsm',
                start_date='2022-06-30',end_date='2022-07-31')
    response=httpx.get(PREVIOUS_RUNS_URL,params=params,timeout=30)
    response.raise_for_status()
    hourly=response.json()['hourly']
    by_day={day:[] for day in [(date(2022,6,30)+timedelta(days=i)).isoformat() for i in range(32)]}
    for index,stamp in enumerate(hourly['time']):
        if stamp[:10] in by_day:
            by_day[stamp[:10]].append((stamp,hourly['precipitation_previous_day1'][index],
                                      hourly['temperature_2m_previous_day1'][index]))
    if any(len(values)!=24 or any(rain is None or temp is None for _,rain,temp in values)
           for values in by_day.values()):
        raise ValueError('Open-Meteo JMA chưa trả đủ 32 ngày thời tiết cần thiết.')
    class CachedClient:
        def get(self,url,params):
            days=[params['start_date'],params['end_date']]
            values=[row for day in days for row in by_day[day]]
            payload={'hourly':{'time':[r[0] for r in values],
                               'precipitation_previous_day1':[r[1] for r in values],
                               'temperature_2m_previous_day1':[r[2] for r in values]}}
            return httpx.Response(200,json=payload,request=httpx.Request('GET',url,params=params))
    client=CachedClient()
    return {(date(2022,7,1)+timedelta(days=i)).isoformat():
            fetch_weather((date(2022,7,1)+timedelta(days=i)).isoformat(),LATITUDE,LONGITUDE,client=client)
            for i in range(31)}


def step(flow,state,action,payload=None):
    return flow.mutate(state['id'],state['revision'],action,payload or {})


def close_day(flow,state,baseline=False):
    quantities={p['sku']:p['baseline'] for p in state['plan']} if baseline else {}
    state=step(flow,state,'plan_approve',{'quantities':quantities,'reason':'Đối chứng baseline cùng thứ ×10; giữ cùng M1 và POS.',
                                          'supply_policy':'seasonal_baseline'} if baseline else {})
    state=step(flow,state,'prepared')
    while state['phase']!='close_pending':
        if state['phase']=='price_pending':
            state=step(flow,state,'price_approve',{'proposal_id':state['pending']['id']})
        elif state['phase']=='price_approved':
            state=step(flow,state,'price_apply',{'proposal_id':state['pending']['id']})
        else:
            state=step(flow,state,'advance',{'target':1320})
    return step(flow,state,'close')


def run_branch(name,simulator,engine,weather_by_day):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='smartfresh-july-'+name+'-') as directory:
        flow=Workflow(engine,simulator,Store(Path(directory)/'sessions.sqlite3'))
        state=flow.create(day='2022-07-01',seed=42,auto_run=False,weather=weather_by_day['2022-07-01'])
        for index in range(31):
            day=state['day']
            expected=simulator.evaluation_counts(day,simulator.version,state['market_context'],state['seed'])
            planned={p['sku']:p for p in state['plan']}
            state=close_day(flow,state,baseline=name=='rolling7')
            metric=totals(state)
            row=dict(day=day,session_id=state['id'],policy=name,weekday=date.fromisoformat(day).strftime('%a'),
                     weather=dict(source=state['weather'].get('forecast_source'),
                                  prior_day_rain_mm=state['weather'].get('forecast_rain_mm_previous_day1'),
                                  prior_day_temp_c=state['weather'].get('forecast_temperature_max_c_previous_day1'),
                                  issued_at=state['weather'].get('issued_at')),
                     prepared=metric['prepared'],sold=metric['sold'],stock=metric['stock'],
                     revenue_vnd=metric['revenue'],contribution_vnd=metric['contribution_before_overhead'],
                     sell_through_pct=metric['sell_through_pct'],base_intent=sum(expected.values()),
                     stockout_skus=sum(bool(p.get('stockout_intervals') or p.get('stockout_since') is not None) for p in state['products'].values()),
                     market_context=state['market_context'],
                     skus=[dict(sku=sku,prepared=p['prepared'],sold=p['sold'],stock=p['stock'],
                                revenue_vnd=p['revenue'],base_intent=expected.get(sku,0),
                                baseline_quantity=planned[sku]['baseline'],joint_quantity=planned[sku]['prepared'],
                                guard=planned[sku].get('v4_plan',{}).get('calibration'))
                           for sku,p in state['products'].items()])
            rows.append(row)
            print(name,day,'prepared',row['prepared'],'sold',row['sold'],'stock',row['stock'],flush=True)
            if index<30:
                next_date=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
                state=flow.next_day(state['id'],weather=weather_by_day[next_date])
    return rows


def main():
    engine=Engine();simulator=Simulator(engine);weather_by_day=api_weather_month()
    joint=run_branch('joint',simulator,engine,weather_by_day)
    baseline=run_branch('rolling7',simulator,engine,weather_by_day)
    assert [r['day'] for r in joint]==[r['day'] for r in baseline]
    assert [r['base_intent'] for r in joint]==[r['base_intent'] for r in baseline]
    assert [r['market_context'] for r in joint]==[r['market_context'] for r in baseline]
    assert [[(p['sku'],p['base_intent']) for p in r['skus']] for r in joint]==[[ (p['sku'],p['base_intent']) for p in r['skus']] for r in baseline]
    output=dict(period='2022-07-01..2022-07-31',seed=42,simulator_version=simulator.version,
                model_version='SMARTFRESH_V4_JOINT_V2',
                policy_revision=json.loads((ROOT/'models/joint/manifest.json').read_text(encoding='utf-8'))['policy_revision'],
                weather_source='OPEN_METEO_JMA_GSM_PREVIOUS_DAY1',weather_latitude=LATITUDE,weather_longitude=LONGITUDE,
                qualification='Post-test development period; generated POS is synthetic, not AEON POS; HCMC weather coordinates are illustrative; JMA GSM fixed 24h lead is available in 2022 but exact issue times are unverified; Rolling-7 changes supply only, M1 price policy shared; JOINT model weights stay fixed.',
                policies={'joint':joint,'rolling7':baseline})
    path=ROOT/'docs/JOINT_TEST_MONTH_AUDIT.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print('report',path,flush=True)


if __name__=='__main__':main()

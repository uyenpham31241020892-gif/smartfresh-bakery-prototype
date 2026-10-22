import copy
import json
from datetime import timedelta
import pytest
from services.ingestion import inspect
from services.quality import weather_check, cutoff, build_snapshot, sales_quality
from test_api import client


def weather(day='2022-08-16'):
    return {'forecast_source':'DECLARED_FORECAST','issued_at':(cutoff(day)-timedelta(hours=12)).isoformat(),
            'forecast_rain_mm_previous_day1':5,'forecast_temperature_max_c_previous_day1':30,
            'weekday_iso':2,'is_weekend':0,'is_public_holiday':0,'is_festival_non_public':0,'month':8,'day_of_year':228}


@pytest.mark.parametrize('field,value',[
    ('issued_at','2022-08-16T06:01:00+07:00'),('issued_at','2022-08-16T05:00:00'),
    ('issued_at','2022-08-13T05:00:00+07:00'),('issued_at','NaT'),
    ('available_at','2022-08-16T07:00:00+07:00'),('available_at','2022-08-15T10:00:00+07:00'),
    ('forecast_source','ERA5_REANALYSIS')])
def test_forecast_invalid_times_and_sources(field,value):
    w=weather();w[field]=value
    with pytest.raises(ValueError):weather_check('2022-08-16',w)


def test_cutoff_boundary_timezone_and_age():
    w=weather();w['issued_at']='2022-08-15T23:00:00Z'
    assert weather_check('2022-08-16',w)['age_hours']==0
    w['issued_at']='2022-08-14T06:00:00+07:00'
    assert weather_check('2022-08-16',w)['age_hours']==48


@pytest.mark.parametrize('field',['hidden_demand','response_draw','ERA5_rain','stock_at_21','y_discount_pct','target_demand'])
def test_evaluation_fields_cannot_enter_or_be_renamed(engine,field):
    raw=f'date,sku_code,sold_qty,{field}\n2022-08-15,BK-001,8,2\n'.encode()
    p=inspect('history.csv',raw,'2022-08-16',engine.master)
    assert not p['valid'] and p['quarantine'] and not p['history']
    p=inspect('history.csv',raw,'2022-08-16',engine.master,{field:'ignored'})
    assert not p['valid']


def test_spoofing_jma_name_does_not_skip_timestamp(engine):
    raw=b'date,forecast_rain_mm_previous_day1,forecast_temperature_max_c_previous_day1,forecast_source\n2022-08-16,1,30,JMA_GSM_PREVIOUS_DAY1\n'
    assert not inspect('weather.csv',raw,'2022-08-16',engine.master)['valid']


def test_snapshot_reproducible_bound_to_input_and_persisted(flow):
    a=flow.create();b=flow.create()
    assert a['feature_snapshot_id']==b['feature_snapshot_id']
    assert a['data_quality']['status']=='WARN'
    assert a['data_quality']['weather']['issued_at'] is None
    assert flow.store.get(a['id'])['data_quality']==a['data_quality']
    h={(r['date'],r['sku']):r['sold'] for r in a['input_history']}
    h[('2022-08-15','BK-001')]+=1
    c=flow.create(history=h)
    assert a['feature_snapshot_id']!=c['feature_snapshot_id']


def test_future_history_blocked_before_inference(flow,monkeypatch):
    def fail(*args):pytest.fail('inference must not run')
    monkeypatch.setattr(flow.engine,'plan',fail)
    with pytest.raises(ValueError,match='leakage'):
        flow.create(history={('2022-08-16','BK-001'):4})


def test_stale_per_sku_history_blocks_before_model(flow,monkeypatch):
    h={(r['date'],r['sku']):r['sold'] for r in flow.create()['input_history'] if r['date']<'2022-08-13'}
    monkeypatch.setattr(flow.engine,'plan',lambda *a:pytest.fail('inference must not run'))
    with pytest.raises(ValueError,match='quá cũ'):flow.create(history=h)


def test_history_not_available_at_cutoff_is_rejected(engine):
    raw=b'date,sku_code,sold_qty,available_at\n2022-08-15,BK-001,8,2022-08-16T07:00:00+07:00\n'
    assert not inspect('history.csv',raw,'2022-08-16',engine.master)['valid']


def test_import_log_quarantine_confirmation_and_restart(client):
    import app as m
    from services.store import Store
    s=client.get('/api/state').json()
    q=client.get('/api/quality',params={'session_id':s['id']}).json()
    assert q['feature_snapshot_id']==s['feature_snapshot_id']
    raw=b'date,sku_code,sold_qty,hidden_demand\n2022-08-15,BK-001,8,10\n'
    p=client.post('/api/imports',data={'day':'2022-08-16','source_name':'Test synthetic'},files={'file':('leak.csv',raw)}).json()
    assert p['quarantine']
    assert client.post('/api/imports/'+p['import_id']+'/confirm',json={}).status_code==400
    log=client.get('/api/imports').json()['imports'][0]
    assert log['status']=='QUARANTINED' and log['source_name']=='Test synthetic'
    assert Store(m.store.path).get(s['id'])['feature_snapshot_id']==q['feature_snapshot_id']
    with Store(m.store.path).connect() as db:
        assert db.execute('SELECT COUNT(*) FROM imports').fetchone()[0]==1
    assert client.post('/api/imports',data={'day':'2022-08-16'},files={'file':('bad.zip',b'bad')}).status_code==400
    assert client.get('/api/imports').json()['imports'][0]['status']=='QUARANTINED'


def test_live_feed_freshness_and_renewal(flow):
    s=flow.create(mode='live');s=flow.mutate(s['id'],s['revision'],'plan_approve');s=flow.mutate(s['id'],s['revision'],'prepared')
    s=flow.mutate(s['id'],s['revision'],'advance',{'target':1170})
    assert not s['pending']['rows'] and sales_quality(s)['status']=='BLOCK'
    s=flow.mutate(s['id'],s['revision'],'confirm_zero_sales',{'confirmed':True,'reason':'Kiểm kê quầy'})
    assert s['pending']['rows'] and sales_quality(s)['status']=='PASS'
    assert s['pending']['feature_snapshot_id']
    s=flow.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':s['pending']['id']})
    s=flow.mutate(s['id'],s['revision'],'price_apply',{'proposal_id':s['pending']['id']})
    s=flow.mutate(s['id'],s['revision'],'advance',{'target':1200})
    assert sales_quality(s)['age_minutes']==30
    # Deliberately age the in-memory feed; proposals must not infer from stale observations.
    s['minute']=1201
    assert flow.proposals(s)['status']=='missing_data'

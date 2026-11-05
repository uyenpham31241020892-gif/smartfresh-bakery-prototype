from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest

from services.weather_api import fetch_weather, FORECAST_URL, RUN_URL, PREVIOUS_RUNS_URL


def fake_client(requests):
    def respond(request):
        requests.append(request)
        if request.url.path == '/v1/forecast' and 'run' in request.url.params:
            day = date.fromisoformat(request.url.params['run'][:10])
            times = [(day + timedelta(days=offset)).isoformat() + f'T{hour:02d}:00'
                     for offset in range(4) for hour in range(24)]
            return httpx.Response(200, json={'hourly': {'time': times,
                'precipitation': [0.5] * len(times), 'temperature_2m': [29.0] * len(times)}})
        if request.url.params.get('models')=='jma_gsm':
            first=date.fromisoformat(request.url.params['start_date'])
            times=[(first+timedelta(days=offset)).isoformat()+f'T{hour:02d}:00'
                   for offset in range(2) for hour in range(24)]
            return httpx.Response(200,json={'hourly':{'time':times,
                'precipitation_previous_day1':[0.5]*len(times),
                'temperature_2m_previous_day1':[29.0]*len(times)}})
        day = request.url.params['end_date']
        previous = request.url.params['start_date']
        return httpx.Response(200, json={'daily': {'time': [previous, day],
            'precipitation_sum': [3.5, 8.0], 'temperature_2m_max': [29.0, 31.0]}})
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_current_api_snapshot_keeps_previous_day_feature_and_target_forecast():
    requests = []
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    with fake_client(requests) as client:
        result = fetch_weather('2026-11-05', 10.7769, 106.7009, now=now, client=client)
    assert str(requests[0].url).startswith(FORECAST_URL)
    assert requests[0].url.params['start_date'] == '2026-11-04'
    assert result['forecast_rain_mm_previous_day1'] == 3.5
    assert result['weather_provenance']['target_date_forecast']['precipitation_sum_mm'] == 8.0
    assert result['weather_provenance']['timestamp_kind'] == 'api_snapshot_captured'
    assert result['weather_provenance']['vintage_verified'] is True
    assert result['issued_at'] == '2026-11-04T19:00:00+07:00'


def test_archived_single_run_is_explicitly_unverified_for_live():
    requests = []
    with fake_client(requests) as client:
        result = fetch_weather('2026-05-03', 10.7769, 106.7009,
                               now=datetime(2026, 11, 5, tzinfo=timezone.utc), client=client)
    assert str(requests[0].url).startswith(RUN_URL)
    assert requests[0].url.params['run'] == '2026-05-01T12:00'
    assert requests[0].url.params['models'] == 'ecmwf_ifs'
    assert 'start_date' not in requests[0].url.params
    assert result['forecast_rain_mm_previous_day1'] == 12.0
    assert result['weather_provenance']['vintage_verified'] is False
    assert result['weather_provenance']['availability_basis'] == 'estimated_6h_after_run'


def test_no_backdating_and_2022_fixed_lead_forecast_is_simulation_only():
    with pytest.raises(ValueError, match='cutoff'):
        fetch_weather('2026-11-05', 10, 106, now=datetime(2026, 11, 5, tzinfo=timezone.utc))
    requests=[]
    with fake_client(requests) as client:
        result=fetch_weather('2022-05-03',10,106,now=datetime(2026,11,5,tzinfo=timezone.utc),client=client)
    assert str(requests[0].url).startswith(PREVIOUS_RUNS_URL)
    assert requests[0].url.params['models']=='jma_gsm'
    assert result['forecast_rain_mm_previous_day1']==12.0
    assert result['issued_at'] is None
    assert result['weather_provenance']['vintage_verified'] is False


def test_2022_historical_api_weather_can_plan_simulation_but_not_live(flow):
    requests=[]
    with fake_client(requests) as client:
        weather=fetch_weather('2022-07-01',10,106,now=datetime(2026,11,5,tzinfo=timezone.utc),client=client)
    session=flow.create(day='2022-07-01',weather=weather)
    assert session['day']=='2022-07-01'
    assert session['data_quality']['weather']['status']=='WARN'
    assert len(session['plan'])==7
    with pytest.raises(ValueError,match='chưa xác minh giờ phát hành'):
        flow.create(day='2022-07-01',mode='live',weather=weather)


def test_next_simulation_day_refreshes_open_meteo_weather(flow,monkeypatch):
    requests=[]
    with fake_client(requests) as client:
        first=fetch_weather('2022-07-01',10,106,now=datetime(2026,11,5,tzinfo=timezone.utc),client=client)
        second=fetch_weather('2022-07-02',10,106,now=datetime(2026,11,5,tzinfo=timezone.utc),client=client)
    session=flow.create(day='2022-07-01',weather=first)
    session['phase']='closed'
    session['products']={sku:{'sold':0,'prepared':0,'stock':0} for sku in flow.engine.master}
    with flow.store.connect() as db:
        db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(session),session['id']))
    called=[]
    def provider(day,latitude,longitude):
        called.append((day,latitude,longitude))
        return second
    monkeypatch.setattr('services.weather_api.fetch_weather',provider)
    following=flow.next_day(session['id'])
    assert called==[('2022-07-02',10.0,106.0)]
    assert following['weather']['date']=='2022-07-02'
    assert following['weather']['forecast_source']=='OPEN_METEO_JMA_GSM_PREVIOUS_DAY1'

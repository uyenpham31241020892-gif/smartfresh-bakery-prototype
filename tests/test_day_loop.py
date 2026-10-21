import copy
from datetime import date,timedelta
import pytest
from services.realtime import Realtime
from services.engine import OUTCOME_FEATURES, outcome_features


def start(flow,mode='simulation',day='2022-08-16'):
    s=flow.create(day=day,mode=mode)
    s=flow.mutate(s['id'],s['revision'],'plan_approve')
    return flow.mutate(s['id'],s['revision'],'prepared')


def test_arrivals_are_trained_reproducible_and_independent_from_m2(engine,simulator,monkeypatch):
    r=simulator.arrivals.report()
    assert r['train_until']<r['validation_from']<=r['calibrated_until']<r['test_from']
    assert r['test_rows']==128 and r['passed'] and r['test_mae']<=r['sku_mean_baseline_mae']
    before=simulator.events('2022-08-19',55)
    monkeypatch.setattr(engine.m2,'predict',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Simulator must not read M2 forecast')))
    assert before==simulator.events('2022-08-19',55)
    assert simulator.events('2022-08-19',56)!=before
    assert all(isinstance(e['minute'],int) and 480<=e['minute']<1320 for e in before)


def test_last_hour_has_calibrated_arrivals_without_forcing_each_sku_to_sell(simulator):
    totals=[]
    for seed in range(30):
        events=simulator.events('2022-08-19',seed)
        totals.append(sum(not e['promo'] and 1110<=e['minute']<1170 for e in events))
    assert sum(n>0 for n in totals)>=29
    assert 5<sum(totals)/len(totals)<45


def test_live_missing_feed_blocks_price_but_simulation_fork_is_separate(flow):
    live=start(flow,'live')
    live=flow.mutate(live['id'],live['revision'],'advance',{'target':1170})
    assert live['pending']['status']=='missing_data' and live['ledger']==[]
    with pytest.raises(ValueError,match='dữ liệu thiếu'):
        flow.mutate(live['id'],live['revision'],'price_approve',{'proposal_id':live['pending']['id']})
    fork=flow.fork_simulation(live['id'])
    assert fork['id']!=live['id'] and fork['mode']=='simulation' and fork['day']==live['day']
    assert fork['weather']==live['weather'] and fork['input_history']==live['input_history']
    assert flow.store.get(live['id'])['ledger']==[]
    clock=Realtime(flow,flow.store)
    with pytest.raises(ValueError,match='bán giả'):
        clock.configure(live['id'],True)


def test_backend_clock_advances_without_browser_pauses_for_approval_and_resumes(flow):
    s=start(flow)
    clock=Realtime(flow,flow.store)
    job=clock.configure(s['id'],True,30.,True)
    wall=job['last_wall']
    for _ in range(23):
        wall+=1;clock.step(wall)
    s=flow.store.get(s['id'])
    assert s['minute']==1170 and s['phase']=='price_pending' and len(s['ledger'])>0
    assert sum(r['sales60'] for r in s['pending']['rows'])>0
    before=copy.deepcopy(s)
    clock.step(wall+100)
    assert flow.store.get(s['id'])==before
    s=flow.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':s['pending']['id']})
    s=flow.mutate(s['id'],s['revision'],'price_apply',{'proposal_id':s['pending']['id']})
    clock.step(wall+101)
    assert flow.store.get(s['id'])['minute']==1200
    flow.assert_accounts(flow.store.get(s['id']))


def test_continuous_clock_reprices_from_current_inventory_and_expires_at_close(flow):
    s=start(flow)
    s=flow.mutate(s['id'],s['revision'],'advance',{'target':1170})
    pid=s['pending']['id']
    s=flow.mutate(s['id'],s['revision'],'tick',{'target':1175})
    assert s['minute']==1175 and s['pending']['as_of_minute']==1175 and s['pending']['id']!=pid
    with pytest.raises(ValueError,match='hết hiệu lực'):
        flow.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':pid})
    while s['minute']<1320:
        s=flow.mutate(s['id'],s['revision'],'tick',{'target':1320})
    assert s['phase']=='close_pending' and s['pending'] is None
    assert s['decisions'][-1]['status']=='expired'
    flow.assert_accounts(s)


def test_closed_day_supplies_next_day_sales_and_waste_not_future_data(flow,simulator):
    s=start(flow,day='2022-08-19')
    while s['minute']<1320:
        s=flow.mutate(s['id'],s['revision'],'tick',{'target':1320})
    s=flow.mutate(s['id'],s['revision'],'close')
    next_s=flow.next_day(s['id'])
    assert next_s['day']=='2022-08-20' and next_s['weather']==simulator.calendar['2022-08-20']
    for p in next_s['plan']:
        previous=s['products'][p['sku']]
        assert p['features']['lag1_sales']==previous['sold']
        row=next(r for r in next_s['day_context']['previous_day_outcomes'] if r['sku_code']==p['sku'])
        assert row['waste_qty']==previous['stock'] and row['sold_qty']==previous['sold']
    assert flow.next_day(s['id'])['id']==next_s['id']
    assert all(r['date']<next_s['day'] for r in next_s['input_history'])


def test_month_selection_uses_own_weekday_weather_and_past_only(flow):
    august=flow.create(day='2022-08-19')
    september=flow.create(day='2022-09-19')
    assert august['weather']!=september['weather']
    assert august['plan'][0]['features']['weekday']!=september['plan'][0]['features']['weekday']
    assert august['input_hash']!=september['input_hash']
    assert all(r['date']<august['day'] for r in august['input_history'])
    assert all(r['date']<september['day'] for r in september['input_history'])


def test_inventory_features_only_use_past_dates():
    outcomes={('2022-08-18','BK-001'):{'prepared_qty':60,'waste_qty':10,'stockout':0,'discounted_qty':5},
              ('2022-08-12','BK-001'):{'prepared_qty':80,'waste_qty':12}}
    before=outcome_features('2022-08-19','BK-001',outcomes)
    outcomes[('2022-08-19','BK-001')]={'prepared_qty':9999,'waste_qty':8888}
    outcomes[('2022-09-19','BK-001')]={'prepared_qty':9999,'waste_qty':8888}
    assert outcome_features('2022-08-19','BK-001',outcomes)==before
    assert before['lag1_waste_qty']==10 and before['lag7_waste_qty']==12

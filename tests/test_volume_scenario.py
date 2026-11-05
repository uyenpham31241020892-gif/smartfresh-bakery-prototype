from collections import Counter
import hashlib
import json
import pytest
from services.engine import ROOT
from services.volume_scenario import SCALE, VERSION, MODEL_VERSION, scaled
from services.volume_market_worker import process
from services.volume_engine import VolumeEngine
from services.baseline_history import report
from services.identity import actor, AccessError
from services.learning import Learning


def step(flow,s,action,payload=None):
    return flow.mutate(s['id'],s['revision'],action,payload or {})


def finish(flow,s):
    while s['phase']!='close_pending':
        if s['phase']=='price_pending':s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id']})
        elif s['phase']=='price_approved':s=step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
        else:s=step(flow,s,'advance',{'target':1320})
    return step(flow,s,'close')


def test_baseline_exact_x10_and_prices_unchanged():
    old,new=report('2022-06-15',30,1),report('2022-06-15',30,10)
    for key in ['prepared','sold','stock','revenue','production_cost_assumed','contribution_before_overhead','list_value','discount_value']:
        assert new['summary'][key]==pytest.approx(old['summary'][key]*10)
    for key in ['average_price','weighted_discount_pct']:
        assert new['summary'][key]==pytest.approx(old['summary'][key])
    assert new['volume_scale']==10
    assert scaled({'sold_qty':2,'unit_price_vnd_reference':25000,'is_weekend':1,'observed_stockout_last60_minutes':15})=={'sold_qty':20,'unit_price_vnd_reference':25000,'is_weekend':1,'observed_stockout_last60_minutes':15}


def test_models_selected_source_and_separate_scaled_bundles(engine):
    volume=VolumeEngine()
    selected=ROOT/'TRAINED_TESTED/agent_sandbox/smartfresh_adapter.py'
    assert volume.manifest['adapter_sha256']==hashlib.sha256(selected.read_bytes()).hexdigest()
    assert volume.adapter.__file__==str(selected)
    assert volume.version==MODEL_VERSION and engine.version!=volume.version
    assert volume.adapter._M1_BUNDLE is not engine.adapter._M1_BUNDLE
    for sku in engine.master:
        assert volume.master[sku]['daily_capacity_units_assumed']==10*engine.master[sku]['daily_capacity_units_assumed']
        assert volume.master[sku]['unit_price_vnd_reference']==engine.master[sku]['unit_price_vnd_reference']
    assert volume.manifest['passed'] and volume.require_integrity()
    assert volume.manifest['training_rows']['m2']==11655


def test_customers_count_windows_seed_and_profiles(simulator):
    source=ROOT/'simulation_only/v4/validation_world.jsonl'
    for day,holiday in [('2022-05-05',False),('2022-05-07',False),('2022-05-02',True)]:
        request=dict(operation='consume',day=day,start=480,end=1320,seed=42,holiday=holiday,discounts={})
        events=process(request,source)['requests']
        counts=Counter(e['sku'] for e in events)
        original=simulator.evaluation_counts(day,simulator.original_version)
        assert counts==Counter({sku:n*10 for sku,n in original.items()})
        assert len({e['event_id'] for e in events})==len(events)
        assert all(e['quantity']==1 and 480<=e['minute']<1320 for e in events)
        split=process(dict(request,end=1170),source)['requests']+process(dict(request,start=1170),source)['requests']
        assert split==events
        assert events==process(request,source)['requests']
        other=process(dict(request,seed=43),source)['requests']
        assert other!=events and Counter(e['sku'] for e in other)==counts
        morning=sum(e['minute']<1020 for e in events)/len(events)
        assert (.45<morning<.65) if holiday or day=='2022-05-07' else (.25<morning<.40)
        discounted=process(dict(request,discounts={k:50 for k in counts}),source)['requests']
        assert len(discounted)>len(events)
        assert {e['event_id'] for e in events}<={e['event_id'] for e in discounted}


def test_full_day_next_day_model_units_and_learning(flow,engine,tmp_path):
    s=flow.create(day='2022-05-05',auto_run=False)
    assert s['model_version']==MODEL_VERSION and s['simulator_version']==VERSION
    assert sum(p['prepared'] for p in s['plan'])>0
    assert s['market_context']['source']=='PAST_X10_WEEKDAY_BASELINE_WITH_CAPPED_WEEKEND_AND_LATENT_VARIATION'
    assert all(p['supply']['demand_scale']==10 for p in s['plan'])
    s=step(flow,s,'plan_approve');s=step(flow,s,'prepared');s=finish(flow,s)
    assert len(s['ledger'])>500
    assert all(p['prepared']==p['sold']+p['stock'] for p in s['products'].values())
    n=flow.next_day(s['id'])
    for p in n['plan']:
        product=s['products'][p['sku']]
        expected=product['sold'] if product.get('stockout_intervals') or product.get('stockout_since') is not None or product['stock']==0 else product['sold']-product['incremental_promo_qty_estimated']
        assert p['features']['sold_calendar_lag1']==pytest.approx(expected)
    learning=Learning(flow.store,engine,tmp_path/'learning')
    result=learning.collect(s)
    assert result['origin']=='simulation_x10'
    rows=learning.rows('m2','simulation_x10')
    assert len(rows)==7 and not learning.rows('m2','real')
    assert all(not r['eligible_for_real_training'] for r in rows)
    assert learning.rows('m1_window','simulation_x10')
    learning.collect(s)
    assert len(learning.rows('m2','simulation_x10'))==7


def test_manager_can_change_one_held_sku_with_approval(flow):
    s=flow.create();s=step(flow,s,'plan_approve');s=step(flow,s,'prepared');s=step(flow,s,'advance',{'target':1170})
    token=actor.set({'id':'manager','username':'manager','role':'manager'})
    try:
        s=step(flow,s,'refresh_price',{'manual_edit':True})
        sku=next(k for k,p in s['products'].items() if p['stock']>0)
        previous={k:p['discount'] for k,p in s['products'].items()}
        with pytest.raises(ValueError):step(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:20}})
        s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:20},'reason':'Manager review'})
        assert {k:p['discount'] for k,p in s['products'].items()}==previous
        s=step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
        assert s['products'][sku]['discount']==20
        assert all(p['discount']==previous[k] and p['price_version']==0 for k,p in s['products'].items() if k!=sku)
        actor.set({'id':'staff','username':'staff','role':'staff'})
        with pytest.raises(AccessError):step(flow,s,'refresh_price',{'manual_edit':True})
    finally:actor.reset(token)


def test_original_scenarios_are_not_new_session_options(flow,engine):
    with pytest.raises(ValueError):flow.create(market_version=flow.simulator.original_version)
    with pytest.raises(ValueError):flow.create(market_version=flow.simulator.replay_version,engine_version=MODEL_VERSION)
    with pytest.raises(ValueError):flow.create(engine_version=engine.version)

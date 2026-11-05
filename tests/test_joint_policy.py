"""Policy examples with hand-computable economics, plus actual full-day integration."""
from pathlib import Path
import json
import math
import pandas as pd
import pytest
from services.joint_policy import pricing,depromo_features,baseline_guard,POLICY
from services.volume_engine import VolumeEngine
from services.volume_scenario import MODEL_VERSION,LEGACY_MODEL_VERSION
from services.engine import ROOT
from services.identity import actor
from services.learning import Learning


class Prep:
    def transform_row(self,f,tier,sku,spec):return f,tier


class Response:
    def __init__(self,function):self.function=function
    def predict(self,rows):return [self.function(f,tier) for f,tier in rows]


SPEC=dict(unit_price_vnd_reference=25000,unit_production_cost_vnd_assumed=12000,
          unit_disposal_cost_vnd_assumed=150,markdown_action_cost_vnd_assumed=350)


def evaluate(stock=100,minute=1290,previous=0,count=0,function=None,**context):
    model=dict(preprocessor=Prep(),model=Response(function or (lambda f,tier:2+60*(tier/50)**2)))
    f=dict(sku_code='TEST',inventory_at_decision=stock,minutes_to_close=1320-minute,
           previous_discount_pct=previous,time=f'{minute//60:02}:{minute%60:02}')
    return pricing(f,dict(current_discount_pct=previous,daily_count=count,**context),model,SPEC)


def test_early_gradual_and_final_deep_clearance_with_positive_net_gain():
    early=evaluate(stock=200,minute=1170)
    assert early['action']==10 and max(c['discount'] for c in early['candidates'])==20
    late=evaluate(stock=100,minute=1290,previous=20,count=2)
    assert late['action']==50 and late['net_gain']>0
    chosen=next(c for c in late['candidates'] if c['discount']==50)
    # Candidate revenue minus HOLD revenue, plus avoided disposal, minus one sticker.
    expected=chosen['expected_sales_to_close']*12500-late['hold_to_close']*20000+chosen['rescued_units']*150-350
    assert chosen['net_gain']==pytest.approx(expected)


def test_popular_high_stock_holds_even_at_final_checkpoint():
    result=evaluate(stock=100,function=lambda f,tier:130+tier)
    assert result['sellout_probability_list']>=.88
    assert result['action']==0 and result['reason']=='SELLOUT_GATE_88'
    assert result['sellout_probability_list']!=min(1,130/100)


def test_protect_2130_availability_separately_from_2200_sellout():
    result=evaluate(stock=100,minute=1170,function=lambda f,tier:1 if f['time']=='21:30' else 24)
    assert result['sellout_probability_hold']<.88
    assert result['availability_probability_2130']<.8
    assert result['reason']=='PROTECT_STOCK_UNTIL_2130' and result['action']==0


def test_no_response_no_discount_and_reserve_final_change():
    assert evaluate(function=lambda f,tier:2)['action']==0
    assert evaluate(minute=1230,previous=20,count=2)['reason']=='RESERVE_FINAL_CLEARANCE'
    assert evaluate(previous=20,count=3)['reason']=='MAX_APPLIED_CHANGES'
    assert evaluate(last_price_change_minute=1280)['reason']=='COOLDOWN'
    manual=evaluate(minute=1200,previous=40,count=1)
    assert manual['cap']==40 and manual['action']==0
    assert any(c['discount']==40 for c in manual['candidates'])


def test_depromo_only_incremental_previous_days_idempotent():
    f=dict(sku_code='TEST',date='2022-05-08',sold_calendar_lag1=20,sold_calendar_lag7=10,sold_last7_observed_mean=80/7)
    history=[dict(sku_code='TEST',date=f'2022-05-{day:02}',sold_qty=20 if day==7 else 10,
                  discounted_qty=12 if day==7 else 0,incremental_promo_qty_estimated=6 if day==7 else 0) for day in range(1,8)]
    history.append(dict(sku_code='TEST',date='2022-05-08',sold_qty=99999,incremental_promo_qty_estimated=99999))
    result=depromo_features(f,history)
    assert result['sold_calendar_lag1']==14  # not 20-12
    assert result['sold_last7_observed_mean']==pytest.approx(74/7)
    assert result['sold_calendar_lag7']==10 and f['sold_calendar_lag1']==20
    assert depromo_features(result,history)==result


def step(flow,s,action,payload=None):return flow.mutate(s['id'],s['revision'],action,payload or {})


def complete(flow,s):
    s=step(flow,s,'plan_approve');s=step(flow,s,'prepared')
    while s['phase']!='close_pending':
        if s['phase']=='price_pending':s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id']})
        elif s['phase']=='price_approved':s=step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
        else:s=step(flow,s,'advance',{'target':1320})
    return step(flow,s,'close')


def test_primary_model_m2_day_bands_and_same_model_for_live(flow,engine,tmp_path):
    learning=Learning(flow.store,engine,tmp_path/'learning')
    assert learning.active().version==MODEL_VERSION
    assert learning.resolve(LEGACY_MODEL_VERSION).version==LEGACY_MODEL_VERSION
    assert learning.resolve(LEGACY_MODEL_VERSION).require_integrity()
    for day,band in [('2022-05-03',(.75,.90)),('2022-05-05',(.45,.50)),('2022-05-06',(.75,.90)),('2022-05-07',(.75,.90))]:
        s=flow.create(day=day)
        assert s['model_version']==MODEL_VERSION
        for row in s['plan']:
            assert band[0]<=row['quantile']<=band[1]
            assert row['prepared']%4==0 and row['prepared']<=row['supply']['capacity']
            assert row['prepared']==row['v4_plan']['initial_qty']+sum(r['qty'] for r in row['v4_plan']['production_batches'])
    with flow.store.read() as db:assert db.execute('SELECT version FROM model_active').fetchone()['version']==MODEL_VERSION
    day='2022-05-03'
    weather=dict(flow.simulator.calendar[day],forecast_source='QA_DECLARED',issued_at=day+'T05:00:00+07:00')
    weather.pop('weather_provenance',None)
    history=flow.simulator.history_before(day,version=flow.simulator.version)
    live=flow.create(day=day,mode='live',history=history,weather=weather,
        outcome_snapshot=flow.simulator.outcomes_before(day,version=flow.simulator.version),source='QA imported POS')
    assert live['model_version']==MODEL_VERSION
    for row in live['plan']:
        assert row['features']['sold_calendar_lag1']==history[('2022-05-02',row['sku'])]
    with pytest.raises(ValueError):flow.create(market_version=flow.simulator.original_version)


def test_real_models_propose_and_applied_counts_not_proposal_counts(flow):
    s=flow.create(day='2022-05-02');s=step(flow,s,'plan_approve');s=step(flow,s,'prepared');s=step(flow,s,'advance',{'target':1170})
    if s['phase']=='running':
        assert all(p['price_changes']==0 for p in s['products'].values())
        return  # HOLD is valid when generated demand already threatens sellout.
    assert s['phase']=='price_pending'
    changed=[r for r in s['pending']['rows'] if r['discount']>r['previous']]
    assert changed and all(r['discount']<=10 for r in changed)
    sku=changed[0]['sku'];before=s['pending']['rows']
    s=step(flow,s,'price_reject',{'proposal_id':s['pending']['id'],'reason':'Review again'})
    assert s['products'][sku]['price_changes']==0
    s=step(flow,s,'refresh_price')
    assert next(r for r in s['pending']['rows'] if r['sku']==sku)['discount']==next(r for r in before if r['sku']==sku)['discount']


def test_full_day_depromo_reaches_next_day_and_no_hidden_future(flow):
    s=complete(flow,flow.create(day='2022-05-02'))
    changed=[r for d in s['decisions'] for r in d['rows'] if r['discount']>r['previous']]
    assert all(r['pricing_policy']['net_gain']>0 for r in changed)
    assert all(p['prepared']==p['sold']+p['stock'] and p['price_changes']<=3 for p in s['products'].values())
    assert sum(p['incremental_promo_qty_estimated'] for p in s['products'].values())>=0
    n=flow.next_day(s['id'])
    for row in n['plan']:
        product=s['products'][row['sku']]
        expected=product['sold'] if product.get('stockout_intervals') or product.get('stockout_since') is not None or product['stock']==0 else product['sold']-product['incremental_promo_qty_estimated']
        assert row['features']['sold_calendar_lag1']==pytest.approx(expected)
        assert not {'unit_events','base_intent_qty','response_draw'} & row['features'].keys()


def test_stockout_sales_remain_lower_bound_during_depromo():
    features=dict(sku_code='TP-DN-001',date='2022-05-03',sold_calendar_lag1=100,
                  sold_calendar_lag7=80,sold_last7_observed_mean=90)
    history=[dict(date='2022-05-02',sku_code='TP-DN-001',sold_qty=100,
                  stockout=1,incremental_promo_qty_estimated=25)]
    adjusted=depromo_features(features,history)
    assert adjusted['sold_calendar_lag1']==100
    assert adjusted['depromo_removed_last7']==0


def test_baseline_guard_does_not_learn_stockout_as_full_demand():
    history=[dict(date=f'2022-04-{d:02}',sku_code='TP-DN-001',sold_qty=100,
                  stockout=0) for d in (4,11,18,25)]
    history.append(dict(date='2022-05-02',sku_code='TP-DN-001',sold_qty=40,stockout=1))
    adjusted,evidence=baseline_guard('2022-05-09','TP-DN-001',history,False,30)
    assert evidence['uncensored_updates']==0
    assert adjusted>=95


def test_online_supply_calibration_uses_prior_residual_without_treating_stockout_as_low_demand():
    baseline=[dict(date=f'2022-06-{d:02}',sku_code='TP-DN-001',sold_qty=100,stockout=0)
              for d in (3,10,17,24)]
    low=dict(date='2022-07-01',sku_code='TP-DN-001',sold_qty=70,prepared_qty=120,
             selected_forecast=120,source_session_id='prior-low',stockout=0)
    high=dict(date='2022-07-01',sku_code='TP-DN-001',sold_qty=120,prepared_qty=120,
              selected_forecast=100,source_session_id='prior-censored',stockout=1)
    _,low_evidence=baseline_guard('2022-07-08','TP-DN-001',baseline+[low],False,110)
    _,high_evidence=baseline_guard('2022-07-08','TP-DN-001',baseline+[high],False,110)
    assert low_evidence['online_updates']==1 and low_evidence['online_factor']<1
    assert high_evidence['online_factor']>1
    assert high_evidence['online_factor']>low_evidence['online_factor']


def test_weekend_calibration_keeps_saturday_and_sunday_separate():
    baseline=[]
    for saturday,sunday in [('2022-06-04','2022-06-05'),('2022-06-11','2022-06-12'),
                            ('2022-06-18','2022-06-19'),('2022-06-25','2022-06-26')]:
        baseline.extend([dict(date=saturday,sku_code='TP-DN-001',sold_qty=100,stockout=0),
                         dict(date=sunday,sku_code='TP-DN-001',sold_qty=200,stockout=0)])
    baseline.extend(dict(date=day,sku_code='TP-DN-001',sold_qty=80,stockout=0)
                    for day in ('2022-06-06','2022-06-07','2022-06-13','2022-06-14'))
    _,saturday=baseline_guard('2022-07-09','TP-DN-001',baseline,True,150)
    _,sunday=baseline_guard('2022-07-10','TP-DN-001',baseline,True,150)
    assert saturday['anchor']==100
    assert sunday['anchor']==pytest.approx(112)
    assert saturday['lower']==pytest.approx(90)
    prior_stockout=dict(date='2022-07-02',sku_code='TP-DN-001',sold_qty=112,
                        prepared_qty=112,stockout=1)
    _,following_saturday=baseline_guard('2022-07-09','TP-DN-001',baseline+[prior_stockout],True,150)
    assert following_saturday['lower']==pytest.approx(98)


def test_training_dates_quantiles_and_censor_lower_bound_manifest():
    report=json.loads((ROOT/'models/joint/manifest.json').read_text(encoding='utf-8'))
    assert report['passed']
    assert report['m1_pos_fit']['last']<'2022-05-01'<=report['m1_pos_validation']['first']
    assert report['quantile_levels']['model_q45']==.45 and report['quantile_levels']['model_q90']==.90
    assert report['censored_m2_rows']>0
    assert all('test_PRIVATE' not in name for name in report['source_sha256'])


def test_three_applied_changes_allowed_fourth_blocked(flow):
    s=flow.create(day='2022-05-02');s=step(flow,s,'plan_approve');s=step(flow,s,'prepared')
    token=actor.set({'id':'manager','username':'manager','role':'manager'})
    try:
        sku='TP-DN-004'
        for minute,tier in [(1170,10),(1200,20),(1230,30)]:
            s=step(flow,s,'advance',{'target':minute})
            s=step(flow,s,'refresh_price',{'manual_edit':True})
            s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:tier},'reason':'Review applied change limit'})
            s=step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
        assert s['products'][sku]['price_changes']==3
        s=step(flow,s,'advance',{'target':1260})
        s=step(flow,s,'refresh_price',{'manual_edit':True})
        s=step(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:40},'reason':'Fourth applied change'})
        with pytest.raises(ValueError):step(flow,s,'price_apply',{'proposal_id':s['pending']['id']})
        assert flow.store.get(s['id'])['products'][sku]['price_changes']==3
    finally:actor.reset(token)


def test_imported_daily_results_keep_incremental_estimate(flow,engine,tmp_path):
    learning=Learning(flow.store,engine,tmp_path/'learning')
    row=dict(date='2022-05-02',sku_code='TP-DN-001',prepared_qty=30,sold_qty=20,waste_qty=10,
        stockout=0,discounted_qty=12,incremental_promo_qty_estimated=6,
        forecast_rain_mm_previous_day1=0,forecast_temperature_max_c_previous_day1=30,
        is_public_holiday=0,is_festival_non_public=0,issued_at='2022-05-02T05:00:00+07:00')
    learning.ingest('qa.csv',pd.DataFrame([row]).to_csv(index=False).encode(),'m2','real')
    saved=learning.outcomes_before('2022-05-03')[('2022-05-02','TP-DN-001')]
    assert saved['sold_qty']==20 and saved['incremental_promo_qty_estimated']==6 and saved['organic_sales_estimated']==14
    with pytest.raises(ValueError):
        learning.ingest('bad.csv',pd.DataFrame([dict(row,incremental_promo_qty_estimated=13)]).to_csv(index=False).encode(),'m2','real')


def test_price_history_handles_zero_sales_manual_price_and_stockout(flow,monkeypatch):
    def past(day,stockout=False):
        return dict(day=day,model_version=MODEL_VERSION,simulator_hash='same',weather={},ledger=[],
            products={'SKU':{'stockout_intervals':[dict(start=1290,end=1320)] if stockout else []}},
            decisions=[dict(minute=1290,status='applied',rows=[dict(sku='SKU',discount=10,approved=20)])])
    monkeypatch.setattr(flow.store,'closed_recent',lambda *a,**kw:[past('2022-05-03',True),past('2022-05-02')])
    state=dict(day='2022-05-05',mode='simulation',seed=42,model_version=MODEL_VERSION,simulator_hash='same',weather={},minute=1290,products={'SKU':dict(discount=20)})
    assert flow.price_history(state,'SKU')==dict(history_days=1,history_rate_next30=0)
    state['products']['SKU']['discount']=0
    assert flow.price_history(state,'SKU')['history_days']==0

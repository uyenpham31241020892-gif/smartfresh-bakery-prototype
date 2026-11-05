from datetime import date,timedelta
import pytest

from services.seasonal_reference import anchor
from services.volume_engine import VolumeEngine
from services.volume_scenario import LEGACY_GENERATED_VERSION,SCALE


def step(flow,state,action,payload=None):
    return flow.mutate(state['id'],state['revision'],action,payload or {})


def test_pos_v3_weekend_lift_is_moderate_and_v2_snapshot_is_preserved(engine,simulator):
    assert simulator.hash_for(LEGACY_GENERATED_VERSION)
    weekdays=[];weekends=[]
    for i in range(14):
        day=(date(2022,7,1)+timedelta(days=i)).isoformat()
        context=simulator.market_context(day,42,[])
        total=sum(context['mean_by_sku'].values())
        (weekends if date.fromisoformat(day).weekday()>=5 else weekdays).append(total)
    assert max(weekends)<1.6*sum(weekdays)/len(weekdays)
    volume=VolumeEngine()
    sku='TP-DN-001';day='2022-07-03'
    raw=[r for r in engine.observed if r['sku_code']==sku]
    scaled=[r for r in volume.observed if r['sku_code']==sku]
    assert anchor(day,scaled,'2022-07-01')==pytest.approx(SCALE*anchor(day,raw,'2022-07-01'))


def test_joint_orders_refills_only_after_observing_elapsed_sales(flow):
    state=flow.create(day='2022-07-01',auto_run=False)
    state=step(flow,state,'plan_approve')
    state=step(flow,state,'prepared')
    assert all(not r['ordered'] for p in state['products'].values() for r in p['refills'] if r['conditional'])
    state=step(flow,state,'advance',{'target':720})
    assert all(r['ordered_at_minute']==720 for p in state['products'].values() for r in p['refills']
               if r['conditional'] and r['ready_time']=='14:00')
    assert all(not r['ordered'] for p in state['products'].values() for r in p['refills']
               if r['conditional'] and r['ready_time']=='17:00')
    state=step(flow,state,'advance',{'target':900})
    assert all(r['ordered_at_minute']==900 for p in state['products'].values() for r in p['refills']
               if r['conditional'] and r['ready_time']=='17:00')
    assert all(p['prepared']<=p['planned_total'] for p in state['products'].values())


def test_seasonal_baseline_bakes_static_quantities_even_on_equal_sku(flow):
    state=flow.create(day='2022-07-01',auto_run=False)
    quantities={p['sku']:p['baseline'] for p in state['plan']}
    state=step(flow,state,'plan_approve',{'quantities':quantities,'reason':'baseline',
                                         'supply_policy':'seasonal_baseline'})
    state=step(flow,state,'prepared')
    assert all(p['planned_total']==quantities[sku] for sku,p in state['products'].items())
    assert all(r['ordered'] and not r['conditional'] for p in state['products'].values() for r in p['refills'])

"""The generated POS must continue through dates absent from the old V4 file."""
from datetime import date
import json
from services.generated_market_worker import process
from services.volume_scenario import VERSION, LEGACY_VOLUME_VERSION


def step(flow, state, action, payload=None):
    return flow.mutate(state['id'], state['revision'], action, payload or {})


def test_chain_generates_missing_v4_day_from_past_baseline(flow):
    state = flow.create(day='2022-05-03')
    state = step(flow, state, 'plan_approve')
    state = step(flow, state, 'prepared')
    while state['phase'] != 'close_pending':
        if state['phase'] == 'price_pending':
            state = step(flow, state, 'price_approve', {'proposal_id': state['pending']['id']})
        elif state['phase'] == 'price_approved':
            state = step(flow, state, 'price_apply', {'proposal_id': state['pending']['id']})
        else:
            state = step(flow, state, 'advance', {'target': 1320})
    state = step(flow, state, 'close')
    following = flow.next_day(state['id'])
    assert following['day'] == '2022-05-04'
    assert following['market_context']['prior_generated_days'] >= 1
    assert following['weather']['forecast_source'] == 'GENERATED_PRIOR_DAY_PROXY'
    assert flow.simulator.evaluation_counts('2022-05-04',flow.simulator.version,
                                            following['market_context'],following['seed'])
    assert date.fromisoformat(following['day']) - date.fromisoformat(state['day']) == __import__('datetime').timedelta(days=1)


def test_generated_market_windows_replay_and_price_response():
    context=dict(version=VERSION,day='2022-05-04',mean_by_sku={'TP-DN-001':120.0})
    request=dict(operation='consume',day='2022-05-04',seed=42,holiday=False,
                 market_context=context,discounts={'TP-DN-001':0},start=480,end=1320)
    full=process(request)['requests']
    split=process(dict(request,end=1170))['requests']+process(dict(request,start=1170))['requests']
    assert sorted(split,key=lambda e:(e['second'],e['event_id']))==full
    assert full==process(request)['requests']
    assert len(full)==process(dict(request,operation='closed_evaluation'))['counts']['TP-DN-001']
    discounted=process(dict(request,discounts={'TP-DN-001':50}))['requests']
    assert {e['event_id'] for e in full}<={e['event_id'] for e in discounted}
    assert len(discounted)>len(full)


def test_legacy_chain_does_not_reuse_old_skipped_day_session(flow):
    old=flow.create(day='2022-05-03')
    old['phase']='closed'
    old['simulator_version']=LEGACY_VOLUME_VERSION
    old['products']={sku:{'sold':0,'prepared':0,'stock':0} for sku in flow.engine.master}
    skipped=dict(old,id='next-'+old['id'],day='2022-05-05',phase='plan_pending')
    with flow.store.connect() as db:
        db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(old),old['id']))
        db.execute('INSERT INTO sessions(id,state) VALUES (?,?)',(skipped['id'],json.dumps(skipped)))
    following=flow.next_day(old['id'])
    assert following['day']=='2022-05-04'
    assert following['id']=='next-v2-'+old['id']
    assert following['simulator_version']==VERSION
    assert following['data_quality']['lineage']['market_transition']==LEGACY_VOLUME_VERSION+' -> '+VERSION

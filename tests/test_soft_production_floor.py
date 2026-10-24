import copy,json
import pytest
from test_api import client
from services.identity import actor,AccessError
from services.engine import SLOTS


def test_manager_48_below_60_is_approved_with_audit_and_actual_inventory(client):
    import app
    s=client.post('/api/sessions',json={}).json();sid=s['id'];row=s['plan'][0];assert row['sku']=='BK-001' and row['floor']==60
    original=copy.deepcopy(s['plan']);r=client.post('/api/sessions/'+sid+'/plan_approve',json={'revision':s['revision'],'payload':{'quantities':{'BK-001':48},'reason':'Ca trước tồn cao, giảm lượng thử nghiệm'}})
    assert r.status_code==200,r.text;s=r.json();assert s['phase']=='plan_approved'
    assert s['plan'][0]['prepared']==original[0]['prepared']==60 and s['plan'][0]['floor']==60 and s['plan'][0]['approved']==48
    a=s['production_approval'];assert a['actor']['role']=='manager' and a['below_floor_skus']==['BK-001'];assert a['reason']
    with app.store.connect() as db:
        event=json.loads(db.execute("SELECT detail FROM audit WHERE session_id=? AND action='PLAN_APPROVE'",(sid,)).fetchone()[0])
    assert event['production_approval']==a and event['before']['quantities']['BK-001']['proposed']==60 and event['after']['quantities']['BK-001']['approved']==48
    s=client.post('/api/sessions/'+sid+'/prepared',json={'revision':s['revision']}).json()
    assert s['products']['BK-001']['prepared']==48 and s['products']['BK-001']['stock']==48
    assert s['totals']['prepared']==284
    assert not app.workflow.safety.incidents(sid),'a valid below-recommendation decision is not a safety incident'


@pytest.mark.parametrize('quantity',[0,-4,1,50,48.5,True,100004])
def test_hard_batch_positive_and_input_limit_still_block_atomic(client,quantity):
    import app
    s=client.post('/api/sessions',json={}).json();before=app.store.get(s['id'])
    r=client.post('/api/sessions/'+s['id']+'/plan_approve',json={'revision':s['revision'],'payload':{'quantities':{'BK-001':quantity},'reason':'Test hard boundary'}})
    assert r.status_code==400 and app.store.get(s['id'])==before


def test_reason_required_and_roles_cannot_override(client):
    import app
    s=client.post('/api/sessions',json={}).json();sid=s['id'];before=app.store.get(sid)
    r=client.post('/api/sessions/'+sid+'/plan_approve',json={'revision':s['revision'],'payload':{'quantities':{'BK-001':52},'reason':'   '}})
    assert r.status_code==400 and app.store.get(sid)==before
    client.post('/api/auth/users',json={'username':'prepstaff','password':'TestPrepPassword123','role':'staff'});client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'prepstaff','password':'TestPrepPassword123'})
    assert client.post('/api/sessions/'+sid+'/plan_approve',json={'revision':s['revision'],'payload':{'quantities':{'BK-001':48},'reason':'Staff attempt'}}).status_code==403
    token=actor.set({'id':'staff','username':'prepstaff','role':'staff'})
    try:
        with pytest.raises(AccessError):app.workflow.do_plan_approve(copy.deepcopy(before),{'quantities':{'BK-001':48},'reason':'Direct service attempt'})
    finally:actor.reset(token)


def test_approved_lower_plan_flows_through_m1_close_reconcile_restart(client):
    import app
    from services.evaluation import reconcile
    from services.store import Store
    s=client.post('/api/sessions',json={}).json();sid=s['id']
    def step(action,payload=None):
        nonlocal s
        r=client.post('/api/sessions/'+sid+'/'+action,json={'revision':s['revision'],'payload':payload or {}});assert r.status_code==200,r.text;s=r.json()
    step('plan_approve',{'quantities':{'BK-001':52},'reason':'Lower preparation with monitoring'});step('prepared')
    for slot in SLOTS:
        step('advance',{'target':slot});pid=s['pending']['id'];step('price_approve',{'proposal_id':pid});step('price_apply',{'proposal_id':pid})
    step('advance',{'target':1320});step('close')
    raw=Store(app.store.path).get(sid);assert raw['production_approval']['below_floor_skus']==['BK-001']
    assert raw['products']['BK-001']['prepared']==52 and reconcile(raw)['publishable']
    assert s['totals']['prepared']==288 and s['totals']['sold']+s['totals']['waste']==288


def test_fallback_manager_below_recommended_floor_is_allowed(client):
    s=client.post('/api/sessions',json={}).json();sid=s['id']
    r=client.post('/api/safety/control',json={'session_id':sid,'revision':s['revision'],'action':'mode','value':'manual','reason':'Manager preparation decision'});assert r.status_code==200;s=r.json()['state']
    assert s['prediction_origin']=='RULE_ROLLING7'
    r=client.post('/api/sessions/'+sid+'/plan_approve',json={'revision':s['revision'],'payload':{'quantities':{'BK-001':48},'reason':'Override advisory floor in manual'}})
    assert r.status_code==200,r.text
    assert r.json()['production_approval']['rows'][0]['below_recommended_floor']

import copy
import json
import shutil
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from services.engine import Engine, ROOT
from services.workflow import Workflow
from services.safety import GuardError
from services.identity import Identity, actor, AccessError
from test_api import client


def action(flow,s,name,payload=None,key=None):return flow.mutate(s['id'],s['revision'],name,payload,key)


def started(flow,operation_mode='assisted'):
    s=flow.create(operation_mode=operation_mode)
    s=action(flow,s,'plan_approve');s=action(flow,s,'prepared')
    return action(flow,s,'advance',{'target':1170})


def test_no_unauthenticated_api_or_role_header_bypass(client):
    import app
    guest=TestClient(app.app)
    assert guest.get('/api/state').status_code==401
    assert guest.post('/api/sessions',json={},headers={'X-Role':'manager'}).status_code==401
    assert guest.get('/api/auth/status').json()['setup_needed'] is False
    assert guest.post('/api/auth/setup',json={'username':'hijacker','password':'NotAllowed123'}).status_code==403


@pytest.mark.parametrize('role',['staff','viewer'])
def test_real_backend_roles_block_approval_and_security_settings(client,role):
    import app
    assert client.post('/api/auth/users',json={'username':role+'test','password':'GD6-test-password','role':role}).status_code==200
    other=TestClient(app.app)
    assert other.post('/api/auth/login',json={'username':role+'test','password':'wrong'}).status_code==403
    login=other.post('/api/auth/login',json={'username':role+'test','password':'GD6-test-password'})
    assert login.status_code==200 and 'HttpOnly' in login.headers['set-cookie']
    s=client.get('/api/state').json()
    for path,data in [('/api/sessions/'+s['id']+'/plan_approve',{'revision':s['revision'],'payload':{'actor':{'role':'manager'}}}),
                      ('/api/ai/settings',{'api_key':'fake','model':'fake'}),
                      ('/api/safety/control',{'session_id':s['id'],'revision':s['revision'],'action':'mode','value':'manual','reason':'Try escalation'}),
                      ('/api/auth/users',{'username':'elevated','password':'GD6-test-password','role':'manager'})]:
        assert other.post(path,json=data).status_code==403
    assert other.get('/api/state').status_code==200
    r=other.post('/api/sessions',json={})
    assert r.status_code==(200 if role=='staff' else 403)
    other.post('/api/auth/logout');assert other.get('/api/state').status_code==401


def test_passwords_are_hashed_sessions_expire_and_bad_logins_lock(client):
    import app
    with app.store.connect() as db:
        u=db.execute('SELECT * FROM local_users').fetchone()
        assert u['password_hash']!='TestPass-GD6-123' and len(u['salt'])==32
    guest=TestClient(app.app)
    for _ in range(5):assert guest.post('/api/auth/login',json={'username':'testmanager','password':'wrong'}).status_code==403
    locked=guest.post('/api/auth/login',json={'username':'testmanager','password':'TestPass-GD6-123'})
    assert locked.status_code==403 and '5 phút' in locked.json()['error']
    with app.store.connect() as db:db.execute('UPDATE login_sessions SET expires=0')
    assert client.get('/api/state').status_code==401


def test_identity_is_persistent_and_audit_uses_authenticated_actor(client):
    import app
    s=client.get('/api/state').json()
    r=client.post('/api/sessions/'+s['id']+'/plan_approve',json={'revision':0,'payload':{'reason':'Approved by logged-in Manager','actor':'forged'}})
    assert r.status_code==200
    detail=json.loads(app.store.audit(s['id'])[0]['detail'])
    assert detail['actor']['username']=='testmanager' and detail['actor']['role']=='manager'
    assert detail['model_hashes'] and detail['feature_snapshot_id']
    assert detail['before']['phase']=='plan_pending' and detail['after']['phase']=='plan_approved'
    restarted=Identity(app.store)
    assert restarted.authenticate(client.cookies.get('smartfresh_auth'))['role']=='manager'


def test_rule_violation_survives_rollback_and_deduplicates(flow):
    s=flow.create()
    for _ in range(2):
        with pytest.raises(GuardError):action(flow,s,'plan_approve',{'quantities':{'BK-001':1},'reason':'Forbidden quantity'})
    assert flow.store.get(s['id'])==s
    incidents=flow.safety.incidents(s['id'])
    assert len(incidents)==1 and incidents[0]['kind']=='HARD_RULE_BLOCK'
    assert flow.safety.control(s['id'])['mode']=='manual'


def test_model_m2_exception_falls_back_without_bypassing_quality(flow,monkeypatch):
    monkeypatch.setattr(flow.engine,'plan',lambda *args:(_ for _ in ()).throw(RuntimeError('M2 unavailable')))
    s=flow.create()
    assert s['prediction_origin']=='RULE_ROLLING7' and s['phase']=='plan_pending'
    assert all(p['prepared']%4==0 and p['prepared']>=p['floor'] and p['contributions']==[] for p in s['plan'])
    assert flow.safety.incidents(s['id'])[0]['kind']=='M2_UNAVAILABLE'
    with pytest.raises(ValueError,match='leakage'):flow.create(history={('2022-08-16','BK-001'):8})


def test_m1_exception_keeps_effective_price_until_manager_applies(flow,monkeypatch):
    s=flow.create();s=action(flow,s,'plan_approve');s=action(flow,s,'prepared')
    before={k:v['discount'] for k,v in s['products'].items()}
    monkeypatch.setattr(flow.engine,'price',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('M1 down')))
    s=action(flow,s,'advance',{'target':1170})
    assert s['pending']['origin']=='MANUAL_RULE'
    assert {k:v['discount'] for k,v in s['products'].items()}==before
    assert flow.safety.control(s['id'])['mode']=='manual'
    assert flow.safety.incidents(s['id'])[0]['kind']=='M1_UNAVAILABLE'
    s=action(flow,s,'price_approve',{'proposal_id':s['pending']['id']})
    assert {k:v['discount'] for k,v in s['products'].items()}==before


def test_stale_stock_blocks_manual_and_ai_prices_and_live_fault_drill(flow):
    s=started(flow)
    s=flow.safety.fault(s['id'],'stale_stock','Test stale stock',s['revision'])
    s=action(flow,s,'refresh_price')
    assert s['pending']['rows']==[]
    with pytest.raises(ValueError):action(flow,s,'price_approve',{'proposal_id':s['pending']['id']})
    live=flow.create(mode='live')
    with pytest.raises(GuardError,match='mô phỏng'):flow.safety.fault(live['id'],'m2_error','Not allowed live',0)


def test_manual_fallback_still_enforces_floor_cap_no_rollback(flow):
    s=started(flow)
    s=flow.safety.set_mode(s['id'],'manual','Manual operations',s['revision'])
    s=action(flow,s,'refresh_price')
    for target in [1170,1200,1230,1260]:
        if s['minute']!=target:s=action(flow,s,'advance',{'target':target})
        assert s['pending']['origin']=='MANUAL_RULE'
        assert all(r['discount']>=r['floor'] and r['discount']<=r['cap'] for r in s['pending']['rows'])
        if target==1260:
            assert all(r['discount']>=30 for r in s['pending']['rows'])
            with pytest.raises(GuardError):action(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{'BK-001':20},'reason':'invalid'})
            break
        s=action(flow,s,'price_approve',{'proposal_id':s['pending']['id']});s=action(flow,s,'price_apply',{'proposal_id':s['pending']['id']})


def test_shadow_records_decision_without_changing_transaction_price(flow):
    s=started(flow,'shadow');old=copy.deepcopy(s['products'])
    discounts={r['sku']:20 for r in s['pending']['rows']}
    s=action(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':discounts,'reason':'Shadow test'})
    pid=s['pending']['id'];s=action(flow,s,'price_apply',{'proposal_id':pid},'shadow-key')
    assert s['products']==old and s['decisions'][-1]['status']=='shadow_only'
    duplicate=flow.mutate(s['id'],s['revision']-1,'price_apply',{'proposal_id':pid},'shadow-key')
    assert duplicate==s


def test_mode_change_invalidates_approved_price_and_stale_revision(flow):
    s=started(flow);s=action(flow,s,'price_approve',{'proposal_id':s['pending']['id']});pid=s['pending']['id'];oldrev=s['revision']
    s=flow.safety.set_mode(s['id'],'manual','Freeze AI',oldrev)
    assert s['pending'] is None and s['decisions'][-1]['status']=='expired_mode_change'
    with pytest.raises(ValueError):flow.mutate(s['id'],oldrev,'price_apply',{'proposal_id':pid})


def test_recovery_requires_ack_clear_verify_resolve_then_explicit_enable(flow):
    s=flow.create();s=flow.safety.fault(s['id'],'m2_error','Drill failure',0)
    s=action(flow,s,'replan');iid=flow.safety.incidents(s['id'])[0]['id']
    with pytest.raises(ValueError):flow.safety.transition(iid,'resolve','Cannot skip acknowledgement')
    flow.safety.transition(iid,'acknowledge','Manager owns incident')
    with pytest.raises(GuardError):flow.safety.transition(iid,'verify','Fault still set')
    s=flow.safety.fault(s['id'],'clear','Fault removed',s['revision'])
    with pytest.raises(GuardError):flow.safety.transition(iid,'resolve','Cannot skip verification')
    receipt=flow.safety.transition(iid,'verify','Artifact and smoke checks')
    assert receipt['verification']['passed']
    with pytest.raises(GuardError):flow.safety.set_mode(s['id'],'assisted','Still open',s['revision'])
    flow.safety.transition(iid,'resolve','Verified and resolved')
    assert flow.safety.control(s['id'])['mode']=='manual'
    s=flow.safety.set_mode(s['id'],'assisted','Manager resumes AI',s['revision'])
    s=action(flow,s,'replan');assert s['prediction_origin']=='AI_M2'


def test_recovery_receipt_invalidated_by_new_revision(flow):
    s=flow.create();flow.safety.report(s['id'],'TEST','Audit recovery')
    iid=flow.safety.incidents(s['id'])[0]['id'];flow.safety.transition(iid,'acknowledge','Owner acknowledges')
    flow.safety.transition(iid,'verify','Run verification')
    s=action(flow,s,'plan_approve')
    with pytest.raises(GuardError,match='đổi'):flow.safety.transition(iid,'resolve','Stale verification')


def test_corrupted_model_startup_remains_safe_and_restore_verifiable(flow,simulator,tmp_path):
    directory=tmp_path/'bundle';shutil.copytree(ROOT/'models',directory)
    raw=(directory/'m2.txt').read_bytes();(directory/'m2.txt').write_bytes(raw+b'corrupt')
    with pytest.raises(ValueError,match='checksum'):Engine(directory)
    degraded=Engine(directory,allow_degraded=True)
    assert degraded.artifact_error and degraded.m2 is None
    isolated=Workflow(degraded,simulator,flow.store)
    s=isolated.create();assert s['prediction_origin']=='RULE_ROLLING7'
    (directory/'m2.txt').write_bytes(raw)
    isolated.safety.verify_state(isolated.store.get(s['id']))
    assert degraded.m2 is not None


def test_runtime_hash_tampering_blocks_model_inference(flow,tmp_path,simulator):
    directory=tmp_path/'bundle';shutil.copytree(ROOT/'models',directory);e=Engine(directory)
    isolated=Workflow(e,simulator,flow.store);s=isolated.create()
    (directory/'m1.txt').write_text('tampered')
    with pytest.raises(ValueError,match='checksum'):e.plan(s['day'],simulator.seed,s['weather'])
    s=action(isolated,s,'plan_approve');s=action(isolated,s,'prepared');s=action(isolated,s,'advance',{'target':1170})
    assert s['pending']['origin']=='MANUAL_RULE'
    assert isolated.safety.incidents(s['id'])


def test_safety_api_drill_lifecycle_and_rollback_receipt(client):
    s=client.get('/api/state').json()
    def control(action,value,revision):return client.post('/api/safety/control',json={'session_id':s['id'],'revision':revision,'action':action,'value':value,'reason':'GD6 test operator'})
    r=control('drill','m2_error',s['revision']);assert r.status_code==200,r.text
    s=r.json()['state'];assert s['prediction_origin']=='RULE_ROLLING7'
    report=client.get('/api/safety',params={'session_id':s['id']}).json();iid=report['incidents'][0]['id']
    assert client.post('/api/safety/incidents/'+iid,json={'action':'acknowledge','reason':'Test owner'}).status_code==200
    r=control('drill','clear',s['revision']);s=r.json()['state']
    for a in ['verify','resolve']:assert client.post('/api/safety/incidents/'+iid,json={'action':a,'reason':'Recovery evidence'}).status_code==200
    r=control('mode','assisted',s['revision']);assert r.status_code==200,r.text
    s=r.json()['state'];assert s['prediction_origin']=='AI_M2'
    r=control('rollback_drill','',s['revision']);assert r.status_code==200,r.text
    assert r.json()['drill']['passed'] and not r.json()['drill']['changed_active_model']


def test_cross_port_origin_and_dns_rebinding_host_are_denied(client):
    assert client.post('/api/sessions',json={},headers={'origin':'http://testserver:9999'}).status_code==403
    assert client.get('/api/state',headers={'host':'evil.example'}).status_code==403


def test_existing_uploaded_database_is_preserved_during_local_auth_migration(tmp_path):
    import zipfile
    original=ROOT.parents[2]/'upload/smartfresh-bakery-prototype(4).zip'
    if not original.exists():pytest.skip('Original user archive not bundled in source; migration integration test is optional.')
    with zipfile.ZipFile(original) as z:
        name=next(n for n in z.namelist() if n.endswith('/runtime/smartfresh.sqlite3'))
        path=tmp_path/'old.sqlite3';path.write_bytes(z.read(name))
    from services.store import Store
    store=Store(path)
    with store.connect() as db:before=[tuple(r) for r in db.execute('SELECT id,state FROM sessions ORDER BY id')]
    Identity(store)
    with store.connect() as db:after=[tuple(r) for r in db.execute('SELECT id,state FROM sessions ORDER BY id')]
    assert before==after

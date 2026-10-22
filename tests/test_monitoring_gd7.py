import copy
import json
import math
import pytest
from services.monitoring import Monitoring, metric, distribution, DEFAULTS
from services.engine import SLOTS
from services.identity import actor
from test_api import client


def monitor(flow):return Monitoring(flow.store,flow.engine,flow.simulator,flow)

def close(flow,mode='simulation'):
    s=flow.create(mode=mode);s=flow.mutate(s['id'],s['revision'],'plan_approve');s=flow.mutate(s['id'],s['revision'],'prepared')
    for slot in SLOTS:
        s=flow.mutate(s['id'],s['revision'],'advance',{'target':slot})
        if not s['pending']['rows']:
            s=flow.mutate(s['id'],s['revision'],'confirm_zero_sales',{'confirmed':True,'reason':'Checked no sales in isolated test'})
        pid=s['pending']['id'];s=flow.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':pid});s=flow.mutate(s['id'],s['revision'],'price_apply',{'proposal_id':pid})
    s=flow.mutate(s['id'],s['revision'],'advance',{'target':1320})
    return flow.mutate(s['id'],s['revision'],'close')


def test_metric_zero_actual_is_na_and_weighted_formula_is_correct():
    assert metric([])['wape_pct'] is None
    m=metric([{'prediction':3,'actual':0}]);assert m['wape_pct'] is None and m['mae']==3 and m['bias_pct'] is None
    m=metric([{'prediction':12,'actual':10},{'prediction':0,'actual':2}])
    assert m['wape_pct']==pytest.approx(100/3) and m['mae']==2 and m['bias_pct']==0


def test_psi_and_ks_finite_for_constant_and_shifted_distribution():
    same=distribution([2]*40,[2]*40)
    assert same['psi']==pytest.approx(0) and same['ks_statistic']==0
    shift=distribution([2]*40,[20]*40)
    assert math.isfinite(shift['psi']) and shift['psi']>0 and shift['ks_statistic']==1
    assert distribution([],[])['psi'] is None


def test_open_session_has_no_target_and_no_future_simulator_read(flow,monkeypatch):
    s=flow.create();before=copy.deepcopy(s);m=monitor(flow)
    monkeypatch.setattr(flow.simulator,'events',lambda *a,**k:pytest.fail('Open day may not reveal future demand'))
    d=m.snapshot(s['id'])
    assert d['accuracy']==[] and d['overview']['closed_metric_rows']==0
    assert all(r['status']=='INSUFFICIENT' for r in d['drift']['data'])
    assert flow.store.get(s['id'])==before


def test_closed_simulator_uses_base_arrivals_and_is_cached(flow,monkeypatch):
    s=close(flow);m=monitor(flow)
    expected=sum(not e['promo'] for e in flow.simulator.events(s['day'],s['seed'],s['weather'],s['simulator_version']))
    rows=m.closed_evaluation(s)
    assert len(rows)==8 and sum(r['actual'] for r in rows)==expected
    assert all(r['target_kind']=='synthetic_base_demand' for r in rows)
    monkeypatch.setattr(flow.simulator,'events',lambda *a,**k:pytest.fail('Cached evaluation should be immutable for same closed snapshot'))
    assert m.closed_evaluation(s)==rows


def test_unavailable_simulator_does_not_substitute_sales_for_demand(flow):
    s=close(flow);s['simulator_hash']='unavailable-version'
    m=monitor(flow);assert m.closed_evaluation(s)==[]


def test_live_sales_proxy_and_rule_fallback_never_merge_with_ai_demand(flow):
    sim=close(flow);live=close(flow,'live');m=monitor(flow)
    rows=m.closed_evaluation(sim)+m.closed_evaluation(live)
    extra=copy.deepcopy(rows[0]);extra['origin']='RULE_ROLLING7';rows.append(extra)
    groups=m.accuracy(rows)
    assert len(groups)==3
    proxy=next(g for g in groups if g['target_kind']=='observed_sales_proxy')
    assert proxy['metrics']['wape_pct'] is None and proxy['metrics']['n']==8
    assert all(len(g['daily'])==1 for g in groups)


def test_reference_excludes_targets_is_train_only_and_hash_checked(flow):
    m=monitor(flow);rows,ref=m.reference(flow.engine)
    assert ref['available'] and rows
    assert all(r['date']<='2022-08-15' for r in rows)
    assert not any('target' in k or 'hidden' in k for r in rows for k in r)
    learned=copy.copy(flow.engine);learned.manifest={**flow.engine.manifest,'parent':'old-model'}
    assert not m.reference(learned)[1]['available']


def test_drift_requires_distinct_days_and_does_not_invent_threshold(flow):
    m=monitor(flow);s=flow.create();row={'day':s['day'],'model_version':flow.engine.version,'origin':'AI_M2','features':s['plan'][0]['features']}
    d=m.drift([row]*40,[],flow.engine,DEFAULTS)
    assert all(r['status']=='INSUFFICIENT' for r in d['data'])
    assert d['data'][0]['current_days']==1


def test_sandbox_isolated_reproducible_metrics_and_drift_alerts(flow):
    m=monitor(flow);s=flow.create();before=flow.store.get(s['id']);original=flow.engine.manifest.copy()
    sandbox=m.sandbox();assert sandbox['policy']=='evaluation_only_no_workflow_mutation'
    d=m.snapshot(s['id'],source='sandbox',sandbox_id=sandbox['id'])
    assert d['scope']['source']=='sandbox' and len(d['accuracy'])==1 and d['accuracy'][0]['metrics']['n']==224
    assert d['drift']['performance'][0]['status']=='REVIEW'
    assert any(r['status']=='REVIEW' for r in d['drift']['data'])
    assert {'DATA_DRIFT','PERFORMANCE_DRIFT'}<={a['code'] for a in d['alerts'] if a['active']}
    assert d['business']['groups']==[]
    assert flow.store.get(s['id'])==before and flow.engine.manifest==original
    assert len(flow.store.sessions())==1 and flow.safety.incidents(s['id'])==[]
    assert m.settings()['psi_threshold'] is None


def test_filters_and_slices_are_grounded_and_bad_dates_rejected(flow):
    s=close(flow);m=monitor(flow);d=m.snapshot(s['id'],sku='BK-001')
    assert d['accuracy'][0]['metrics']['n']==1
    assert [r['slice'] for r in d['accuracy'][0]['slices']['sku']]==['BK-001']
    empty=m.snapshot(s['id'],date_from='2026-01-01');assert empty['accuracy']==[]
    with pytest.raises(ValueError):m.snapshot(s['id'],date_from='2022-09-01',date_to='2022-08-01')


def test_monitoring_separates_proposed_applied_shadow_and_blocked_incidents(flow):
    s=close(flow);m=monitor(flow)
    shadow=copy.deepcopy(s);shadow['id']='shadow';shadow['decisions'][0]['status']='shadow_only'
    d=m.safety([s,shadow])
    assert d['checked_applied_rows']==72 and d['applied_violations']==0
    bad=copy.deepcopy(s);bad['id']='bad';bad['decisions'][0]['rows'][0]['approved']=99
    assert m.safety([bad])['applied_violations']==1
    q=m.business([bad]);assert q['groups'][0]['lost_simulator_only'] is not None
    bad['products']['BK-001']['revenue']+=1
    assert m.business([bad])['mismatches']


def test_alert_ack_persists_and_new_evidence_reopens_without_mode_change(flow):
    s=flow.create();m=monitor(flow)
    sample={'code':'CHECK','severity':'review','title':'Test','message':'Needs review','evidence':{'count':1}}
    a=m.sync_alerts('testscope',[sample])[0]
    m.acknowledge(a['id'],a['evidence_hash'],'Operator read evidence')
    assert m.sync_alerts('testscope',[sample])[0]['ack_by']=='system'
    restarted=monitor(flow)
    assert restarted.sync_alerts('testscope',[sample])[0]['ack_by']=='system'
    changed={**sample,'evidence':{'count':2}}
    assert m.sync_alerts('testscope',[changed])[0]['ack_by'] is None
    with pytest.raises(ValueError):m.acknowledge(a['id'],a['evidence_hash'],'Stale evidence')
    assert not m.sync_alerts('testscope',[])[0]['active']
    assert flow.safety.control(s['id'])['mode']=='assisted'


def test_threshold_configuration_versioned_and_logged(flow):
    m=monitor(flow);assert m.settings()['psi_threshold'] is None
    c=m.configure({'expected_version':0,'psi_threshold':.3,'performance_delta_pp':7,'calibration_note':'Experimental local threshold, not SLA'})
    assert c['version']==1 and c['psi_threshold']==.3
    with pytest.raises(ValueError):m.configure({'expected_version':0,'calibration_note':'Old client setting'})
    with flow.store.connect() as db:assert db.execute("SELECT COUNT(*) FROM audit WHERE action='MONITORING_CONFIG_CHANGED'").fetchone()[0]==1


def test_http_metrics_use_real_status_latency_and_do_not_persist_credentials(client):
    import app
    s=client.get('/api/state').json()
    r=client.get('/api/state?session_id=missing&api_key=DO_NOT_STORE_SECRET')
    assert r.status_code==400 and len(r.headers['X-Request-ID'])==32
    d=client.get('/api/monitoring',params={'session_id':s['id']}).json()
    assert d['operations']['http']['http_4xx']>=1 and d['operations']['http']['p95_ms'] is not None
    with app.store.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM monitoring_http')]
    assert 'DO_NOT_STORE_SECRET' not in json.dumps(rows)
    assert not any(r['route'].startswith('/api/monitoring') for r in rows)


def test_api_monitoring_roles_and_existing_sessions_preserved(client):
    import app
    from fastapi.testclient import TestClient
    s=client.get('/api/state').json();before=app.store.get(s['id'])
    for role in ['staff','viewer']:
        assert client.post('/api/auth/users',json={'username':'mon'+role,'password':'GD7-test-password','role':role}).status_code==200
        other=TestClient(app.app);other.post('/api/auth/login',json={'username':'mon'+role,'password':'GD7-test-password'})
        assert other.get('/api/monitoring',params={'session_id':s['id']}).status_code==200
        assert other.post('/api/monitoring/sandbox',json={'session_id':s['id']}).status_code==403
        assert other.post('/api/monitoring/config',json={'expected_version':0,'calibration_note':'Not allowed role'}).status_code==403
    assert app.store.get(s['id'])==before
    r=client.post('/api/monitoring/sandbox',json={'session_id':s['id']});assert r.status_code==200,r.text
    d=client.get('/api/monitoring',params={'session_id':s['id'],'source':'sandbox','sandbox_id':r.json()['id']})
    assert d.status_code==200,d.text
    a=next(x for x in d.json()['alerts'] if x['active'])
    r=client.post('/api/monitoring/alerts/'+a['id']+'/acknowledge',json={'evidence_hash':a['evidence_hash'],'note':'Reviewed demonstration only'})
    assert r.status_code==200
    assert app.store.get(s['id'])==before


def test_job_runtime_failures_rejections_and_restart_are_distinct(flow):
    m=monitor(flow)
    with Monitoring.job(flow.store,'SUCCESS'):pass
    with pytest.raises(RuntimeError):
        with Monitoring.job(flow.store,'FAILURE'):raise RuntimeError('SECRET_MUST_NOT_BE_STORED')
    with pytest.raises(ValueError):
        with Monitoring.job(flow.store,'REJECTED'):raise ValueError('Invalid data')
    with flow.store.connect() as db:
        db.execute("INSERT INTO monitoring_jobs VALUES ('stopped','INTERRUPTED',NULL,'running','2099-01-01',NULL,NULL,NULL)")
    Monitoring.recover_jobs(flow.store)
    with flow.store.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM monitoring_jobs')]
    assert {r['status'] for r in rows}=={'succeeded','failed','rejected','interrupted'}
    assert 'SECRET_MUST_NOT_BE_STORED' not in json.dumps(rows)


def test_telemetry_records_actual_server_failure(client,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    safe=TestClient(app.app,raise_server_exceptions=False)
    safe.cookies.update(client.cookies)
    with monkeypatch.context() as patch:
        patch.setattr(app.workflow,'create',lambda **kwargs:(_ for _ in ()).throw(RuntimeError('injected API failure')))
        assert safe.post('/api/sessions',json={}).status_code==500
    s=client.get('/api/state').json()
    d=client.get('/api/monitoring',params={'session_id':s['id']}).json()
    assert d['operations']['http']['http_5xx']>=1
    assert any(a['code']=='HTTP_5XX' and a['active'] for a in d['alerts'])


def test_monitoring_upgrade_preserves_existing_users_tokens_and_sessions(flow):
    from services.identity import Identity
    identity=Identity(flow.store)
    identity.create('existingmanager','Existing-GD6-Password',bootstrap=True)
    token,_=identity.login('existingmanager','Existing-GD6-Password')
    s=flow.create()
    with flow.store.connect() as db:
        before_users=[tuple(r) for r in db.execute('SELECT * FROM local_users')]
        before_tokens=[tuple(r) for r in db.execute('SELECT * FROM login_sessions')]
        before_states=[tuple(r) for r in db.execute('SELECT id,state FROM sessions')]
    m=monitor(flow);m.snapshot(s['id'])
    with flow.store.connect() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM local_users')]==before_users
        assert [tuple(r) for r in db.execute('SELECT * FROM login_sessions')]==before_tokens
        assert [tuple(r) for r in db.execute('SELECT id,state FROM sessions')]==before_states
    assert Identity(flow.store).authenticate(token)['username']=='existingmanager'

import copy
import json
import pytest
from services.evaluation import Evaluation,reconcile
from services.learning import Learning
from services.store import Store
from services.identity import actor
from test_learning import daily
from test_monitoring_gd7 import close
from test_api import client


def test_reconciliation_provisional_closed_and_certification(flow,engine,tmp_path):
    s=flow.create();assert reconcile(s)['status']=='PROVISIONAL';assert reconcile(s)['kpis'] is None
    s=close(flow);r=reconcile(s);assert r['publishable']
    assert sum(x['prepared'] for x in r['rows'])==sum(x['sold']+x['waste'] for x in r['rows'])
    assert r['kpis']['revenue']==sum(t['paid'] for t in s['ledger'])
    e=Evaluation(flow.store,Learning(flow.store,engine,tmp_path/'models'))
    before=flow.store.get(s['id']);token=actor.set({'id':'manager','username':'testmanager','role':'manager'})
    try:
        receipt=e.certify(s['id'],r['revision'],r['state_sha256'],'Đã kiểm tra sổ')
        assert receipt['actor']['username']=='testmanager'
        assert e.certify(s['id'],r['revision'],r['state_sha256'],'Lặp lại')['id']==receipt['id']
        with pytest.raises(ValueError):e.certify(s['id'],r['revision']-1,r['state_sha256'],'Stale')
    finally:actor.reset(token)
    assert e.report(s['id'])['receipt_current']
    assert before==flow.store.get(s['id'])


def test_bad_line_math_unknown_sku_and_report_mismatch_block_publication(flow):
    s=close(flow);assert s['ledger']
    bad=copy.deepcopy(s);bad['ledger'][0]['unit_price']+=1
    assert not reconcile(bad)['publishable'];assert reconcile(bad)['kpis'] is None
    bad=copy.deepcopy(s);bad['ledger'][0]['sku']='UNKNOWN'
    assert reconcile(bad)['errors']
    bad=copy.deepcopy(s);next(iter(bad['products'].values()))['revenue']+=1
    assert reconcile(bad)['status']=='MISMATCH'
    from services.monitoring import Monitoring
    result=Monitoring.business([bad,s]);assert len(result['daily'])==1 and result['mismatches']


def test_close_rejects_line_math_even_when_total_matches(flow):
    s=close(flow);s['phase']='close_pending';s['ledger'][0]['unit_price']+=1
    with pytest.raises(ValueError,match='Đối soát'):flow.do_close(s,{})
    assert s['phase']=='close_pending'


def test_sensitivity_isolated_and_monotonic(flow,engine,tmp_path):
    s=close(flow);e=Evaluation(flow.store,Learning(flow.store,engine,tmp_path/'models'))
    before=copy.deepcopy(flow.store.get(s['id']));r=e.sensitivity(s['id'])
    assert len(r['scenarios'])==3
    values=[x['incremental_units_sum'] for x in r['scenarios']]
    assert values==sorted(values) and values[-1]>0
    assert flow.store.get(s['id'])==before


def test_registry_fresh_holdout_no_fit_no_reuse_and_restart(engine,tmp_path):
    l=Learning(Store(tmp_path/'db.sqlite'),engine,tmp_path/'artifacts')
    df=daily(engine);l.ingest('train.csv',df.to_csv(index=False).encode(),'m2');r=l.train('m2')
    with pytest.raises(ValueError,match='7 ngày'):l.fresh_holdout(r['id'])
    l.ingest('new.csv',daily(engine,70).iloc[504:].to_csv(index=False).encode(),'m2')
    model=l.resolve(r['id']);before=(model.model_dir/'m2.txt').read_bytes();active=l.active().version
    h=l.fresh_holdout(r['id']);assert h['rows']==56 and h['from']>r['evaluated_until'] and h['passed']
    assert (model.model_dir/'m2.txt').read_bytes()==before and l.active().version==active
    with pytest.raises(ValueError,match='7 ngày'):l.fresh_holdout(r['id'])
    versions=Learning(l.store,engine,l.root).registry()['versions'];v=next(v for v in versions if v['version']==r['id'])
    assert v['integrity'] and all(v['compatibility'].values()) and len(v['holdouts'])==1
    l.promote(r['id'],engine.version,'Đánh giá đạt')
    l.rollback(r['id'],'Diễn tập quay lại')
    assert l.active().version==engine.version


def test_failed_fresh_holdout_blocks_promotion(engine,tmp_path):
    l=Learning(Store(tmp_path/'db.sqlite'),engine,tmp_path/'artifacts');l.ingest('x.csv',daily(engine).to_csv(index=False).encode(),'m2');r=l.train('m2')
    with l.store.connect() as db:db.execute('INSERT INTO model_holdouts VALUES (?,?,?)',('failed',r['id'],json.dumps({'passed':False})))
    with pytest.raises(ValueError,match='không đạt'):l.promote(r['id'],engine.version,'Should block')
    assert l.active().version==engine.version


def test_incompatible_policy_and_tampered_artifact_block_promotion(engine,tmp_path):
    l=Learning(Store(tmp_path/'db.sqlite'),engine,tmp_path/'artifacts');l.ingest('x.csv',daily(engine).to_csv(index=False).encode(),'m2');r=l.train('m2');e=l.resolve(r['id'])
    original=copy.deepcopy(e.selection);e.selection['selected_q']=.1
    assert not l.compatible(e,engine)['same_policy'];e.selection=original
    with (e.model_dir/'m2.txt').open('a') as f:f.write('\nCORRUPTED')
    assert next(v for v in l.registry()['versions'] if v['version']==r['id'])['integrity'] is False
    with pytest.raises(ValueError):l.promote(r['id'],engine.version,'Must reject')


def test_api_auth_kpi_suppression_and_no_f04(client):
    import app
    c=client;s=c.post('/api/sessions',json={}).json();sid=s['id']
    assert c.get('/api/evaluation/'+sid).json()['kpis'] is None
    assert c.get('/api/registry').status_code==200
    assert c.post('/api/evaluation/'+sid+'/certify',json={'revision':s['revision'],'state_sha256':'bad','reason':'Test'}).status_code==400
    c.post('/api/auth/users',json={'username':'evalstaff','password':'testpassword123','role':'staff'})
    c.post('/api/auth/logout');c.post('/api/auth/login',json={'username':'evalstaff','password':'testpassword123'})
    assert c.get('/api/evaluation/'+sid).status_code==200
    assert c.post('/api/evaluation/'+sid+'/certify',json={'revision':s['revision'],'state_sha256':'bad','reason':'Test'}).status_code==403
    assert c.post('/api/learning/invalid/holdout',json={}).status_code==403
    from pathlib import Path
    js=Path('web/app.js').read_text();assert 'function reportReference' not in js and 'Baseline và M1 + M2' not in js


def test_m1_fresh_holdout_and_zero_actual_metrics(engine,tmp_path):
    import pandas as pd
    from services.engine import LADDER,FLOORS,CAPS
    l=Learning(Store(tmp_path/'db.sqlite'),engine,tmp_path/'artifacts');records=[]
    for r in daily(engine,49).to_dict('records'):
        for j in range(5):
            for tier in LADDER:
                if FLOORS[j]<=tier<=CAPS[j]:records.append({**r,'slot':j,'discount_pct':tier,'incremental_promo_qty':0,'measurement_method':'controlled_increment','experiment_id':f'holdout-{j}-{tier}'})
    df=pd.DataFrame(records);l.ingest('train.csv',df[df.date<='2024-02-11'].to_csv(index=False).encode(),'m1');r=l.train('m1')
    l.ingest('fresh.csv',df[df.date>'2024-02-11'].to_csv(index=False).encode(),'m1');h=l.fresh_holdout(r['id'])
    assert h['kind']=='m1' and h['passed'] and h['candidate']['mae']==0
    assert h['candidate']['wape_pct'] is None and h['candidate']['bias_pct'] is None
    with pytest.raises(ValueError):l.fresh_holdout(r['id'])


def test_upgrade_schema_preserves_users_tokens_sessions_and_receipt(engine,flow,tmp_path):
    from services.identity import Identity
    s=close(flow);identity=Identity(flow.store);identity.create('upgradeuser','Upgrade-Password-123',bootstrap=True)
    token,user=identity.login('upgradeuser','Upgrade-Password-123');before=flow.store.get(s['id'])
    l=Learning(flow.store,engine,tmp_path/'models');evaluation=Evaluation(flow.store,l);r=evaluation.report(s['id'])
    receipt=evaluation.certify(s['id'],s['revision'],r['state_sha256'],'Migration test')
    l2=Learning(flow.store,engine,l.root);r2=Evaluation(flow.store,l2).report(s['id'])
    assert identity.authenticate(token)==user and flow.store.get(s['id'])==before
    assert r2['receipt_current'] and r2['receipt']['id']==receipt['id']
    damaged=copy.deepcopy(before);next(iter(damaged['products'].values()))['revenue']+=1
    with flow.store.connect() as db:db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(damaged),s['id']))
    assert not evaluation.report(s['id'])['receipt_current']
    with pytest.raises(ValueError):evaluation.certify(s['id'],s['revision'],r['state_sha256'],'Stale evidence')


def test_api_null_kpis_when_closed_accounting_is_corrupt(client):
    import app
    s=close(app.workflow);s['ledger'][0]['unit_price']+=1
    with app.store.connect() as db:db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(s),s['id']))
    r=client.get('/api/state',params={'session_id':s['id']}).json()
    assert r['reconciliation']['status']=='MISMATCH'
    assert r['totals']['revenue'] is None and r['totals']['contribution_before_overhead'] is None
    assert client.get('/api/evaluation/'+s['id']).json()['kpis'] is None
    m=client.get('/api/monitoring',params={'session_id':s['id']}).json()
    assert m['business']['groups']==[] and m['accuracy']==[] and m['business']['mismatches']



def test_rollback_recovers_when_active_artifact_folder_is_missing(engine,tmp_path):
    import shutil
    l=Learning(Store(tmp_path/'db.sqlite'),engine,tmp_path/'artifacts');l.ingest('x.csv',daily(engine).to_csv(index=False).encode(),'m2');r=l.train('m2')
    l.promote(r['id'],engine.version,'Approved in temporary test')
    shutil.rmtree(l.root/r['id'])
    restarted=Learning(l.store,engine,l.root)
    registry=restarted.registry();assert registry['active']==r['id']
    assert not next(v for v in registry['versions'] if v['version']==r['id'])['integrity']
    restarted.rollback(r['id'],'Recover from deleted active artifacts')
    assert restarted.active().version==engine.version

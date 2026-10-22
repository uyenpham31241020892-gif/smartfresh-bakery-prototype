import asyncio,copy,hashlib,json,sqlite3,zipfile
from pathlib import Path
import pytest
from test_api import client
from test_monitoring_gd7 import close
from services.readiness import Readiness,release_check,health
from services.learning import Learning
from services.identity import Identity
from services.evaluation import Evaluation
from scripts.backup_restore import backup,restore


def test_health_and_safe_503(client,monkeypatch):
    import app
    r=client.get('/api/health');assert r.status_code==200 and r.json()['database'] and r.json()['dependencies']
    monkeypatch.setattr(app.learning,'active',lambda:(_ for _ in ()).throw(ValueError('PRIVATE_KEY_AND_PATH')))
    r=client.get('/api/health');assert r.status_code==503 and not r.json()['ok'] and 'PRIVATE_KEY' not in r.text
    assert r.headers['x-request-id']


def test_structured_errors_validation_no_secret_and_500(client,monkeypatch):
    import app
    secret='PASSWORD_SHOULD_NOT_ECHO'
    r=client.post('/api/auth/login',json={'username':'x','password':{'secret':secret}})
    assert r.status_code==422 and secret not in r.text
    assert r.json()['code']=='VALIDATION_ERROR' and r.json()['request_id']==r.headers['x-request-id']
    assert r.headers['cache-control']=='no-store' and r.headers['x-content-type-options']=='nosniff'
    for path in ['/api/does-not-exist']:
        r=client.get(path);assert r.status_code==404 and r.json()['code']=='NOT_FOUND'
    monkeypatch.setattr(app.workflow,'create',lambda **k:(_ for _ in ()).throw(RuntimeError(secret)))
    r=client.post('/api/sessions',json={});assert r.status_code==500 and r.json()['code']=='INTERNAL_ERROR' and secret not in r.text


def test_security_cross_origin_host_body_limit_and_viewer(client):
    assert client.post('/api/sessions',json={},headers={'Origin':'https://attacker.example'}).status_code==403
    assert client.post('/api/sessions',json={},headers={'sec-fetch-site':'cross-site'}).status_code==403
    assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==403
    r=client.post('/api/sessions',content=b'{}',headers={'Content-Length':str(26*1024*1024),'Content-Type':'application/json'})
    assert r.status_code==413 and r.json()['code']=='PAYLOAD_TOO_LARGE' and r.json()['request_id']==r.headers['x-request-id']
    client.post('/api/auth/users',json={'username':'qaviewer','password':'ReadOnlyPassword123','role':'viewer'})
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'qaviewer','password':'ReadOnlyPassword123'})
    assert client.post('/api/sessions',json={}).status_code==403
    assert client.get('/api/registry').status_code==200


def test_chunked_request_limit_without_content_length():
    from services.http_limits import BodySizeLimit
    called=[];sent=[];messages=iter([{'type':'http.request','body':b'123','more_body':True},{'type':'http.request','body':b'456','more_body':False}])
    async def inner(*args):called.append(True)
    async def receive():return next(messages)
    async def send(message):sent.append(message)
    asyncio.run(BodySizeLimit(inner,max_bytes=5)({'type':'http','method':'POST','headers':[]},receive,send))
    assert not called and sent[0]['status']==413


def test_request_trace_links_audit_and_real_transactions(client):
    import app
    s=client.post('/api/sessions',json={}).json();sid=s['id']
    for action,payload in [('plan_approve',{}),('prepared',{}),('advance',{'target':1170})]:
        r=client.post('/api/sessions/'+sid+'/'+action,json={'revision':s['revision'],'payload':payload});assert r.status_code==200;s=r.json()
    trace=client.get('/api/trace/'+r.headers['x-request-id']).json()
    assert trace['events'] and trace['transactions'] and trace['requests']
    assert all(t['transaction']['request_id']==r.headers['x-request-id'] for t in trace['transactions'])
    assert trace['transactions'][0]['transaction']['model_version']==s['model_version']
    assert client.get('/api/trace/invalid').status_code==400


def release_fixture(root):
    (root/'code.txt').write_text('release source');m={'release_id':'testrelease','files':{'code.txt':hashlib.sha256(b'release source').hexdigest()}}
    (root/'release_manifest.json').write_text(json.dumps(m));(root/'docs').mkdir()
    (root/'docs/GD9_QA_RESULTS.json').write_text(json.dumps({'release_id':'testrelease','passed':1,'failed':0,'pytest_exit_code':0,'e2e':{'passed':True}}))


def test_go_requires_current_receipt_release_qa_and_no_incidents(flow,engine,tmp_path):
    s=close(flow);l=Learning(flow.store,engine,tmp_path/'learning');root=tmp_path/'release';root.mkdir();release_fixture(root)
    identity=Identity(flow.store);identity.create('readyuser','ReadyPassword123',bootstrap=True)
    ready=Readiness(flow.store,l,flow,root)
    assert ready.snapshot(s['id'])['decision']=='NO_GO'
    e=Evaluation(flow.store,l);r=e.report(s['id']);e.certify(s['id'],s['revision'],r['state_sha256'],'Verified temporary session')
    result=ready.snapshot(s['id']);assert result['decision']=='GO' and result['production_decision']=='NOT_ASSESSED'
    (root/'code.txt').write_text('changed');assert ready.snapshot(s['id'])['decision']=='NO_GO'
    (root/'code.txt').write_text('release source')
    (root/'docs/GD9_QA_RESULTS.json').write_text(json.dumps({'release_id':'stale','passed':10,'failed':0,'pytest_exit_code':0,'e2e':{'passed':True}}))
    assert ready.snapshot(s['id'])['decision']=='NO_GO'
    (root/'docs/GD9_QA_RESULTS.json').write_text(json.dumps({'release_id':'testrelease','passed':1,'failed':0,'pytest_exit_code':0,'e2e':{'passed':True}}))
    flow.safety.report(s['id'],'TEST_FAILURE','Synthetic test')
    assert ready.snapshot(s['id'])['decision']=='NO_GO'


def test_release_manifest_missing_corrupt_and_path_escape(tmp_path):
    assert release_check(tmp_path)['status']=='FAIL'
    (tmp_path/'release_manifest.json').write_text('{bad');assert release_check(tmp_path)['status']=='FAIL'
    (tmp_path/'release_manifest.json').write_text(json.dumps({'files':{'../outside':'abc'}}));assert release_check(tmp_path)['status']=='FAIL'


def test_backup_restore_keeps_history_accounts_and_disables_old_tokens(flow,engine,tmp_path):
    s=close(flow);l=Learning(flow.store,engine,tmp_path/'learning');i=Identity(flow.store);i.create('backupuser','BackupPassword123',bootstrap=True);token,user=i.login('backupuser','BackupPassword123')
    archive=tmp_path/'backup.zip'
    with pytest.raises(ValueError):backup(flow.store.path,l.root,archive)
    backup(flow.store.path.resolve(),l.root,archive,True)
    original=flow.store.get(s['id']);target=tmp_path/'restored';restore(archive,target,True)
    from services.store import Store
    restored=Store(target/'state.sqlite3');ri=Identity(restored)
    assert restored.get(s['id'])==original and ri.authenticate(token) is None
    assert ri.login('backupuser','BackupPassword123')[1]['username']=='backupuser'
    assert i.authenticate(token)==user and flow.store.get(s['id'])==original
    with pytest.raises(ValueError):restore(archive,target,True)


def test_restore_rejects_checksum_corruption_and_zip_slip_without_destination(flow,engine,tmp_path):
    l=Learning(flow.store,engine,tmp_path/'learning');Identity(flow.store);archive=tmp_path/'ok.zip';backup(flow.store.path.resolve(),l.root,archive,True)
    with zipfile.ZipFile(archive) as z:files={n:z.read(n) for n in z.namelist()}
    files['state.sqlite3']=b'corrupted';bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:
        for k,v in files.items():z.writestr(k,v)
    target=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='Checksum'):restore(bad,target,True)
    assert not target.exists()
    escape=tmp_path/'escape.zip';content=b'escape';manifest={'format':1,'files':{'state.sqlite3':hashlib.sha256(files['state.sqlite3']).hexdigest(),'learning/../../ESCAPE':hashlib.sha256(content).hexdigest()}}
    with zipfile.ZipFile(escape,'w') as z:
        z.writestr('backup_manifest.json',json.dumps(manifest));z.writestr('state.sqlite3',files['state.sqlite3']);z.writestr('learning/../../ESCAPE',content)
    with pytest.raises(ValueError):restore(escape,target,True)
    assert not target.exists() and not (tmp_path/'ESCAPE').exists()


def test_backup_restores_active_learned_artifacts_and_checks_native_hashes(engine,tmp_path):
    from test_learning import daily
    from services.store import Store
    l=Learning(Store(tmp_path/'original.sqlite3'),engine,tmp_path/'learning');Identity(l.store)
    l.ingest('test.csv',daily(engine).to_csv(index=False).encode(),'m2');r=l.train('m2');l.promote(r['id'],engine.version,'Temporary recovery test')
    archive=tmp_path/'learned.zip';backup(l.store.path.resolve(),l.root,archive,True)
    target=tmp_path/'restored';restore(archive,target,True)
    restored=Learning(Store(target/'state.sqlite3'),engine,target/'learning');assert restored.active().version==r['id'];restored.active().require_integrity()
    with zipfile.ZipFile(archive) as z:files={n:z.read(n) for n in z.namelist()}
    key='learning/'+r['id']+'/m2.txt';files[key]=b'tampered artifact'
    manifest=json.loads(files['backup_manifest.json']);manifest['files'][key]=hashlib.sha256(files[key]).hexdigest();files['backup_manifest.json']=json.dumps(manifest).encode()
    bad=tmp_path/'tampered.zip'
    with zipfile.ZipFile(bad,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    with pytest.raises(ValueError,match='Artifact'):restore(bad,tmp_path/'bad-restored',True)
    assert not (tmp_path/'bad-restored').exists()

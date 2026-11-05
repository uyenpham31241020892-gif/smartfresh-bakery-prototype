"""V4 compatibility regression for the preserved prototype, no training/tuning."""
import csv,io,json,os,sys,tempfile,zipfile,uuid
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA_ROOT=Path(tempfile.mkdtemp(prefix='smartfresh-v4-qa-'))
os.environ['SMARTFRESH_DB']=str(QA_ROOT/'qa.sqlite3')
os.environ['SMARTFRESH_LEARNING_DIR']=str(QA_ROOT/'lifecycle')
import app
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    c=TestClient(app.app)
    from services.identity import Identity
    salt='0'*32
    with app.store.connect() as db:
        db.execute("UPDATE local_users SET password_hash=?,salt=? WHERE username='manager.chau'",(Identity.password('qa-only-password',salt),salt))
    r=c.post('/api/auth/login',json={'username':'manager.chau','password':'qa-only-password'})
    assert r.status_code==200,r.text
    return c
def new(c,**kwargs):
    r=c.post('/api/sessions',json=dict(day='2022-05-02',auto_run=False,**kwargs));assert r.status_code==200,r.text;return r.json()
def act(c,s,action,payload=None,expect=200):
    r=c.post('/api/sessions/'+s['id']+'/'+action,json={'revision':s['revision'],'payload':payload or {},'key':uuid.uuid4().hex})
    assert r.status_code==expect,(action,r.text)
    return r.json()
def running(c):
    s=new(c);s=act(c,s,'plan_approve');return act(c,s,'prepared')
def resolve_pending(c,s):
    if s['phase']=='price_pending':s=act(c,s,'price_approve',{'proposal_id':s['pending']['id']})
    if s['phase']=='price_approved':s=act(c,s,'price_apply',{'proposal_id':s['pending']['id']})
    return s
def finish(c,s):
    while s['minute']<1320:
        s=resolve_pending(c,s);s=act(c,s,'advance',{'target':min(1320,s['minute']+30)})
    return act(c,s,'close')

def test_hashes_and_health(client):
    assert app.engine.require_integrity()
    assert client.get('/api/health').json()['ok']
    assert app.engine.version=='SMARTFRESH_V4_LOCKED'
    assert len(app.engine.master)==7

def test_july_operating_audit_is_available_in_business_reports(client):
    response=client.get('/api/test-month-report')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['status']=='complete'
    assert len(data['rows'])==31
    assert data['rows'][0]['day']=='2022-07-01'
    assert data['rows'][-1]['day']=='2022-07-31'
    assert data['weather_source']=='OPEN_METEO_JMA_GSM_PREVIOUS_DAY1'
def test_original_v4_m2_adapter_parity(client):
    e=app.engine
    for day in ['2022-05-02','2022-05-07','2022-06-15','2022-06-26']:
        rows=e.plan(day,app.simulator.history_before(day),app.simulator.calendar[day],app.simulator.outcomes_before(day))
        for p in rows:assert p['v4_plan']==e.adapter.prepare(p['features'],[])
def test_original_v4_m1_adapter_parity(client):
    e=app.engine;spec=e.master['TP-DN-001']
    for j in range(5):
        row=e.price('TP-DN-001',j,25,64,0,2,4,60,app.simulator.calendar['2022-05-02'])
        old=e.adapter._DAILY_CHANGE_TRACKER
        try:
            e.adapter._DAILY_CHANGE_TRACKER={}
            action=e.adapter.markdown({'model_features':row['model_features'],'price_context':{'current_discount_pct':0,'list_price_vnd':spec['unit_price_vnd_reference']}},'2022-05-02T'+['19:30','20:00','20:30','21:00','21:30'][j]+':00+07:00')
            assert row['v4_action']==action
        finally:e.adapter._DAILY_CHANGE_TRACKER=old
def test_refills_not_stocked_in_morning(client):
    s=running(client)
    for p in s['plan']:
        assert s['products'][p['sku']]['prepared']==p['v4_plan']['initial_qty']
    s=act(client,s,'advance',{'target':840})
    for p in s['plan']:assert s['products'][p['sku']]['prepared']==p['v4_plan']['initial_qty']+sum(b['qty'] for b in p['v4_plan']['production_batches'] if b['ready_time']<='14:00')
    s=act(client,s,'advance',{'target':1020})
    for p in s['plan']:assert s['products'][p['sku']]['prepared']==p['prepared']
def test_plan_override_and_reason(client):
    s=new(client);sku=s['plan'][0]['sku'];q=48
    act(client,s,'plan_approve',{'quantities':{sku:q}},expect=400)
    s=act(client,s,'plan_approve',{'quantities':{sku:q},'reason':'Ca trước tồn nhiều'})
    assert next(x for x in s['plan'] if x['sku']==sku)['approved']==q
def test_bad_batch_opens_incident(client):
    s=new(client);act(client,s,'plan_approve',{'quantities':{'TP-DN-001':50},'reason':'QA'},expect=400)
    assert client.get('/api/safety?session_id='+s['id']).json()['incidents']
def test_reject_and_revision(client):
    s=new(client);old=dict(s);s=act(client,s,'plan_reject',{'reason':'Kiểm tra lại sản lượng'})
    assert s['phase']=='plan_rejected'
    act(client,old,'plan_approve',expect=400)
def test_full_day_reconciliation_and_chain(client):
    s=finish(client,running(client));r=client.get('/api/evaluation/'+s['id']).json()
    assert r['publishable'] and not r['errors']
    f=r['financial_estimate'];assert f['contribution_before_overhead']==f['revenue']-f['preparation_cost']-f['disposal_fee']-f['markdown_cost']
    for p in s['products'].values():assert p['prepared']==p['sold']+p['stock']
    c=client.post('/api/evaluation/'+s['id']+'/certify',json=dict(revision=s['revision'],state_sha256=r['state_sha256'],reason='Đã đối soát'))
    assert c.status_code==200,c.text
    n=client.post('/api/day-chain/'+s['id'],json={});assert n.status_code==200,n.text
    assert n.json()['day']=='2022-05-03'
def test_m1_approval_does_not_apply_price(client):
    s=running(client);s=act(client,s,'advance',{'target':1170})
    r=client.post('/api/safety/control',json=dict(session_id=s['id'],revision=s['revision'],action='mode',value='manual',reason='Manager tự chọn'))
    assert r.status_code==200,r.text;s=r.json()['state'];assert s['pending']
    sku=s['pending']['rows'][0]['sku'];s=act(client,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:30},'reason':'Tồn cao cuối ngày'})
    assert s['products'][sku]['discount']==0
    s=act(client,s,'price_apply',{'proposal_id':s['pending']['id'],'channels':{sku:'sticker'}})
    assert s['products'][sku]['discount']==30 and s['products'][sku]['markdown_cost']==350 and s['products'][sku]['price_version']==1
def test_manual_50_cap_and_rejection(client):
    s=act(client,running(client),'advance',{'target':1170})
    r=client.post('/api/safety/control',json=dict(session_id=s['id'],revision=s['revision'],action='mode',value='manual',reason='Kiểm tra quyền Manager'));s=r.json()['state'];sku=s['pending']['rows'][0]['sku']
    act(client,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{sku:50},'reason':'QA chặn sớm'},expect=400)
def test_shadow_records_without_changing_pos(client):
    s=act(client,running(client),'advance',{'target':1170})
    r=client.post('/api/safety/control',json=dict(session_id=s['id'],revision=s['revision'],action='mode',value='shadow',reason='Thử quyết định Shadow'));assert r.status_code==200,r.text;s=r.json()['state']
    if not s.get('pending'):return
    before={k:p['discount'] for k,p in s['products'].items()};s=resolve_pending(client,s)
    assert before=={k:p['discount'] for k,p in s['products'].items()}
def test_api_surfaces_preserved(client):
    s=running(client);sid=s['id']
    for url in ['/api/metadata','/api/quality?session_id='+sid,'/api/monitoring?session_id='+sid,'/api/safety?session_id='+sid,'/api/business-report/'+sid,'/api/baseline-history/'+sid,'/api/registry','/api/learning','/api/readiness?session_id='+sid,'/api/proposal-explanation/'+sid+'?component=m2','/api/export/'+sid,'/api/audit/'+sid,'/api/simulator','/api/reference']:
        r=client.get(url);assert r.status_code==200,(url,r.text)
def test_drift_reference_and_sandbox(client):
    s=new(client);r=client.post('/api/monitoring/sandbox',json={'session_id':s['id']});assert r.status_code==200,r.text
    data=client.get('/api/monitoring',params=dict(session_id=s['id'],source='sandbox',sandbox_id=r.json()['id'])).json()
    assert data['drift']['reference']['available'] and data['drift']['reference']['rows']==777
    assert len(data['drift']['data'])==7
    assert all(x['current_n']>0 for x in data['drift']['data'])
def test_lifecycle_snapshot_restore(client):
    before=dict(app.engine.manifest['native_model_hashes'])
    r=client.post('/api/registry/checkpoint',json={'reason':'Snapshot QA V4'});assert r.status_code==200,r.text
    ident=r.json()['checkpoints'][0]['id']
    r=client.post('/api/registry/restore',json={'reason':'Khôi phục QA V4','checkpoint_id':ident});assert r.status_code==200,r.text
    assert before==app.engine.manifest['native_model_hashes'] and app.engine.require_integrity()
def test_train_remains_locked(client):
    assert client.post('/api/learning/train',json={'kind':'m2'}).status_code==409
def test_missing_and_future_features_block(client):
    e=app.engine;f=dict(e.morning[('2022-05-02','TP-DN-001')]);f['prior_day_rain_mm']=None
    with pytest.raises(ValueError):e.validate_features(f,'2022-05-02','TP-DN-001')
    f=dict(e.morning[('2022-05-02','TP-DN-001')]);f['history_through']='2022-05-02'
    with pytest.raises(ValueError):e.validate_features(f,'2022-05-02','TP-DN-001')
def test_upload_v4_features_and_quarantine(client):
    raw=(ROOT/'data/v4/import_example.csv').read_bytes()
    r=client.post('/api/imports',data={'day':'2022-05-02'},files={'file':('morning_features_V4.csv',raw,'text/csv')});assert r.status_code==200,r.text
    assert r.json()['valid'],r.text
    n=client.post('/api/imports/'+r.json()['import_id']+'/confirm',json={});assert n.status_code==200,n.text
    bad=client.post('/api/imports',data={'day':'2022-05-02'},files={'file':('bad.csv',b'date,sku_code,sold_qty\n2022-05-02,BK-001,-1\n','text/csv')})
    assert bad.status_code==200 and not bad.json()['valid']
def test_csv_excel_zip_parsers(client):
    from services.ingestion import tables
    import pandas as pd
    content=b'sku_code,minute,quantity\nTP-DN-001,480,2\n';assert len(tables('sales.csv',content))==1
    out=io.BytesIO();pd.DataFrame([{'sku_code':'TP-DN-001','minute':480,'quantity':2}]).to_excel(out,index=False)
    assert len(tables('sales.xlsx',out.getvalue()))==1
    z=io.BytesIO()
    with zipfile.ZipFile(z,'w') as archive:archive.writestr('history.csv','date,sku_code,sold_qty\n2022-05-01,TP-DN-001,3\n')
    assert len(tables('input.zip',z.getvalue()))==1
def test_staff_and_viewer_permissions(client):
    for role in ['staff','viewer']:
        name=role+uuid.uuid4().hex[:6];r=client.post('/api/auth/users',json=dict(username=name,password='demo12345',role=role));assert r.status_code==200
        c=TestClient(app.app);assert c.post('/api/auth/login',json=dict(username=name,password='demo12345')).status_code==200
        s=new(client)
        assert c.get('/api/registry').status_code==200
        assert c.post('/api/registry/checkpoint',json={'reason':'Không có quyền'}).status_code==403
        assert c.post('/api/sessions/'+s['id']+'/plan_approve',json={'revision':s['revision'],'payload':{}}).status_code==403
def test_localhost_csrf_and_auth(client):
    c=TestClient(app.app);assert c.get('/api/metadata').status_code==401
    assert client.get('/api/health',headers={'host':'evil.example'}).status_code==403
    assert client.post('/api/sessions',json={},headers={'origin':'https://evil.example'}).status_code==403
def test_copilot_reads_v4_tools_without_mutation(client,monkeypatch):
    from services.assistant import Assistant,SYSTEM,PROMPT_VERSION
    a=Assistant();calls=[]
    def fake(payload):
        calls.append(payload)
        if len(calls)==1:return {'id':'qa-tool-call','output':[{'type':'function_call','name':'get_session_context','arguments':'{}','call_id':'ctx'},{'type':'function_call','name':'get_model_evidence','arguments':'{"sku":"TP-DN-001"}','call_id':'m2'}]}
        return {'id':'qa-answer','output':[{'type':'message','content':[{'type':'output_text','text':'Đã đọc dữ liệu ca V4; cần Manager duyệt.'}]}]}
    monkeypatch.setattr(a,'request',fake)
    s=new(client);raw=app.store.get(s['id']);before=raw['revision']
    result=a.chat('Giải thích TP-DN-001',raw,lambda sku:app.evidence(raw,sku))
    assert set(result['tools_used'])=={'get_session_context','get_model_evidence'}
    assert app.store.get(s['id'])['revision']==before
    assert 'V4' in SYSTEM and PROMPT_VERSION.startswith('SMARTFRESH_V4')

def manual(c):
    s=act(c,running(c),'advance',{'target':1170})
    r=c.post('/api/safety/control',json=dict(session_id=s['id'],revision=s['revision'],action='mode',value='manual',reason='Manager tự quyết'))
    assert r.status_code==200,r.text;return r.json()['state']
def set_price(c,s,sku,tier):
    s=act(c,s,'price_approve',dict(proposal_id=s['pending']['id'],discounts={sku:tier},reason='Manager rà soát tồn và sức bán'))
    return act(c,s,'price_apply',dict(proposal_id=s['pending']['id']))
def test_cooldown_blocks_second_change_same_clock(client):
    s=manual(client);sku=s['pending']['rows'][0]['sku'];s=set_price(client,s,sku,20)
    s=act(client,s,'refresh_price');s=act(client,s,'price_approve',dict(proposal_id=s['pending']['id'],discounts={sku:30},reason='Thử cooldown'))
    act(client,s,'price_apply',dict(proposal_id=s['pending']['id']),expect=400)
    assert app.store.get(s['id'])['products'][sku]['discount']==20

def test_manual_50_available_at_2030_and_cooldown_still_applies(client):
    s=manual(client);sku=s['pending']['rows'][0]['sku'];s=act(client,s,'price_reject',{'proposal_id':s['pending']['id'],'reason':'Giữ để kiểm tra 20:30'})
    s=act(client,s,'advance',{'target':1200});s=act(client,s,'price_reject',{'proposal_id':s['pending']['id'],'reason':'Giữ để kiểm tra 20:30'})
    s=act(client,s,'advance',{'target':1230});s=set_price(client,s,sku,50)
    assert s['products'][sku]['discount']==50
    # A third change ten minutes later is blocked by the 30-minute cooldown.
    other=next(r['sku'] for r in s['plan'] if r['sku']!=sku and s['products'][r['sku']]['stock']>0)
    s=act(client,s,'advance',{'target':1260});s=set_price(client,s,other,20)
    s=act(client,s,'advance',{'target':1290});s=set_price(client,s,other,30)
    s=act(client,s,'advance',{'target':1300});s=act(client,s,'refresh_price');s=act(client,s,'price_approve',dict(proposal_id=s['pending']['id'],discounts={other:40},reason='Kiểm tra giới hạn hai lần'))
    act(client,s,'price_apply',dict(proposal_id=s['pending']['id']),expect=400)
    assert app.store.get(s['id'])['products'][other]['price_changes']==2

def test_hash_failure_is_not_bypassed(client):
    path=ROOT/'v4/artifacts_build/models/policy_config.json';saved=path.read_bytes()
    try:
        path.write_bytes(saved+b' ')
        assert client.get('/api/health').status_code==503
        with pytest.raises(ValueError):app.engine.plan('2022-05-02',app.simulator.history_before('2022-05-02'),app.simulator.calendar['2022-05-02'])
    finally:path.write_bytes(saved)
    assert client.get('/api/health').status_code==200

def test_offline_database_and_lifecycle_backup(client,tmp_path):
    from scripts.backup_restore import backup,restore
    s=running(client)
    assert client.post('/api/registry/checkpoint',json={'reason':'Snapshot trước backup'}).status_code==200
    archive=tmp_path/'backup.zip';dest=tmp_path/'restored'
    backup(app.store.path,app.learning.root,archive,server_stopped=True)
    result=restore(archive,dest,server_stopped=True)
    assert result['requires_login'] and (dest/'state.sqlite3').is_file()
    import sqlite3
    with sqlite3.connect(dest/'state.sqlite3') as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM login_sessions').fetchone()[0]==0

def test_v4_simulation_retains_price_response_and_no_future_output(client):
    sim=app.simulator;discounts={sku:0 for sku in app.engine.master}
    request=dict(operation='consume',day='2022-05-02',start=1170,end=1320,discounts=discounts)
    hold=sim._custodian(request)['requests']
    reduced=sim._custodian(dict(request,discounts={k:50 for k in discounts}))['requests']
    assert len(reduced)>len(hold)
    early=sim._custodian(dict(request,end=1200))['requests']
    assert all(1170<=r['minute']<1200 and set(r)=={'sku','minute','quantity','origin','second','event_id','customer_id','transaction_at'} and r['transaction_at']<'2022-05-02T20:00:00+07:00' for r in early)
    with pytest.raises(ValueError):sim.events('2022-05-02',version=sim.version)
    s=new(client)
    assert all(not {'unit_events','base_intent_qty','discount_sensitive_pool_qty','response_draw'} & set(p['features']) for p in s['plan'])

def test_new_sessions_have_one_primary_source(client):
    r=client.post('/api/sessions',json=dict(day='2022-05-02',auto_run=False,market_version=app.simulator.replay_version))
    assert r.status_code==400,r.text

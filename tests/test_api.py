import io
from datetime import date, timedelta
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from services.store import Store
from services.workflow import Workflow


@pytest.fixture
def client(monkeypatch,tmp_path,engine,simulator):
    import app as module
    store=Store(tmp_path/'api.sqlite3')
    monkeypatch.setattr(module,'store',store)
    from services.identity import Identity
    monkeypatch.setattr(module,'identity',Identity(store))
    monkeypatch.setattr(module,'workflow',Workflow(engine,simulator,store))
    from services.learning import Learning
    learner = Learning(store, engine, tmp_path/'artifacts')
    monkeypatch.setattr(module, 'learning', learner)
    module.workflow.active_engine, module.workflow.version_engine = learner.active, learner.resolve
    module.workflow.observed_history = learner.history_before
    module.workflow.observed_outcomes = learner.outcomes_before
    from services.realtime import Realtime
    monkeypatch.setattr(module,'realtime',Realtime(module.workflow,store))
    c=TestClient(module.app)
    assert c.post('/api/auth/setup',json={'username':'testmanager','password':'TestPass-GD6-123'}).status_code==200
    return c


def test_health_and_invalid_archive(client):
    assert client.get('/api/health').json()['ok']
    r=client.post('/api/imports',data={'day':'2022-08-16'},files={'file':('broken.zip',b'not-a-zip','application/zip')})
    assert r.status_code==400
    assert 'bị hỏng' in r.json()['error']


def test_new_date_xlsx_import_runs_real_inference_once(client,engine):
    day='2026-10-21'
    rows=[{'date':(date(2026,10,21)-timedelta(days=k)).isoformat(),'sku_code':sku,'sold_qty':30}
          for sku in engine.master for k in range(1,15)]
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as w:
        pd.DataFrame(rows).to_excel(w,index=False,sheet_name='history')
        pd.DataFrame([{'date':day,'forecast_rain_mm_previous_day1':8,'forecast_temperature_max_c_previous_day1':31,
                       'issued_at':'2026-10-20T18:00:00+07:00'}]).to_excel(w,index=False,sheet_name='weather')
    r=client.post('/api/imports',data={'day':day},files={'file':('new-day.xlsx',output.getvalue())})
    assert r.status_code==200,r.text
    p=r.json()
    assert p['valid'] and p['history_rows']==112
    assert p['warnings']
    url='/api/imports/'+p['import_id']+'/confirm'
    r=client.post(url,json={})
    assert r.status_code==200,r.text
    state=r.json()
    assert state['phase']=='plan_pending' and state['mode']=='live'
    assert all(p['features']['lag1_sales']==30 for p in state['plan'])
    assert all(p['features']['history_days']==14 for p in state['plan'])
    assert len(state['input_hash'])==64
    assert 'input_history' not in state
    again=client.post(url,json={}).json()
    assert state['id']==again['id'] and len(client.get('/api/sessions').json())==1


def test_local_origin_and_missing_ai_key(client,monkeypatch):
    import app as module
    monkeypatch.setattr(module.assistant,'key','')
    assert client.post('/api/sessions',json={},headers={'origin':'https://unrelated.example'}).status_code==403
    s=client.get('/api/state').json()
    r=client.post('/api/chat',json={'session_id':s['id'],'message':'Giải thích BK-001'})
    assert r.status_code==400 and 'API key' in r.json()['error']
    assert s['phase']=='plan_pending'


def test_ai_connection_is_verified_before_replacing_key(client,monkeypatch):
    import app as module
    from services.assistant import Assistant
    current=Assistant()
    current.configure('test-old-key-no-network-000','gpt-4.1-mini')
    monkeypatch.setattr(module,'assistant',current)
    s=client.get('/api/state').json()
    def rejected(self,*args):
        raise ValueError('OpenAI trả HTTP 401.')
    monkeypatch.setattr(Assistant,'chat',rejected)
    r=client.post('/api/ai/connect',json={'session_id':s['id'],'api_key':'test-new-key-no-network-000','model':'gpt-4.1-mini'})
    assert r.status_code==400
    assert current.key=='test-old-key-no-network-000'
    assert not current.status()['verified']


def test_ai_connect_returns_response_evidence_and_never_exposes_key(client,monkeypatch):
    import app as module
    from services.assistant import Assistant
    monkeypatch.setattr(module,'assistant',Assistant())
    s=client.get('/api/state').json()
    def answered(self,question,state,evidence):
        assert evidence('BK-001')['m2']['sku']=='BK-001'
        return {'answer':'Test response only.','model':self.model,'response_id':'test-response-id',
                'tools_used':['get_session_context','get_model_evidence'],'revision':state['revision'],'session_id':state['id']}
    monkeypatch.setattr(Assistant,'chat',answered)
    key='test-key-no-network-000000'
    r=client.post('/api/ai/connect',json={'session_id':s['id'],'api_key':key,'model':'gpt-4.1-mini'})
    assert r.status_code==200,r.text
    assert r.json()['ai']['verified']
    assert r.json()['verification']['response_id']=='test-response-id'
    assert key not in r.text
    audit=client.get('/api/audit/'+s['id']).json()
    assert audit[0]['action']=='OPENAI_CONNECTION_TEST'
    assert key not in str(audit)


def test_gemini_catalogue_does_not_replace_connection_or_return_key(client, monkeypatch):
    import app as module
    import services.providers as native
    before = module.assistant.status()
    key = 'test-only-gemini-key-not-real'
    def catalogue(candidate):
        assert candidate.provider == 'Gemini' and candidate.key == key
        return {'key_accepted': True, 'models': [{'id': 'gemini-test', 'name': 'Test model'}]}
    monkeypatch.setattr(native, 'list_gemini_models', catalogue)
    response = client.post('/api/ai/models', json={'provider': 'Gemini', 'api_key': key, 'model': 'gemini-test'})
    assert response.status_code == 200 and key not in response.text
    assert module.assistant.status() == before

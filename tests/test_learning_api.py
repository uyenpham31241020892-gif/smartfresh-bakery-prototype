import io
import pandas as pd
from services.learning import demo_data
from test_api import client


def test_demo_upload_evaluate_and_block_promotion(client):
    initial = client.get('/api/learning').json()
    response = client.post('/api/learning/demo', json={'kind': 'm2', 'origin': 'real'})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['origin'] == 'demo' and report['status'] == 'demo_only'
    bad = client.post('/api/learning/'+report['id']+'/promote', json={'expected_active': initial['active'], 'reason': 'Must reject demo'})
    assert bad.status_code == 400 and client.get('/api/learning').json()['active'] == initial['active']
    assert client.get('/api/learning/template/m2').status_code == 200


def test_learning_xlsx_upload_and_real_confirmation(client, engine):
    raw = demo_data('m2', engine.master)  # synthetic test fixture only; isolated DB/artifacts
    out = io.BytesIO()
    pd.read_csv(io.BytesIO(raw)).to_excel(out, index=False)
    uploaded = client.post('/api/learning/upload', data={'kind': 'm2', 'origin': 'real'}, files={'file': ('outcomes.xlsx',out.getvalue())})
    assert uploaded.status_code == 200 and uploaded.json()['added'] == 504
    before = client.get('/api/state').json()
    trained = client.post('/api/learning/train', json={'kind': 'm2'})
    assert trained.status_code == 200, trained.text
    report = trained.json()
    assert report['status'] == 'awaiting_confirmation'
    assert client.get('/api/learning').json()['active'] == before['model_version']
    adopted = client.post('/api/learning/'+report['id']+'/promote', json={'expected_active': before['model_version'], 'reason': 'Test-only confirmation'})
    assert adopted.status_code == 200 and adopted.json()['active'] == report['id']
    assert client.get('/api/state?session_id='+before['id']).json()['model_version'] == before['model_version']
    rollback = client.post('/api/learning/rollback', json={'expected_active': report['id'], 'reason': 'Test-only rollback'})
    assert rollback.status_code == 200 and rollback.json()['active'] == before['model_version']

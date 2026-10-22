"""Authenticated E2E and fault rehearsal in a temporary database, never user runtime."""
import json,os,secrets,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    with tempfile.TemporaryDirectory(prefix='smartfresh-gd9-e2e-') as tmp:
        os.environ['SMARTFRESH_DB']=str(Path(tmp)/'state.sqlite3');os.environ['SMARTFRESH_LEARNING_DIR']=str(Path(tmp)/'learning');os.environ['AI_PROVIDER']='OpenAI'
        import app
        from fastapi.testclient import TestClient
        from scripts.backup_restore import backup,restore
        from services.store import Store
        from services.learning import Learning
        c=TestClient(app.app);password=secrets.token_urlsafe(20)
        assert c.get('/api/state').status_code==401
        assert c.post('/api/auth/setup',json={'username':'qaoperator','password':password}).status_code==200
        assert c.get('/api/health').status_code==200
        s=c.post('/api/sessions',json={}).json();sid=s['id'];traces=[]
        def step(action,payload=None,revision=None):
            nonlocal s
            r=c.post('/api/sessions/'+sid+'/'+action,json={'revision':s['revision'] if revision is None else revision,'payload':payload or {}})
            assert r.status_code==200,r.text
            traces.append(r.headers['x-request-id']);s=r.json()
        assert c.get('/api/readiness',params={'session_id':sid}).json()['decision']=='NO_GO'
        rev=s['revision'];step('plan_approve');bad=c.post('/api/sessions/'+sid+'/prepared',json={'revision':rev});assert bad.status_code==400 and bad.json()['request_id']==bad.headers['x-request-id']
        step('prepared')
        for minute in [1170,1200,1230,1260,1290]:
            step('advance',{'target':minute});pid=s['pending']['id'];step('price_approve',{'proposal_id':pid});step('price_apply',{'proposal_id':pid})
        step('advance',{'target':1320});step('close')
        r=c.get('/api/evaluation/'+sid).json();assert r['publishable']
        assert c.post('/api/evaluation/'+sid+'/certify',json={'revision':s['revision'],'state_sha256':r['state_sha256'],'reason':'E2E temporary verification'}).status_code==200
        traced=c.get('/api/trace/'+traces[0]).json();assert traced['events'] and traced['requests']
        # Unauthorized role cannot approve or mutate model, even via raw HTTP.
        c.post('/api/auth/users',json={'username':'qaviewer','password':password,'role':'viewer'})
        viewer=TestClient(app.app);viewer.post('/api/auth/login',json={'username':'qaviewer','password':password})
        assert viewer.post('/api/learning/rollback',json={'expected_active':app.engine.version,'reason':'Unauthorized test'}).status_code==403
        assert viewer.get('/api/readiness',params={'session_id':sid}).status_code==200
        original=app.store.get(sid)
        archive=Path(tmp)/'backup.zip';backup(app.store.path.resolve(),app.learning.root,archive,True)
        restored=Path(tmp)/'restored';restore(archive,restored,True)
        recovered_store=Store(restored/'state.sqlite3');assert recovered_store.get(sid)==original
        recovered=Learning(recovered_store,app.engine,restored/'learning');assert recovered.active().version==app.learning.active().version
        with recovered_store.connect() as db:assert db.execute('SELECT count(*) FROM login_sessions').fetchone()[0]==0
        # A degraded model must yield 503 without secret exception text.
        saved=app.learning.active
        app.learning.active=lambda:(_ for _ in ()).throw(ValueError('private-path-and-key'))
        try:
            h=c.get('/api/health');assert h.status_code==503 and 'private-path' not in h.text
        finally:app.learning.active=saved
        print(json.dumps({'passed':True,'temporary_workspace':True,'closed_session_reconciled':True,'manager_certification':True,'stale_revision_blocked':True,'viewer_denied':True,'request_trace':True,'backup_restore_verified':True,'restored_tokens_invalidated':True,'model_failure_health_503':True,'steps':len(traces)},indent=2))
if __name__=='__main__':main()

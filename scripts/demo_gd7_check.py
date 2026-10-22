"""Rehearse GD7 through authenticated APIs in a temporary workspace only."""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix='smartfresh-gd7-') as tmp:
        os.environ['SMARTFRESH_DB']=str(Path(tmp)/'demo.sqlite3')
        os.environ['SMARTFRESH_LEARNING_DIR']=str(Path(tmp)/'learning')
        import app
        from fastapi.testclient import TestClient
        c=TestClient(app.app);password=secrets.token_urlsafe(18)
        assert c.post('/api/auth/setup',json={'username':'monitoroperator','password':password}).status_code==200
        s=c.post('/api/sessions',json={}).json();original=app.store.get(s['id'])
        d=c.get('/api/monitoring',params={'session_id':s['id']});assert d.status_code==200,d.text
        assert d.json()['accuracy']==[]
        def step(action,payload=None):
            nonlocal s
            r=c.post('/api/sessions/'+s['id']+'/'+action,json={'revision':s['revision'],'payload':payload or {}})
            assert r.status_code==200,r.text
            s=r.json()
        step('plan_approve');step('prepared')
        for minute in [1170,1200,1230,1260,1290]:
            step('advance',{'target':minute});pid=s['pending']['id'];step('price_approve',{'proposal_id':pid});step('price_apply',{'proposal_id':pid})
        step('advance',{'target':1320});step('close')
        d=c.get('/api/monitoring',params={'session_id':s['id']}).json()
        assert d['accuracy'][0]['metrics']['n']==8
        before=app.store.get(s['id'])
        sandbox=c.post('/api/monitoring/sandbox',json={'session_id':s['id']});assert sandbox.status_code==200,sandbox.text
        params={'session_id':s['id'],'source':'sandbox','sandbox_id':sandbox.json()['id']}
        demo=c.get('/api/monitoring',params=params);assert demo.status_code==200,demo.text
        demo=demo.json();codes={a['code'] for a in demo['alerts'] if a['active']}
        assert 'DATA_DRIFT' in codes and 'PERFORMANCE_DRIFT' in codes
        a=next(a for a in demo['alerts'] if a['active'])
        assert c.post('/api/monitoring/alerts/'+a['id']+'/acknowledge',json={'evidence_hash':a['evidence_hash'],'note':'Isolated rehearsal review'}).status_code==200
        assert app.store.get(s['id'])==before
        assert c.post('/api/auth/users',json={'username':'monitorviewer','password':password,'role':'viewer'}).status_code==200
        viewer=TestClient(app.app);viewer.post('/api/auth/login',json={'username':'monitorviewer','password':password})
        assert viewer.get('/api/monitoring',params={'session_id':s['id']}).status_code==200
        assert viewer.post('/api/monitoring/sandbox',json={'session_id':s['id']}).status_code==403
        print(json.dumps({'passed':True,'temporary_database':True,'open_day_accuracy':'N/A',
                          'closed_runtime_metric':d['accuracy'][0]['metrics'],
                          'sandbox_rows':demo['accuracy'][0]['metrics']['n'],'sandbox_alerts':sorted(codes),
                          'drift_changes_no_workflow_state':True,'viewer_cannot_write':True,
                          'real_http_requests':d['operations']['http']['requests']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

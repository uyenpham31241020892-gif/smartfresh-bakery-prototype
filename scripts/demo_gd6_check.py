"""End-to-end safety rehearsal against a temporary database, never the user's workspace."""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix='smartfresh-gd6-') as tmp:
        os.environ['SMARTFRESH_DB']=str(Path(tmp)/'demo.sqlite3')
        os.environ['SMARTFRESH_LEARNING_DIR']=str(Path(tmp)/'learning')
        import app
        from fastapi.testclient import TestClient
        c=TestClient(app.app)
        password=secrets.token_urlsafe(18)
        assert c.post('/api/auth/setup',json={'username':'drillmanager','password':password}).status_code==200
        s=c.post('/api/sessions',json={}).json()
        checks=[]
        def control(action,value):
            nonlocal s
            r=c.post('/api/safety/control',json={'session_id':s['id'],'revision':s['revision'],'action':action,'value':value,'reason':'Isolated automated GD6 rehearsal'})
            assert r.status_code==200,r.text
            s=r.json()['state'];return r.json()
        def step(action,payload=None):
            nonlocal s
            r=c.post('/api/sessions/'+s['id']+'/'+action,json={'revision':s['revision'],'payload':payload or {}})
            assert r.status_code==200,r.text
            s=r.json()
        def recover():
            report=c.get('/api/safety',params={'session_id':s['id']}).json()
            incidents=[i for i in report['incidents'] if i['status']!='resolved']
            for i in incidents:
                assert c.post('/api/safety/incidents/'+i['id'],json={'action':'acknowledge','reason':'Assigned drill owner'}).status_code==200
            control('drill','clear')
            for i in incidents:
                for a in ['verify','resolve']:
                    r=c.post('/api/safety/incidents/'+i['id'],json={'action':a,'reason':'Repaired and verified in isolated rehearsal'})
                    assert r.status_code==200,r.text
            control('mode','assisted')
        control('drill','m2_error');assert s['prediction_origin']=='RULE_ROLLING7'
        checks.append('M2 error => rule fallback, pending Manager approval')
        recover();assert s['prediction_origin']=='AI_M2'
        checks.append('acknowledge => clear => verify => resolve => explicit resume')
        assert c.post('/api/auth/users',json={'username':'drillstaff','password':password,'role':'staff'}).status_code==200
        staff=TestClient(app.app)
        assert staff.post('/api/auth/login',json={'username':'drillstaff','password':password}).status_code==200
        assert staff.post('/api/sessions/'+s['id']+'/plan_approve',json={'revision':s['revision']}).status_code==403
        checks.append('Staff cannot approve even via direct API')
        step('plan_approve');step('prepared');step('advance',{'target':1170})
        control('drill','m1_error');assert s['pending']['origin']=='MANUAL_RULE'
        assert all(p['discount']==0 for p in s['products'].values())
        checks.append('M1 error => manual suggestion, effective prices unchanged')
        recover();step('refresh_price')
        control('drill','stale_stock');assert s['pending']['rows']==[]
        checks.append('untrusted stock blocks all M1 suggestions')
        recover()
        receipt=control('rollback_drill','')['drill']
        assert receipt['passed'] and not receipt['changed_active_model']
        checks.append('isolated rollback smoke drill leaves active model unchanged')
        assert c.get('/api/safety',params={'session_id':s['id']}).json()['control']['mode']=='assisted'
        result={'passed':True,'temporary_database':True,'checks':checks}
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

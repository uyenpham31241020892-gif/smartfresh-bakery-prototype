import pytest
from test_api import client
from services.engine import SLOTS

def advance_to(c,minute):
    s=c.post('/api/sessions',json={}).json();sid=s['id']
    def step(action,payload=None):
        nonlocal s
        r=c.post('/api/sessions/'+sid+'/'+action,json={'revision':s['revision'],'payload':payload or {}});assert r.status_code==200,r.text;s=r.json()
    step('plan_approve');step('prepared')
    for slot in SLOTS:
        step('advance',{'target':slot})
        if slot==minute:break
        pid=s['pending']['id'];step('price_approve',{'proposal_id':pid});step('price_apply',{'proposal_id':pid})
    return s

def test_manager_switch_manual_refreshes_edits_only_selected_sku_and_applies(client):
    import app
    s=advance_to(client,1290);sid=s['id'];old=s['pending']['id']
    r=client.post('/api/safety/control',json={'session_id':sid,'revision':s['revision'],'action':'mode','value':'manual','reason':'Tồn cao; quản lý tự chọn mức giảm'})
    assert r.status_code==200,r.text;s=r.json()['state']
    assert s['phase']=='price_pending' and s['pending']['id']!=old and s['pending']['origin']=='MANUAL_RULE'
    assert all(isinstance(x['sales30'],int) and isinstance(x['sales60'],int) for x in s['pending']['rows'])
    sku=s['pending']['rows'][0]['sku'];before={k:p['discount'] for k,p in s['products'].items()}
    body={'revision':s['revision'],'payload':{'proposal_id':s['pending']['id'],'discounts':{sku:50},'reason':'Bán chậm, còn nhiều tồn lúc 21:30'}}
    r=client.post('/api/sessions/'+sid+'/price_approve',json=body);assert r.status_code==200,r.text;s=r.json()
    assert s['products'][sku]['discount']==before[sku]
    r=client.post('/api/sessions/'+sid+'/price_apply',json={'revision':s['revision'],'payload':{'proposal_id':s['pending']['id']}});assert r.status_code==200,r.text;s=r.json()
    assert s['products'][sku]['discount']==50
    assert all(p['discount']==max(before[k],30) for k,p in s['products'].items() if k!=sku)
    # Current-slot editing after application, not after closing.
    r=client.post('/api/sessions/'+sid+'/refresh_price',json={'revision':s['revision'],'payload':{}});assert r.status_code==200
    rows=r.json()['pending']['rows'];assert next(x for x in rows if x['sku']==sku)['previous']==50

def test_manager_cannot_override_cap_and_old_proposal_is_invalid(client):
    s=advance_to(client,1260);sid=s['id'];old=s['pending']['id']
    r=client.post('/api/safety/control',json={'session_id':sid,'revision':s['revision'],'action':'mode','value':'manual','reason':'Manual review'});s=r.json()['state']
    assert client.post('/api/sessions/'+sid+'/price_approve',json={'revision':s['revision'],'payload':{'proposal_id':old}}).status_code==400
    sku=s['pending']['rows'][0]['sku']
    assert client.post('/api/sessions/'+sid+'/price_approve',json={'revision':s['revision'],'payload':{'proposal_id':s['pending']['id'],'discounts':{sku:50},'reason':'Too early'}}).status_code==400

def test_shadow_and_role_guards_remain(client):
    s=advance_to(client,1170);sid=s['id'];prices={k:p['discount'] for k,p in s['products'].items()}
    r=client.post('/api/safety/control',json={'session_id':sid,'revision':s['revision'],'action':'mode','value':'shadow','reason':'Shadow test'});s=r.json()['state'];pid=s['pending']['id']
    s=client.post('/api/sessions/'+sid+'/price_approve',json={'revision':s['revision'],'payload':{'proposal_id':pid}}).json()
    s=client.post('/api/sessions/'+sid+'/price_apply',json={'revision':s['revision'],'payload':{'proposal_id':pid}}).json()
    assert {k:p['discount'] for k,p in s['products'].items()}==prices
    client.post('/api/auth/users',json={'username':'pricingstaff','password':'TestPricingPassword','role':'staff'});client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'pricingstaff','password':'TestPricingPassword'})
    assert client.post('/api/safety/control',json={'session_id':sid,'revision':s['revision'],'action':'mode','value':'manual','reason':'Unauthorized'}).status_code==403

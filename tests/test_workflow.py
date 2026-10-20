import copy
import pytest
from services.engine import SLOTS


def update(flow,s,action,payload=None,key=None):
    return flow.mutate(s['id'],s['revision'],action,payload,key)


def started(flow,mode='simulation'):
    s=flow.create(mode=mode)
    s=update(flow,s,'plan_approve')
    assert s['phase']=='plan_approved' and not s['products']
    return update(flow,s,'prepared')


def test_full_day_stops_at_every_approval_and_balances(flow):
    s=started(flow)
    for t in SLOTS:
        s=update(flow,s,'advance',{'target':1320})
        assert s['minute']==t and s['phase']=='price_pending'
        before={k:p['discount'] for k,p in s['products'].items()}
        with pytest.raises(ValueError,match='xác nhận'):
            update(flow,s,'advance',{'target':1320})
        pid=s['pending']['id']
        s=update(flow,s,'price_approve',{'proposal_id':pid})
        assert {k:p['discount'] for k,p in s['products'].items()} == before
        s=update(flow,s,'price_apply',{'proposal_id':pid},key=pid)
        # Idempotent duplicate apply cannot apply or log again.
        again=flow.mutate(s['id'],s['revision']-1,'price_apply',{'proposal_id':pid},pid)
        assert s == again
        for p in s['products'].values():
            assert p['stock']+p['sold']==p['prepared']
    s=update(flow,s,'advance',{'target':1320})
    assert s['phase']=='close_pending'
    s=update(flow,s,'close')
    assert s['phase']=='closed'
    for sku,p in s['products'].items():
        tx=[t for t in s['ledger'] if t['sku']==sku]
        assert p['revenue']==sum(t['paid'] for t in tx)
        assert p['sold']==sum(t['qty'] for t in tx)
        for t in tx:
            assert t['unit_price']==round(p['price']*(1-t['discount']/100))
    with pytest.raises(ValueError,match='đã chốt'):
        update(flow,s,'advance',{'target':1320})
    assert flow.store.get(s['id']) == s
    assert len(flow.store.audit(s['id'])) == 20


def test_stale_revisions_and_invalid_adjustments_are_atomic(flow):
    s=flow.create()
    with pytest.raises(ValueError,match='bội số 4'):
        update(flow,s,'plan_approve',{'quantities':{'BK-001':1},'reason':'test'})
    assert flow.store.get(s['id'])==s
    s2=update(flow,s,'plan_approve')
    with pytest.raises(ValueError,match='thay đổi'):
        flow.mutate(s['id'],s['revision'],'prepared')
    assert flow.store.get(s['id'])==s2


def test_live_sales_invalidate_approved_proposal_and_keep_old_price(flow):
    s=started(flow,mode='live')
    s=update(flow,s,'advance',{'target':1170})
    s=update(flow,s,'confirm_zero_sales',{'confirmed':True,'reason':'Verified zero before incoming sale'})
    pid=s['pending']['id']
    s=update(flow,s,'price_approve',{'proposal_id':pid})
    s=update(flow,s,'sales',{'rows':[{'sku_code':'BK-001','minute':1170,'quantity':2}]})
    assert s['phase']=='price_pending' and s['pending']['id']!=pid
    assert s['products']['BK-001']['discount']==0
    assert s['ledger'][-1]['paid']==2*s['products']['BK-001']['price']
    with pytest.raises(ValueError,match='duyệt'):
        update(flow,s,'price_apply',{'proposal_id':pid})
    with pytest.raises(ValueError,match='đúng phút'):
        update(flow,s,'sales',{'rows':[{'sku_code':'BK-001','minute':1169,'quantity':1}]})


def test_floor_rejection_requires_valid_alternative(flow):
    s=started(flow)
    for target in [1170,1200,1230]:
        s=update(flow,s,'advance',{'target':target})
        s=update(flow,s,'price_reject',{'proposal_id':s['pending']['id'],'reason':'Giữ giá'})
    s=update(flow,s,'advance',{'target':1260})
    with pytest.raises(ValueError,match='sàn'):
        update(flow,s,'price_reject',{'proposal_id':s['pending']['id'],'reason':'Giữ giá'})
    with pytest.raises(ValueError,match='thang giá'):
        update(flow,s,'price_approve',{'proposal_id':s['pending']['id'],'discounts':{'BK-001':25},'reason':'test'})

"""GD8 accounting evidence and isolated assumption sensitivity. No F04 policy comparison."""
import hashlib
import json
import math
from datetime import datetime, timezone
from .identity import actor
from .engine import LADDER
from .costs import estimate, COST_POLICY_ID


def fingerprint(s):
    content={k:s.get(k) for k in ['id','day','phase','revision','model_version','products','ledger']}
    content['financial_policy']=COST_POLICY_ID
    return hashlib.sha256(json.dumps(content,sort_keys=True,allow_nan=False).encode()).hexdigest()


def reconcile(s):
    errors=[]; rows=[]
    integer=lambda x:type(x) is int and x>=0
    for i,t in enumerate(s['ledger']):
        if t.get('sku') not in s['products'] or not all(integer(t.get(k)) for k in ['qty','unit_price','paid']) or t.get('qty',0)<=0:
            errors.append(f'Giao dịch {i+1}: SKU hoặc số lượng/tiền không hợp lệ.');continue
        if t['paid']!=t['qty']*t['unit_price']:errors.append(f'Giao dịch {i+1}: thành tiền khác số lượng × đơn giá.')
        discount=t.get('discount');p=s['products'][t['sku']]
        if not isinstance(discount,(int,float)) or not math.isfinite(discount) or not 0<=discount<=100 or t['unit_price']!=round(p['price']*(1-discount/100)):
            errors.append(f'Giao dịch {i+1}: đơn giá không khớp mức giảm ghi nhận.')
    for sku,p in s['products'].items():
        tx=[t for t in s['ledger'] if t.get('sku')==sku]
        qty=sum(t.get('qty',0) for t in tx);paid=sum(t.get('paid',0) for t in tx)
        ok=all(integer(p.get(k)) for k in ['prepared','sold','stock','revenue']) and p['prepared']==p['sold']+p['stock'] and p['sold']==qty and p['revenue']==paid
        if not ok:errors.append(sku+': lệch tồn, số bán hoặc doanh thu so với sổ giao dịch.')
        rows.append({'sku':sku,'prepared':p['prepared'],'sold':p['sold'],'ending_stock':p['stock'],'waste':p['stock'] if s['phase']=='closed' else None,'ledger_sold':qty,'reported_revenue':p['revenue'],'ledger_revenue':paid,'passed':ok})
    closed=s['phase']=='closed';valid=not errors
    revenue=sum(r['ledger_revenue'] for r in rows)
    financial=estimate(s['products'],closed=closed);cost=financial['preparation_cost']
    return {'session_id':s['id'],'day':s['day'],'mode':s['mode'],'model_version':s['model_version'],'revision':s['revision'],'state_sha256':fingerprint(s),'checked_at':datetime.now(timezone.utc).isoformat(),'status':'MISMATCH' if errors else 'RECONCILED' if closed else 'PROVISIONAL','publishable':closed and valid,'errors':errors,'rows':rows,'financial_estimate':financial,'kpis':{'revenue':revenue,'production_cost_assumed':cost,'contribution_before_overhead':financial['contribution_before_overhead'],'waste':sum(r['ending_stock'] for r in rows),'stockout_sku_sessions':sum(p['stock']==0 for p in s['products'].values()),'lost_sales':sum(p.get('lost',0) for p in s['products'].values()) if s['mode']=='simulation' else None} if closed and valid else None,'notes':['V4 unit cost × all actually prepared, including unsold stock; disposal 150 VND/unit at close; channel markdown costs included. No double counting of waste cost; contribution is not net profit.','Ending inventory is not confirmed physical disposal.','Unserved requests are simulator-only counts, not real customer footfall.']}


class Evaluation:
    def __init__(self,store,learning):
        self.store,self.learning=store,learning
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reconciliation_receipts(id TEXT PRIMARY KEY,session_id TEXT,payload TEXT)')
    def report(self,sid):
        report=reconcile(self.store.get(sid))
        with self.store.connect() as db:
            old=db.execute('SELECT payload FROM reconciliation_receipts WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
        report['receipt']=json.loads(old['payload']) if old else None
        report['receipt_current']=bool(old and report['receipt']['state_sha256']==report['state_sha256'])
        return report
    def certify(self,sid,revision,expected_hash,reason):
        if len(reason.strip())<3:raise ValueError('Cần lý do xác nhận đối soát.')
        with self.store.connect() as db:
            row=db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()
            if not row:raise ValueError('Không tìm thấy ca.')
            s=json.loads(row['state']);r=reconcile(s)
            if revision!=s['revision'] or expected_hash!=r['state_sha256']:raise ValueError('Ca đã thay đổi; tải lại đối soát.')
            if not r['publishable']:raise ValueError('Chỉ xác nhận ca đã đóng và đối soát khớp.')
            ident=r['state_sha256']
            old=db.execute('SELECT payload FROM reconciliation_receipts WHERE id=?',(ident,)).fetchone()
            if old:return json.loads(old['payload'])
            r.update(id=ident,actor=actor.get(),reason=reason.strip())
            db.execute('INSERT INTO reconciliation_receipts VALUES (?,?,?)',(ident,sid,json.dumps(r)))
            db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',(sid,'RECONCILIATION_CERTIFIED',json.dumps(r)))
        return r
    def sensitivity(self,sid):
        s=self.store.get(sid)
        if s['phase']!='closed':raise ValueError('Chốt ca trước khi phân tích giả định.')
        if not reconcile(s)['publishable']:raise ValueError('Đối soát lỗi; không công bố phân tích.')
        # Sensitivity uses V4 next-30min forecasts at recorded decisions, never a causal uplift.
        scenarios=[]
        for factor in [.5,1.,1.5]:
            units=revenue=0.;details=[]
            for d in s['decisions']:
                if d.get('status')!='applied':continue
                for r in d.get('rows',[]):
                    selected=next((c for c in r.get('candidates',[]) if c['discount']==r['approved']),None)
                    if selected is None:continue
                    qty=min(float(r['stock']),max(0,float(selected['expected_sales_next30'])*factor))
                    value=qty*round(r['price']*(1-r['approved']/100));units+=qty;revenue+=value
                    details.append({'sku':r['sku'],'slot':d['minute'],'expected_next30':qty})
            scenarios.append({'response_factor':factor,'incremental_units_sum':units,'incremental_revenue_sum':revenue,'rows':details})
        return {'session_id':sid,'model_version':e.version,'scenarios':scenarios,'note':'Độ nhạy dự báo bán 30 phút V4 tại các snapshot đã áp dụng. Đây là lượng bán dự kiến (không phải uplift). Không cộng thành doanh thu cả ca, không tái chạy model/policy hoặc dùng kết quả này để tune.'}

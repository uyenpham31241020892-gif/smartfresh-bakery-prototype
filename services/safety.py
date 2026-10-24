"""GD6 local incident state machine, rule fallback and recovery evidence."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import math
import uuid
from .identity import actor,request_trace
from .quality import sales_quality, digest, build_snapshot
from .engine import LADDER, CAPS, FLOORS


class GuardError(ValueError):
    pass


def now():return datetime.now(timezone.utc).isoformat()


class Safety:
    def __init__(self,store,resolver):
        self.store,self.resolver=store,resolver
        self.bound=ContextVar('safety_db_'+str(id(self)),default=None)
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS safety_controls(sid TEXT PRIMARY KEY,mode TEXT NOT NULL DEFAULT 'assisted',faults TEXT NOT NULL DEFAULT '[]',version INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,sid TEXT,kind TEXT,priority TEXT,status TEXT,detail TEXT,owner TEXT,verification TEXT,created TEXT,updated TEXT);
            ''')

    @contextmanager
    def bind(self,db):
        token=self.bound.set(db)
        try:yield
        finally:self.bound.reset(token)

    @contextmanager
    def connection(self):
        if self.bound.get() is not None:yield self.bound.get()
        else:
            with self.store.connect() as db:yield db

    def audit(self,db,sid,action,detail):
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',(sid,action,json.dumps({'actor':actor.get(),'request_id':request_trace.get(),'at':now(),**detail},ensure_ascii=False)))

    def control(self,sid):
        with self.connection() as db:
            r=db.execute('SELECT * FROM safety_controls WHERE sid=?',(sid,)).fetchone()
        return {**dict(r),'faults':json.loads(r['faults'])} if r else {'sid':sid,'mode':'assisted','faults':[],'version':0}

    def report(self,sid,kind,message,priority='P1',force_manual=True):
        with self.connection() as db:
            row=db.execute("SELECT id FROM incidents WHERE sid=? AND kind=? AND status!='resolved'",(sid,kind)).fetchone()
            if row:return row['id']
            iid=uuid.uuid4().hex
            db.execute('INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (iid,sid,kind,priority,'open',str(message)[:2000],None,None,now(),now()))
            if force_manual:
                db.execute("INSERT INTO safety_controls(sid,mode,version) VALUES (?,'manual',1) ON CONFLICT(sid) DO UPDATE SET mode='manual',version=version+1",(sid,))
            self.audit(db,sid,'INCIDENT_OPENED',{'incident_id':iid,'kind':kind,'priority':priority,'detail':str(message)[:2000]})
        return iid

    def incidents(self,sid=None):
        with self.connection() as db:
            rows=db.execute('SELECT * FROM incidents '+('WHERE sid=? OR sid=\'__system__\' ' if sid else '')+'ORDER BY created DESC LIMIT 100',(sid,) if sid else ()).fetchall()
        return [dict(r) for r in rows]

    def safe_plan(self,sid,engine,day,visible,weather,outcomes):
        c=self.control(sid)
        try:
            if 'm2_error' in c['faults']:raise RuntimeError('Drill: M2 prediction failed (synthetic fault)')
            if c['mode']=='manual':return self.rolling7(engine,day,visible,weather,outcomes),'RULE_ROLLING7'
            engine.require_integrity()
            plans=engine.plan(day,visible,weather,outcomes)
            if {p['sku'] for p in plans}!=set(engine.master) or len(plans)!=len(engine.master) or any(not math.isfinite(p['forecast']) or p['forecast']<0 or type(p['prepared']) is not int or not 4<=p['prepared']<=100000 or p['prepared']%4 or p['prepared']<p['floor'] for p in plans):
                raise GuardError('M2 output violates numeric/batch/floor rules')
            return plans,'AI_M2'
        except Exception as exc:
            self.report(sid,'M2_UNAVAILABLE',str(exc))
            return self.rolling7(engine,day,visible,weather,outcomes),'RULE_ROLLING7'

    @staticmethod
    def rolling7(engine,day,visible,weather,outcomes):
        plans=[]
        for sku,r in engine.master.items():
            vals=[v for (d,s),v in visible.items() if s==sku and 0<(datetime.fromisoformat(day)-datetime.fromisoformat(d)).days<=7]
            if not vals:raise GuardError('Không có lịch sử hợp lệ cho Rolling-7; không tự đoán 0.')
            forecast=sum(vals)/len(vals);base=engine.baseline(day,sku,visible);floor=4*math.ceil(.9*base/4)
            qty=max(4,base,floor)
            plans.append({'sku':sku,'name':r['product_name_reference'].removeprefix('AEON BREAD '),'price':int(r['unit_price_vnd_reference']),
                          'baseline':base,'forecast':forecast,'buffer':qty-forecast,'floor':floor,'prepared':qty,'batches':qty//4,
                          'quantile':None,'features':engine.features(day,sku,visible,weather,outcomes),'model_bias':None,'contributions':[],
                          'history_warning':len(vals)<7,'prediction_origin':'RULE_ROLLING7','explanation':'Rolling-7 + baseline rule + batch 4; chờ Manager duyệt, không có TreeSHAP.'})
        return plans

    def price_gate(self,s):
        c=self.control(s['id'])
        if 'stale_stock' in c['faults'] or sales_quality(s)['status']=='BLOCK':
            self.report(s['id'],'STOCK_UNTRUSTED','Nguồn tồn/bán chưa có hoặc quá hạn; không gợi ý giá.','P2')
            return 'blocked'
        if 'm1_error' in c['faults']:
            self.report(s['id'],'M1_UNAVAILABLE','Drill: M1 không phản hồi; giữ giá đang hiệu lực và chờ xử lý thủ công.')
            return 'manual'
        return c['mode']

    @staticmethod
    def manual_rows(s,j):
        rows=[]
        for sku,p in s['products'].items():
            if not 0<=p['stock']<=p['prepared']:raise GuardError('Tồn kho không hợp lệ; không được tự sửa số liệu.')
            tier=max(p['discount'],FLOORS[j])
            if tier not in LADDER or tier>CAPS[j]:raise GuardError('Giá hiện tại không tương thích hard rules.')
            tx=[t for t in s['ledger'] if t['sku']==sku]
            sales30=sum(t['qty'] for t in tx if s['minute']-30<=t['minute']<=s['minute'])
            sales60=sum(t['qty'] for t in tx if s['minute']-60<=t['minute']<=s['minute'])
            rows.append({'sku':sku,'minute':s['minute'],'stock':p['stock'],'sales30':sales30,'sales60':sales60,'previous':p['discount'],
                         'discount':tier,'price':p['price'],'new_price':round(p['price']*(1-tier/100)),'cap':CAPS[j],'floor':FLOORS[j],
                         'schedule':[],'candidates':[],'low_stock':p['stock']<=3,'reason':'MANUAL_HOLD_OR_MANDATORY_FLOOR'})
        return rows

    def set_mode(self,sid,mode,reason,expected_revision):
        if mode not in ['manual','assisted','shadow'] or not reason.strip():raise ValueError('Cần chế độ hợp lệ và lý do.')
        s=self.store.get(sid)
        if s['revision']!=expected_revision:raise ValueError('Dữ liệu đã thay đổi; tải lại ca.')
        if s['phase']=='closed':raise ValueError('Ca đã chốt; không đổi chế độ.')
        if mode!='manual':
            if any(r['status']!='resolved' for r in self.incidents(sid)):raise GuardError('Còn sự cố chưa đóng; chưa được bật AI.')
            self.verify_state(s)
        with self.store.connect() as db:
            latest=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()['state'])
            if latest['revision']!=expected_revision:raise ValueError('Dữ liệu đã thay đổi; tải lại ca.')
            db.execute('INSERT INTO safety_controls(sid,mode,version) VALUES (?,?,1) ON CONFLICT(sid) DO UPDATE SET mode=excluded.mode,version=version+1',(sid,mode))
            if latest.get('pending'):
                latest['pending']['status']='expired_mode_change';latest['decisions'].append(latest['pending']);latest['pending']=None
                latest['phase']='running'
            latest['revision']+=1
            self.store.save(db,latest,'SAFETY_MODE_CHANGED',{'mode':mode,'reason':reason})
        return latest

    def verify_state(self,s):
        c=self.control(s['id'])
        if c['faults']:raise GuardError('Chưa gỡ lỗi diễn tập: '+', '.join(c['faults']))
        engine=self.resolver(s['model_version']);engine.require_integrity();engine.reload_if_needed()
        from .workflow import Workflow
        Workflow.assert_accounts(s)
        if s['minute']>=1170 and s['phase']!='closed' and sales_quality(s)['status']=='BLOCK':raise GuardError('Nguồn bán/tồn chưa mới; chưa được phục hồi AI.')
        history={(r['date'],r['sku']):r['sold'] for r in s['input_history']}
        outcomes={(r['date'],r['sku_code']):r for r in s.get('input_outcomes',[])}
        q=s.get('data_quality',{})
        trusted_demo=q.get('weather',{}).get('status')=='WARN' and q.get('lineage',{}).get('weather_origin')=='bundled_V606_lagged_reanalysis'
        feature_rows=[{'sku':sku,'features':engine.features(s['day'],sku,history,s['weather'],outcomes)} for sku in engine.master]
        build_snapshot(s['day'],history,s['weather'],engine,feature_rows,outcomes,q.get('lineage',{}),trusted_demo)
        rows=engine.plan(s['day'],history,s['weather'],outcomes)
        if not all(math.isfinite(p['forecast']) and p['prepared']%4==0 and p['prepared']>=p['floor'] for p in rows):raise GuardError('Smoke test M2 thất bại.')
        j=max(0,min(4,sum(s['minute']>=t for t in [1170,1200,1230,1260,1290])-1))
        for sku,p in s['products'].items():
            r=engine.price(sku,j,p['stock'],p['prepared'],p['discount'],0,0,p['forecast'],s['weather'],as_of=s['minute'])
            if r['discount'] not in LADDER or not max(p['discount'],FLOORS[j])<=r['discount']<=CAPS[j]:raise GuardError('Smoke test M1 hard rules thất bại.')
        return {'passed':True,'revision':s['revision'],'control_version':c['version'],'model_version':engine.version,
                'model_hashes':engine.manifest['native_model_hashes'],'checked_at':now(),
                'checks':['artifact_hash','accounting','fresh_feed','no_drill_fault','point_in_time_inputs','M2_smoke','M1_hard_rules'],
                'fingerprint':digest({'revision':s['revision'],'control_version':c['version'],'model_hashes':engine.manifest['native_model_hashes']})}

    def transition(self,iid,action,reason):
        if not reason.strip():raise ValueError('Cần ghi nhận lý do / hành động khắc phục.')
        with self.store.connect() as db:r=db.execute('SELECT * FROM incidents WHERE id=?',(iid,)).fetchone()
        if not r:raise ValueError('Không tìm thấy sự cố.')
        r=dict(r)
        if r['status']=='resolved':raise ValueError('Sự cố đã đóng.')
        if action=='acknowledge':
            if r['status']!='open':raise ValueError('Sự cố đã được tiếp nhận.')
            status='acknowledged';receipt=None
        elif action in ['verify','resolve']:
            if r['status']!='acknowledged':raise ValueError('Cần tiếp nhận sự cố trước khi kiểm tra/đóng.')
            if r['sid']=='__system__':
                eng=self.resolver(None);eng.require_integrity();eng.reload_if_needed()
                receipt={'passed':True,'model_hashes':eng.manifest['native_model_hashes'],'checked_at':now()}
            else:receipt=self.verify_state(self.store.get(r['sid']))
            if action=='resolve':
                if not r['verification']:raise GuardError('Cần chạy kiểm tra phục hồi trước khi đóng sự cố.')
                previous=json.loads(r['verification'])
                if previous.get('fingerprint')!=receipt.get('fingerprint') or previous.get('model_hashes')!=receipt.get('model_hashes'):
                    raise GuardError('Dữ liệu/model đã đổi sau kiểm tra; hãy Verify lại.')
                status='resolved'
            else:status='acknowledged'
        else:raise ValueError('Thao tác sự cố không hợp lệ.')
        with self.store.connect() as db:
            current=db.execute('SELECT status,updated FROM incidents WHERE id=?',(iid,)).fetchone()
            if current['status']!=r['status'] or current['updated']!=r['updated']:raise ValueError('Sự cố đã thay đổi; tải lại.')
            db.execute('UPDATE incidents SET status=?,owner=?,verification=?,updated=? WHERE id=?',
                       (status,actor.get()['username'],json.dumps(receipt) if receipt else None,now(),iid))
            self.audit(db,r['sid'],'INCIDENT_'+action.upper(),{'incident_id':iid,'reason':reason,'verification':receipt})
        return {'id':iid,'status':status,'verification':receipt}

    def fault(self,sid,kind,reason,revision):
        self.store.get(sid)
        if kind not in ['m1_error','m2_error','stale_stock','clear']:raise ValueError('Loại diễn tập không hợp lệ.')
        with self.store.connect() as db:
            s=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()['state'])
            if s['mode']!='simulation' or s['phase']=='closed':raise GuardError('Chỉ diễn tập trên ca mô phỏng chưa chốt.')
            if s['revision']!=revision:raise ValueError('Dữ liệu đã thay đổi; tải lại.')
            if kind=='m2_error' and s['phase']!='plan_pending':raise ValueError('Diễn tập M2 cần ca mới đang chờ duyệt sản lượng.')
            db.execute("INSERT INTO safety_controls(sid,mode,faults,version) VALUES (?,'manual',?,1) ON CONFLICT(sid) DO UPDATE SET faults=excluded.faults,version=version+1",(sid,json.dumps([] if kind=='clear' else [kind])))
            s['revision']+=1
            self.store.save(db,s,'SAFETY_DRILL',{'kind':kind,'reason':reason})
        if kind!='clear':self.report(sid,{'m1_error':'M1_UNAVAILABLE','m2_error':'M2_UNAVAILABLE','stale_stock':'STOCK_UNTRUSTED'}[kind], 'Lỗi diễn tập: '+kind,'P2' if kind=='stale_stock' else 'P1')
        return s

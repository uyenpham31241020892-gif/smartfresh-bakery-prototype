"""GD7: observational monitoring. Evaluation targets never enter inference/training.
Uses only existing dependencies; schema additions preserve all GD6 tables.
"""
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
import numpy as np
import pandas as pd
from .engine import DATA, ROOT, SLOTS, LADDER, CAPS, FLOORS
from .identity import actor
from .quality import digest, sales_quality

FEATURES = ['sold_calendar_lag1','sold_calendar_lag7','sold_last7_observed_mean','prepared_last_observed','censored_last7_observed_rate','prior_day_rain_mm','prior_day_temp_c']
DEFAULTS = {'version':0,'psi_threshold':None,'performance_delta_pp':None,'academic_wape_goal_pct':18.,
            'window_days':7,'min_rows':30,'min_days':5,'calibration_note':'Chưa hiệu chỉnh ngưỡng drift; không phải SLA production.'}


def utcnow():return datetime.now(timezone.utc).isoformat()
def number(v):
    try:return float(v) if math.isfinite(float(v)) else None
    except (ValueError,TypeError):return None

def metric(rows):
    values=[(number(r.get('prediction')),number(r.get('actual'))) for r in rows]
    values=[(p,a) for p,a in values if p is not None and a is not None and a>=0]
    if not values:return {'n':0,'wape_pct':None,'mae':None,'bias_pct':None,'actual_sum':0,'prediction_sum':0}
    p,a=np.asarray(values).T;den=float(a.sum())
    return {'n':len(values),'wape_pct':float(np.abs(p-a).sum()/den*100) if den else None,
            'mae':float(np.abs(p-a).mean()),'bias_pct':float((p-a).sum()/den*100) if den else None,
            'actual_sum':den,'prediction_sum':float(p.sum())}


def distribution(reference,current):
    r=np.array([n for x in reference if (n:=number(x)) is not None]);c=np.array([n for x in current if (n:=number(x)) is not None])
    if not len(r) or not len(c):return {'psi':None,'ks_statistic':None,'reference_n':len(r),'current_n':len(c),'bins':[]}
    if np.ptp(r)==0:
        eps=max(abs(float(r[0]))*1e-6,1e-6);edges=np.array([-np.inf,r[0]-eps,r[0]+eps,np.inf])
    else:edges=np.r_[-np.inf,np.unique(np.quantile(r,[.1,.2,.3,.4,.5,.6,.7,.8,.9])),np.inf]
    rc=np.histogram(r,edges)[0];cc=np.histogram(c,edges)[0]
    rp=(rc+.5)/(len(r)+.5*len(rc));cp=(cc+.5)/(len(c)+.5*len(cc))
    psi=float(np.sum((cp-rp)*np.log(cp/rp)))
    support=np.unique(np.r_[r,c]);ks=float(np.max(np.abs(np.searchsorted(np.sort(r),support,side='right')/len(r)-np.searchsorted(np.sort(c),support,side='right')/len(c))))
    bins=[{'low':number(edges[i]),'high':number(edges[i+1]),'reference_count':int(rc[i]),'current_count':int(cc[i]),
           'reference_pct':float(rc[i]/len(r)*100),'current_pct':float(cc[i]/len(c)*100)} for i in range(len(rc))]
    return {'psi':psi,'ks_statistic':ks,'reference_n':len(r),'current_n':len(c),'reference_mean':float(r.mean()),'current_mean':float(c.mean()),'bins':bins,
            'method':'PSI: reference deciles, pseudocount 0.5; KS statistic only, no p-value.'}


class Monitoring:
    @staticmethod
    def ensure_schema(store):
        if getattr(store,'_monitoring_ready',False):return
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS monitoring_http(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT,route TEXT,method TEXT,status INTEGER,elapsed_ms REAL,request_id TEXT);
                CREATE INDEX IF NOT EXISTS monitoring_http_time ON monitoring_http(created);
                CREATE TABLE IF NOT EXISTS monitoring_jobs(id TEXT PRIMARY KEY,kind TEXT,sid TEXT,status TEXT,created TEXT,finished TEXT,elapsed_ms REAL,error_type TEXT);
                CREATE TABLE IF NOT EXISTS monitoring_evaluations(sid TEXT PRIMARY KEY,state_hash TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS monitoring_sandboxes(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS monitoring_settings(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS monitoring_alerts(id TEXT PRIMARY KEY,scope TEXT,code TEXT,severity TEXT,title TEXT,message TEXT,evidence TEXT,evidence_hash TEXT,active INTEGER,ack_by TEXT,ack_at TEXT,ack_note TEXT,first_seen TEXT,last_seen TEXT,cleared_at TEXT);
                CREATE INDEX IF NOT EXISTS monitoring_alert_scope ON monitoring_alerts(scope,active);
            ''')
        store._monitoring_ready=True

    def __init__(self,store,engine,simulator,workflow):
        self.store,self.engine,self.simulator,self.workflow=store,engine,simulator,workflow
        self.ensure_schema(store)

    @staticmethod
    def record_http(store,route,method,status,elapsed_ms,request_id):
        # No query strings, credentials, request bodies or response payloads are persisted.
        Monitoring.ensure_schema(store)
        with store.connect() as db:
            db.execute('INSERT INTO monitoring_http(created,route,method,status,elapsed_ms,request_id) VALUES (?,?,?,?,?,?)',
                       (utcnow(),route,method,int(status),max(0,float(elapsed_ms)),request_id))
            db.execute('DELETE FROM monitoring_http WHERE id NOT IN (SELECT id FROM monitoring_http ORDER BY id DESC LIMIT 20000)')

    @staticmethod
    @contextmanager
    def job(store,kind,sid=None):
        jid=uuid.uuid4().hex;started=time.perf_counter();tracked=False;status='succeeded';error_type=None
        try:
            Monitoring.ensure_schema(store)
            with store.connect() as db:db.execute('INSERT INTO monitoring_jobs VALUES (?,?,?,?,?,?,?,?)',(jid,kind,sid,'running',utcnow(),None,None,None))
            tracked=True
        except Exception:
            pass  # Job observability must not block the work itself.
        try:
            yield jid
        except ValueError as exc:
            status='rejected';error_type=type(exc).__name__;raise
        except Exception as exc:
            status='failed';error_type=type(exc).__name__;raise
        except BaseException as exc:
            status='interrupted';error_type=type(exc).__name__;raise
        finally:
            if tracked:
                try:
                    with store.connect() as db:db.execute('UPDATE monitoring_jobs SET status=?,finished=?,elapsed_ms=?,error_type=? WHERE id=?',
                        (status,utcnow(),(time.perf_counter()-started)*1000,error_type,jid))
                except Exception:
                    pass

    @staticmethod
    def recover_jobs(store):
        Monitoring.ensure_schema(store)
        with store.connect() as db:db.execute("UPDATE monitoring_jobs SET status='interrupted',finished=?,error_type='SERVER_RESTART' WHERE status='running'",(utcnow(),))

    def settings(self):
        with self.store.connect() as db:r=db.execute('SELECT payload FROM monitoring_settings WHERE id=1').fetchone()
        return {**DEFAULTS,**(json.loads(r['payload']) if r else {})}

    def configure(self,payload):
        old=self.settings();new={**old}
        if payload.get('expected_version')!=old['version']:raise ValueError('Cấu hình đã thay đổi; tải lại trước khi lưu.')
        for field in ['psi_threshold','performance_delta_pp']:
            v=payload.get(field)
            if v is not None and (type(v) not in [int,float] or not math.isfinite(v) or v<=0 or v>100):raise ValueError('Ngưỡng cần là số dương hữu hạn, hoặc để trống.')
            new[field]=v
        note=str(payload.get('calibration_note','')).strip()
        if len(note)<8 or len(note)>500:raise ValueError('Cần ghi chú hiệu chỉnh/thử nghiệm 8–500 ký tự; ngưỡng chưa phải SLA.')
        new['calibration_note']=note;new['version']+=1;new['updated_by']=actor.get()['username'];new['updated_at']=utcnow()
        with self.store.connect() as db:
            r=db.execute('SELECT payload FROM monitoring_settings WHERE id=1').fetchone()
            version=json.loads(r['payload'])['version'] if r else 0
            if version!=old['version']:raise ValueError('Cấu hình đã thay đổi; tải lại.')
            db.execute('INSERT INTO monitoring_settings VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(json.dumps(new),))
            self.workflow.safety.audit(db,None,'MONITORING_CONFIG_CHANGED',{'before':old,'after':new})
        return new

    def closed_evaluation(self,s):
        if s['phase']!='closed':return []
        from .evaluation import reconcile
        if not reconcile(s)['publishable']:return []
        state_hash=digest({k:s.get(k) for k in ['id','revision','day','model_version','prediction_origin','plan','products','weather','simulator_hash','simulator_version','seed']})
        with self.store.connect() as db:r=db.execute('SELECT * FROM monitoring_evaluations WHERE sid=?',(s['id'],)).fetchone()
        if r and r['state_hash']==state_hash:return json.loads(r['payload'])
        if s['mode']=='simulation':
            if s.get('simulator_hash')!=self.simulator.hash_for(s.get('simulator_version')):return []
            try:actual=self.simulator.evaluation_counts(s['day'],s.get('simulator_version'))
            except ValueError:return []
            target='V4_organic_simulated_requests' if s.get('simulator_version')==self.simulator.version else 'V4_observed_POS_replay'
            target_note='Nhu cầu gốc mô phỏng V4 chỉ đọc sau chốt ca; không đưa vào feature.' if target=='V4_organic_simulated_requests' else 'Lượng bán quan sát replay V4, có thể bị censored; không phải nhu cầu tiềm ẩn.'
        else:
            actual={sku:p['sold'] for sku,p in s['products'].items()}
            target='observed_sales_proxy';target_note='Số bán quan sát, có thể bị kiểm duyệt do hết hàng/khuyến mãi; không phải nhãn nhu cầu gốc.'
        rows=[]
        for p in s['plan']:
            sku=p['sku'];product=s['products'].get(sku)
            if product is None:continue
            rows.append({'session_id':s['id'],'day':s['day'],'sku':sku,'model_version':s['model_version'],
                         'origin':p.get('prediction_origin',s.get('prediction_origin','LEGACY_UNKNOWN')),
                         'target_kind':target,'target_note':target_note,'prediction':p['forecast'],'actual':actual.get(sku,0),
                         'features':{f:p.get('features',{}).get(f) for f in FEATURES},
                         'weekday':s['weather'].get('weekday_iso'),'is_holiday':s['weather'].get('is_public_holiday',0),
                         'rain_mm':s['weather'].get('forecast_rain_mm_previous_day1'),
                         'evaluation_recorded_at':utcnow(),'simulator_hash':s.get('simulator_hash'),'simulator_version':s.get('simulator_version'),
                         'stockout':product.get('first_stockout_minute',1320)<1320 or product['stock']==0 or any(x['date']==s['day'] and x['sku_code']==sku and x.get('censored_demand_flag') for x in self.engine.observed),'source_mode':s['mode'],'is_synthetic':s['mode']=='simulation'})
        with self.store.connect() as db:
            db.execute('INSERT INTO monitoring_evaluations VALUES (?,?,?) ON CONFLICT(sid) DO UPDATE SET state_hash=excluded.state_hash,payload=excluded.payload',
                       (s['id'],state_hash,json.dumps(rows,allow_nan=False)))
        return rows

    @staticmethod
    def accuracy(rows):
        grouped=defaultdict(list)
        for r in rows:grouped[(r['model_version'],r['origin'],r['target_kind'])].append(r)
        result=[]
        for (model,origin,target),group in sorted(grouped.items()):
            daily=[]
            for day in sorted({r['day'] for r in group}):daily.append({'day':day,**metric([r for r in group if r['day']==day])})
            slices={}
            for field,fn in [('sku',lambda r:r['sku']),('day_type',lambda r:'holiday' if r['is_holiday'] else 'weekend' if (r.get('weekday') or 1)>=6 else 'weekday'),
                             ('weather',lambda r:'missing' if number(r.get('rain_mm')) is None else 'rainy' if r['rain_mm']>0 else 'dry')]:
                keys=sorted({str(fn(r)) for r in group})
                slices[field]=[{'slice':k,**metric([r for r in group if str(fn(r))==k])} for k in keys]
            result.append({'model_version':model,'origin':origin,'target_kind':target,'target_note':group[0]['target_note'],
                           'is_synthetic':all(r['is_synthetic'] for r in group),'session_count':len({r['session_id'] for r in group}),
                           'day_count':len(daily),'stockout_rows':sum(r['stockout'] for r in group),'metrics':metric([r for r in group if not r.get('stockout')]),'all_observed_metrics':metric(group),'uncensored_metrics':metric([r for r in group if not r.get('stockout')]),'censored_rate_pct':100*sum(bool(r.get('stockout')) for r in group)/len(group),'daily':daily,'slices':slices})
        return result

    def reference(self,engine,sku=''):
        if engine.manifest.get('parent'):return [],{'available':False,'reason':'Không có reference feature tương thích đã đăng ký.'}
        path=DATA/'fit_features.csv'
        try:
            engine.require_integrity();sha=hashlib.sha256(path.read_bytes()).hexdigest()
            frame=pd.read_csv(path)
        except (OSError,ValueError):return [],{'available':False,'reason':'Reference V4 không vượt kiểm tra hash.'}
        frame=frame[frame['date']<=engine.manifest['trained_until']]
        if sku:frame=frame[frame.sku_code==sku]
        columns=['date','sku_code']+[f for f in FEATURES if f in frame]
        return frame[columns].to_dict('records'),{'available':True,'sha256':sha,'rows':len(frame),'from':frame.date.min() if len(frame) else None,'through':frame.date.max() if len(frame) else None,'source':'V4 Fit feature reference, proxy data','features':[f for f in FEATURES if f in frame]}

    def drift(self,feature_rows,evaluation_rows,engine,config,sku=''):
        reference,manifest=self.reference(engine,sku)
        current=[r for r in feature_rows if r['model_version']==engine.version and r['origin']=='AI_M2']
        current_days=sorted({r['day'] for r in current})[-config['window_days']:]
        current=[r for r in current if r['day'] in current_days]
        days=len(current_days);result=[]
        for f in FEATURES:
            refs=[r.get(f) for r in reference];vals=[r.get('features',{}).get(f) for r in current]
            dist=distribution(refs,vals)
            eligible=manifest['available'] and dist['reference_n']>=config['min_rows'] and dist['current_n']>=config['min_rows'] and days>=config['min_days']
            status='INSUFFICIENT' if not eligible else 'UNCONFIGURED' if config['psi_threshold'] is None else 'REVIEW' if dist['psi']>=config['psi_threshold'] else 'WITHIN_LOCAL_THRESHOLD'
            result.append({'feature':f,**dist,'eligible':eligible,'status':status,'current_days':days})
        comparable=[r for r in evaluation_rows if r['model_version']==engine.version and r['origin']=='AI_M2' and r['target_kind']!='observed_sales_proxy']
        performance=[]
        for target in sorted({r['target_kind'] for r in comparable}):
            rows=[r for r in comparable if r['target_kind']==target];dates=sorted({r['day'] for r in rows});w=config['window_days']
            recent_days=dates[-w:];previous_days=dates[-2*w:-w]
            recent=[r for r in rows if r['day'] in recent_days];previous=[r for r in rows if r['day'] in previous_days]
            rm,pm=metric(recent),metric(previous)
            eligible=min(len(recent_days),len(previous_days))>=config['min_days'] and min(rm['n'],pm['n'])>=config['min_rows'] and rm['wape_pct'] is not None and pm['wape_pct'] is not None
            delta=rm['wape_pct']-pm['wape_pct'] if eligible else None
            performance.append({'target_kind':target,'reference':pm,'recent':rm,'reference_days':previous_days,'recent_days':recent_days,
                                'delta_wape_pp':delta,'eligible':eligible,'status':'INSUFFICIENT' if not eligible else 'UNCONFIGURED' if config['performance_delta_pp'] is None else 'REVIEW' if delta>=config['performance_delta_pp'] else 'WITHIN_LOCAL_THRESHOLD'})
        return {'reference':manifest,'data':result,'performance':performance,
                'note':'PSI/KS mô tả thay đổi, không chứng minh nguyên nhân hay suy giảm accuracy. Không p-value, không auto retrain/rollback. Cửa sổ performance dùng ngày có quan sát, cùng model/origin/target.'}

    @staticmethod
    def safety(states):
        violations=[];checked_proposed=checked_applied=0;counts=Counter();seen=set()
        for s in states:
            for d in s.get('decisions',[])+([s['pending']] if s.get('pending') else []):
                key=(s['id'],d.get('id'))
                if key in seen:continue
                seen.add(key);counts[d.get('status','unknown')]+=1
                minute=d.get('as_of_minute',d.get('minute',0));j=max((i for i,t in enumerate(SLOTS) if t<=minute),default=-1)
                for r in d.get('rows',[]):
                    for phase,value in [('proposal',r.get('discount'))]+([('applied',r.get('approved'))] if d.get('status')=='applied' else []):
                        if phase=='proposal':checked_proposed+=1
                        else:checked_applied+=1
                        previous=r.get('previous',0)
                        valid=j>=0 and type(value) is int and value in LADDER and max(previous,FLOORS[j])<=value<=CAPS[j]
                        if not valid:violations.append({'session_id':s['id'],'proposal_id':d.get('id'),'sku':r.get('sku'),'phase':phase,'value':value,'minute':minute})
        return {'checked_proposal_rows':checked_proposed,'checked_applied_rows':checked_applied,
                'proposal_violations':sum(r['phase']=='proposal' for r in violations),'applied_violations':sum(r['phase']=='applied' for r in violations),
                'violations':violations[:100],'proposal_status_counts':dict(counts),
                'note':'Vi phạm đề xuất, vi phạm đã áp dụng và số lần backend chặn là ba số khác nhau; Shadow không được tính là applied.'}

    def operations(self,states):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
        with self.store.connect() as db:
            http=[dict(r) for r in db.execute('SELECT route,method,status,elapsed_ms,request_id,created FROM monitoring_http WHERE created>=? ORDER BY id DESC LIMIT 20000',(cutoff,))]
            audit=[dict(r) for r in db.execute('SELECT session_id,action,detail FROM audit ORDER BY id DESC LIMIT 20000')]
            jobs=[dict(r) for r in db.execute('SELECT * FROM monitoring_jobs WHERE created>=? ORDER BY created DESC LIMIT 100',(cutoff,))]
            clocks=[dict(r) for r in db.execute('SELECT sid,enabled,error FROM simulation_clocks')] if db.execute("SELECT 1 FROM sqlite_master WHERE name='simulation_clocks'").fetchone() else []
        routes=defaultdict(list)
        for r in http:routes[(r['method'],r['route'])].append(r)
        def stats(rows):
            lat=[r['elapsed_ms'] for r in rows]
            return {'requests':len(rows),'http_4xx':sum(400<=r['status']<500 for r in rows),'http_5xx':sum(r['status']>=500 for r in rows),
                    'p50_ms':float(np.percentile(lat,50)) if lat else None,'p95_ms':float(np.percentile(lat,95)) if lat else None}
        ids={s['id'] for s in states};events=[r for r in audit if r['session_id'] in ids];eventcounts=Counter(r['action'] for r in events)
        overrides=0
        for r in events:
            if r['action'] not in ['PLAN_APPROVE','PRICE_APPROVE']:continue
            d=json.loads(r['detail']);after=d.get('after',{})
            if r['action']=='PLAN_APPROVE':overrides+=int(any(v.get('approved') is not None and v.get('approved')!=v.get('proposed') for v in after.get('quantities',{}).values()))
            else:overrides+=int(any(v.get('approved') is not None and v.get('approved')!=v.get('discount') for v in after.get('proposal',{}).get('rows',[])))
        workflow={'pending_plan':sum(s['phase']=='plan_pending' for s in states),'pending_price':sum(s['phase']=='price_pending' for s in states),
                  'approved_not_applied':sum(s['phase']=='price_approved' for s in states),'approvals':eventcounts['PLAN_APPROVE']+eventcounts['PRICE_APPROVE'],
                  'rejections':eventcounts['PLAN_REJECT']+eventcounts['PRICE_REJECT'],'overrides':overrides,'event_counts':dict(eventcounts)}
        return {'http':{**stats(http),'window_hours':24,'clock':'wall_clock_UTC','retention_max':20000,
                        'routes':[{'method':m,'route':p,**stats(v)} for (m,p),v in sorted(routes.items())],
                        'recent_errors':[r for r in http if r['status']>=400][:20],
                        'note':'API local 24 giờ theo thời gian máy; không lưu body/query/credentials. GET snapshot monitoring thành công bị loại để tránh tự làm lệch mẫu; thao tác sandbox/config/ack vẫn được ghi.'},
                'workflow':workflow,'job_failures':[{'kind':'SIMULATION_CLOCK',**r} for r in clocks if r['error'] and (not ids or r['sid'] in ids)]+[{'kind':r['kind'],'sid':r['sid'] or 'workspace','error':r['error_type'],'status':r['status']} for r in jobs if r['status'] in ['failed','interrupted'] and (not r['sid'] or not ids or r['sid'] in ids)],
                'jobs_recent':jobs,'jobs_status_counts':dict(Counter(r['status'] for r in jobs)),
                'audit_scanned':len(audit),'audit_truncated':len(audit)==20000}

    @staticmethod
    def business(states):
        closed=[s for s in states if s['phase']=='closed'];daily=[];mismatches=[]
        for s in closed:
            prepared=sold=waste=revenue=stockouts=0;lost=0 if s['mode']=='simulation' else None
            for sku,p in s['products'].items():
                prepared+=p['prepared'];sold+=p['sold'];waste+=p['stock'];revenue+=p['revenue'];stockouts+=p['stock']==0
                if lost is not None:lost+=p.get('lost',0)
                ledger=[t for t in s['ledger'] if t['sku']==sku]
                if p['prepared']!=p['stock']+p['sold'] or p['stock']<0 or p['revenue']!=sum(t['paid'] for t in ledger) or p['sold']!=sum(t['qty'] for t in ledger):mismatches.append({'session_id':s['id'],'sku':sku})
            from .evaluation import reconcile
            check=reconcile(s)
            if check['errors']:
                if not any(m['session_id']==s['id'] for m in mismatches):mismatches.append({'session_id':s['id'],'sku':'LEDGER'})
                continue
            daily.append({'session_id':s['id'],'day':s['day'],'mode':s['mode'],'prepared':prepared,'sold':sold,'waste':waste,'revenue_vnd':revenue,
                          'waste_rate_pct':waste/prepared*100 if prepared else None,'stockout_sku_rows':stockouts,'lost_simulator_only':lost})
        groups=[]
        for mode in sorted({r['mode'] for r in daily}):
            rows=[r for r in daily if r['mode']==mode];p=sum(r['prepared'] for r in rows);w=sum(r['waste'] for r in rows)
            groups.append({'mode':mode,'sessions':len(rows),'prepared':p,'sold':sum(r['sold'] for r in rows),'waste':w,'waste_rate_pct':w/p*100 if p else None,
                           'revenue_vnd':sum(r['revenue_vnd'] for r in rows),'stockout_sku_rows':sum(r['stockout_sku_rows'] for r in rows),
                           'lost_simulator_only':sum(r['lost_simulator_only'] for r in rows) if mode=='simulation' else None})
        return {'groups':groups,'daily':daily,'mismatches':mismatches,'note':'Chỉ ca đã chốt và đối soát khớp; ca mismatch bị loại khỏi KPI, vẫn hiện cảnh báo. Không cộng ca nhập với mô phỏng. Một ngày có thể có nhiều ca thử, tổng ca không phải doanh thu duy nhất theo ngày/quầy. Stockout ở đây = tồn cuối ca bằng 0, chưa phải thời lượng hết hàng. Lost sales thật chưa quan sát được.'}

    def sync_alerts(self,scope,alerts):
        now=utcnow();activeids=set()
        with self.store.connect() as db:
            for alert in alerts:
                aid=digest({'scope':scope,'code':alert['code']});activeids.add(aid);evidence=json.dumps(alert['evidence'],sort_keys=True,allow_nan=False)
                fingerprint=digest(alert['evidence']);previous=db.execute('SELECT * FROM monitoring_alerts WHERE id=?',(aid,)).fetchone()
                reset=previous is None or not previous['active'] or previous['evidence_hash']!=fingerprint
                if previous is None:
                    db.execute('INSERT INTO monitoring_alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (aid,scope,alert['code'],alert['severity'],alert['title'],alert['message'],evidence,fingerprint,1,None,None,None,now,now,None))
                else:
                    db.execute('UPDATE monitoring_alerts SET severity=?,title=?,message=?,evidence=?,evidence_hash=?,active=1,last_seen=?,cleared_at=NULL,ack_by=?,ack_at=?,ack_note=? WHERE id=?',
                               (alert['severity'],alert['title'],alert['message'],evidence,fingerprint,now,None if reset else previous['ack_by'],None if reset else previous['ack_at'],None if reset else previous['ack_note'],aid))
            for row in db.execute('SELECT id FROM monitoring_alerts WHERE scope=? AND active=1',(scope,)).fetchall():
                if row['id'] not in activeids:db.execute('UPDATE monitoring_alerts SET active=0,cleared_at=? WHERE id=?',(now,row['id']))
            rows=db.execute('SELECT * FROM monitoring_alerts WHERE scope=? ORDER BY active DESC,last_seen DESC LIMIT 100',(scope,)).fetchall()
        return [{**dict(r),'evidence':json.loads(r['evidence'])} for r in rows]

    def acknowledge(self,aid,evidence_hash,note):
        if not 3<=len(note.strip())<=500:raise ValueError('Cần ghi chú tiếp nhận 3–500 ký tự.')
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM monitoring_alerts WHERE id=?',(aid,)).fetchone()
            if not row or not row['active'] or row['evidence_hash']!=evidence_hash:raise ValueError('Cảnh báo đã đổi hoặc đã hết; tải lại trước khi tiếp nhận.')
            db.execute('UPDATE monitoring_alerts SET ack_by=?,ack_at=?,ack_note=? WHERE id=?',(actor.get()['username'],utcnow(),note.strip(),aid))
            self.workflow.safety.audit(db,None,'MONITORING_ALERT_ACK',{'alert_id':aid,'evidence_hash':evidence_hash,'note':note.strip()})
        return {'acknowledged':True,'note':'Tiếp nhận không đồng nghĩa đã hết điều kiện cảnh báo; không đổi mode AI.'}

    def sandbox(self):
        # Separate demonstration dataset. No session, model, learning or price is modified.
        self.engine.require_integrity()
        if self.engine.manifest.get('parent'):raise ValueError('Bộ minh họa này dùng model V4 đã khóa; model đang chọn đã học mới. Chọn ca dùng V4 đã khóa để minh họa.')
        visible=dict(self.simulator.seed);rows=[];sid='monitor-demo-'+uuid.uuid4().hex
        dates=sorted(d for d in self.simulator.calendar if d>='2022-05-01')[:28]
        for index,day in enumerate(dates):
            weather=self.simulator.calendar[day];plans=self.engine.plan(day,self.simulator.history_before(day),weather,self.simulator.outcomes_before(day))
            actual=self.simulator.evaluation_counts(day,self.simulator.version)
            for p in plans:
                value=int(round(actual[p['sku']]*(2.5 if index>=21 else 1.0)))
                rows.append({'session_id':sid,'day':day,'sku':p['sku'],'model_version':self.engine.version,'origin':'AI_M2',
                             'target_kind':'controlled_synthetic_demand','target_note':'Minh họa cô lập: lượt mua synthetic; từ ngày 22 tiêm shock minh họa 2.5x vào bản sao đánh giá sau khi đã dự báo.',
                             'prediction':p['forecast'],'actual':value,'features':{f:(p['features'].get(f)*2.5 if index>=21 and f in ['sold_calendar_lag1','sold_calendar_lag7','sold_last7_observed_mean'] else p['features'].get(f)) for f in FEATURES},
                             'weekday':weather['weekday_iso'],'is_holiday':weather['is_public_holiday'],'rain_mm':weather['forecast_rain_mm_previous_day1'],
                             'stockout':False,'source_mode':'sandbox','is_synthetic':True})
            # Only completed synthetic days become history for later demonstration predictions.
            for r in rows[-len(plans):]:visible[(day,r['sku'])]=r['actual']
        payload={'id':sid,'created':utcnow(),'model_version':self.engine.version,'rows':rows,'label':'Minh họa drift cô lập · 28 ngày · shock nhu cầu 2.5x',
                 'model_hashes':self.engine.manifest['native_model_hashes'],'policy':'evaluation_only_no_workflow_mutation',
                 'demo_thresholds':{'psi_threshold':.2,'performance_delta_pp':5.,'calibration_note':'Ngưỡng minh họa cố ý để trình diễn; chưa hiệu chỉnh, không phải SLA.'}}
        with self.store.connect() as db:
            db.execute('INSERT INTO monitoring_sandboxes VALUES (?,?,?)',(sid,json.dumps(payload,allow_nan=False),payload['created']))
            self.workflow.safety.audit(db,None,'MONITORING_SANDBOX_CREATED',{'id':sid,'rows':len(rows),'model':self.engine.version,'scenario':payload['label']})
        return {k:v for k,v in payload.items() if k!='rows'}

    def sandboxes(self):
        with self.store.connect() as db:rows=db.execute('SELECT payload FROM monitoring_sandboxes ORDER BY created DESC LIMIT 10').fetchall()
        return [{k:v for k,v in json.loads(r['payload']).items() if k!='rows'} for r in rows]

    def snapshot(self,sid,source='runtime',sandbox_id='',date_from='',date_to='',mode='',sku='',model_version=''):
        started=time.perf_counter();current=self.store.get(sid)
        for d in [date_from,date_to]:
            if d:
                try:
                    if datetime.strptime(d,'%Y-%m-%d').strftime('%Y-%m-%d')!=d:raise ValueError('noncanonical date')
                except ValueError:raise ValueError('Bộ lọc ngày phải có dạng YYYY-MM-DD.')
        if date_from and date_to and date_from>date_to:raise ValueError('Ngày bắt đầu phải trước ngày kết thúc.')
        if mode not in ['','simulation','live']:raise ValueError('Chế độ lọc không hợp lệ.')
        if sku and sku not in self.engine.master:raise ValueError('SKU không hợp lệ.')
        if source not in ['runtime','sandbox']:raise ValueError('Nguồn giám sát không hợp lệ.')
        if source=='runtime':sandbox_id=''
        def in_range(day):return (not date_from or day>=date_from) and (not date_to or day<=date_to)
        where=['1=1'];args=[]
        if date_from:where.append("json_extract(state,'$.day')>=?");args.append(date_from)
        if date_to:where.append("json_extract(state,'$.day')<=?");args.append(date_to)
        if mode:where.append("json_extract(state,'$.mode')=?");args.append(mode)
        if model_version:where.append("json_extract(state,'$.model_version')=?");args.append(model_version)
        with self.store.connect() as db:
            states=[json.loads(r['state']) for r in db.execute('SELECT state FROM sessions WHERE '+' AND '.join(where)+' ORDER BY rowid DESC LIMIT 501',args)]
            imports=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM imports ORDER BY rowid DESC LIMIT 1000')]
            incidents=[dict(r) for r in db.execute('SELECT sid,kind,status FROM incidents')]
        truncated=len(states)>500;states=states[:500]
        selected_model=model_version or current['model_version'];engine_error=None
        try:
            selected_engine=self.workflow.version_engine(selected_model)
            selected_engine.require_integrity()
        except (ValueError,OSError) as exc:
            engine_error=str(exc);selected_engine=None
        feature_rows=[];evaluations=[];unevaluated_closed=0
        if source=='sandbox':
            if not sandbox_id:raise ValueError('Chọn hoặc tạo bộ minh họa giám sát trước.')
            with self.store.connect() as db:r=db.execute('SELECT payload FROM monitoring_sandboxes WHERE id=?',(sandbox_id,)).fetchone()
            if not r:raise ValueError('Không tìm thấy bộ minh họa.')
            sandbox=json.loads(r['payload'])
            evaluations=[r for r in sandbox['rows'] if in_range(r['day']) and (not sku or r['sku']==sku) and (not model_version or r['model_version']==model_version)]
            feature_rows=evaluations
            config={**self.settings(),**sandbox['demo_thresholds']};source_label=sandbox['label']
        else:
            config=self.settings();source_label='Các ca local đã lưu; metric accuracy chỉ từ ca đã chốt.'
            for s in states:
                for p in s['plan']:
                    if not sku or sku==p['sku']:feature_rows.append({'day':s['day'],'sku':p['sku'],'model_version':s['model_version'],'origin':p.get('prediction_origin',s.get('prediction_origin','LEGACY_UNKNOWN')),'features':p.get('features',{})})
                result=self.closed_evaluation(s)
                if s['phase']=='closed' and not result:unevaluated_closed+=1
                evaluations.extend(r for r in result if not sku or r['sku']==sku)
        accuracy=self.accuracy(evaluations)
        drift=self.drift(feature_rows,evaluations,selected_engine,config,sku) if selected_engine else {'reference':{'available':False,'reason':engine_error},'data':[],'performance':[],'note':'Không tính drift từ model/reference không xác minh được.'}
        # SKU filters affect numeric safety/business slices; workflow counts remain per session.
        slices=states
        if sku:
            slices=[{**s,'products':{k:v for k,v in s['products'].items() if k==sku},'ledger':[t for t in s['ledger'] if t['sku']==sku],
                     'decisions':[{**d,'rows':[r for r in d.get('rows',[]) if r['sku']==sku]} for d in s['decisions']],
                     'pending':{**s['pending'],'rows':[r for r in s['pending'].get('rows',[]) if r['sku']==sku]} if s.get('pending') else None} for s in states]
        safety=self.safety(slices);ops=self.operations(states);ids={s['id'] for s in states}
        safety['hard_rule_incidents']=sum(i['sid'] in ids and i['kind']=='HARD_RULE_BLOCK' for i in incidents)
        safety['scope']='Các ca vận hành theo bộ lọc, không phải dữ liệu sandbox.'
        business=self.business(slices) if source=='runtime' else {'groups':[],'daily':[],'mismatches':[],'note':'Sandbox không tạo giao dịch/tồn kho; không bịa KPI kinh doanh cho bộ minh họa drift.'}
        q=current.get('data_quality',{});recentimports=[p for p in imports if in_range(p.get('day',''))]
        errors=[e for p in recentimports for e in p.get('errors',[])]
        dq={'scope_session':sid,'status':q.get('status','LEGACY'),'history':[r for r in q.get('history',[]) if not sku or r['sku']==sku],
            'weather':q.get('weather',{}),'sales':sales_quality(current),'prediction_as_of':q.get('prediction_as_of'),'feature_snapshot_id':current.get('feature_snapshot_id'),
            'imports':{'scanned':len(recentimports),'scan_limit':1000,'valid_previews':sum(p.get('valid',False) for p in recentimports),
                       'confirmed':sum(bool(p.get('confirmed_session')) for p in recentimports),'quarantined':sum(not p.get('valid',False) for p in recentimports),
                       'blocked_confirmations':sum(p.get('status')=='BLOCKED' for p in recentimports),'row_errors':len(errors),
                       'duplicate_errors':sum('trùng' in e.get('message','').lower() for e in errors),
                       'accepted_history_rows':sum(len(p.get('history',[])) for p in recentimports if p.get('confirmed_session')),
                       'accepted_transaction_rows':sum(len(p.get('transactions',[])) for p in recentimports if p.get('confirmed_session'))},
            'note':'DQ của ca đang chọn; thống kê nhập theo ngày mục tiêu. Dữ liệu năm 2022 so với đồng hồ ca, không so với hôm nay.'}
        if current['phase']=='closed':dq['sales']={**dq['sales'],'status':'CLOSED','message':'Ca đã chốt; không đánh giá gate feed realtime.'}
        relevant_incidents=[i for i in incidents if i['sid'] in [sid,'__system__'] and i['status']!='resolved']
        alerts=[]
        def alert(code,severity,title,message,evidence):alerts.append({'code':code,'severity':severity,'title':title,'message':message,'evidence':evidence})
        if engine_error:alert('ARTIFACT','critical','Model không vượt kiểm tra hash',engine_error,{'model':selected_model,'session_id':sid})
        if any(r['status']=='BLOCK' for r in dq['history']):alert('HISTORY_STALE','critical','Lịch sử không đủ mới','Kiểm tra nguồn dữ liệu trước khi dùng dự báo.',{'session_id':sid,'skus':[r['sku'] for r in dq['history'] if r['status']=='BLOCK']})
        if current['minute']>=1170 and current['phase']!='closed' and dq['sales']['status']=='BLOCK':alert('FEED_STALE','review','Nguồn bán/tồn đang bị chặn','GD6 vẫn thực thi gate; dashboard không tự sửa tồn.',{'session_id':sid,'age_minutes':dq['sales']['age_minutes']})
        if relevant_incidents:alert('INCIDENT_OPEN','review','Có sự cố chưa đóng','Mở An toàn & sự cố để xử lý theo GD6.',{'session_id':sid,'count':len(relevant_incidents),'kinds':sorted({i['kind'] for i in relevant_incidents})})
        if safety['applied_violations']:alert('M1_APPLIED_RULE','critical','Phát hiện vi phạm ở quyết định đã áp dụng','Phân biệt với đề xuất bị chặn; cần kiểm tra ledger và incident.',{'count':safety['applied_violations'],'rows':safety['violations'][:10]})
        if business['mismatches']:alert('RECONCILIATION','critical','Sổ ca không khớp đối soát','Không coi báo cáo tổng là đã được nghiệm thu; kiểm tra dữ liệu gốc.',{'rows':business['mismatches'][:20]})
        if ops['http']['http_5xx']:alert('HTTP_5XX','review','API có lỗi 5xx trong 24 giờ','Xem route và request ID ở tab Vận hành.',{'count':ops['http']['http_5xx']})
        if ops['job_failures']:alert('JOB_FAILURE','review','Có đồng hồ/job dừng do lỗi','Đây là lỗi thực tế đã lưu, không đồng nhất với ứng viên model không đạt.',{'jobs':ops['job_failures']})
        for g in accuracy:
            if g['origin']=='AI_M2' and g['target_kind']!='observed_sales_proxy' and g['metrics']['n']>=config['min_rows'] and g['day_count']>=config['min_days'] and g['metrics']['wape_pct'] is not None and g['metrics']['wape_pct']>config['academic_wape_goal_pct']:
                alert('WAPE_'+g['model_version']+'_'+g['target_kind'],'review','WAPE vượt mục tiêu học thuật 18%','Chỉ yêu cầu xem xét; không phải SLA và không tự rollback model.',{'source':source,'model':g['model_version'],'target_kind':g['target_kind'],'wape_pct':g['metrics']['wape_pct'],'n':g['metrics']['n']})
        drifting=[r for r in drift['data'] if r['status']=='REVIEW']
        if drifting:alert('DATA_DRIFT','review','Phân phối feature vượt ngưỡng local','Ngưỡng cần hiệu chỉnh; PSI/KS không chứng minh model đã hỏng.',{'source':source,'features':[{'feature':r['feature'],'psi':r['psi']} for r in drifting],'threshold':config['psi_threshold']})
        worsening=[r for r in drift['performance'] if r['status']=='REVIEW']
        if worsening:alert('PERFORMANCE_DRIFT','review','Sai số tăng giữa hai cửa sổ','So cùng model/origin/target, không trộn bán quan sát với nhu cầu gốc.',{'source':source,'windows':worsening,'threshold_pp':config['performance_delta_pp']})
        for b in business['groups']:
            if b['stockout_sku_rows'] or (b['lost_simulator_only'] or 0)>0:alert('SERVICE_GUARDRAIL_'+b['mode'],'review','Cần xem nguy cơ hết hàng / mất lượt bán','Không chỉ tối ưu waste; lost sales của ca live chưa biết.',{'mode':b['mode'],'stockout_sku_rows':b['stockout_sku_rows'],'lost_simulator_only':b['lost_simulator_only']})
        scope=digest({'session_id':sid,'source':source,'sandbox_id':sandbox_id,'date_from':date_from,'date_to':date_to,'mode':mode,'sku':sku,'model':selected_model})
        alerts=self.sync_alerts(scope,alerts)
        return {'generated_at':utcnow(),'scope':{'session_id':sid,'source':source,'source_label':source_label,'sandbox_id':sandbox_id,'date_from':date_from,'date_to':date_to,'mode':mode,'sku':sku,
                       'selected_model':selected_model,'session_count':len(states),'closed_sessions':sum(s['phase']=='closed' for s in states),'session_limit':500,'truncated':truncated,'unevaluated_closed_sessions':unevaluated_closed},
                'overview':{'status':'BLOCK' if any(a['active'] and a['severity']=='critical' for a in alerts) else 'REVIEW' if any(a['active'] for a in alerts) else 'OBSERVING',
                            'active_alerts':sum(a['active'] for a in alerts),'model_integrity':engine_error is None,'closed_metric_rows':len(evaluations),'api_5xx_24h':ops['http']['http_5xx']},
                'data_quality':dq,'accuracy':accuracy,'drift':drift,'m1_safety':safety,'operations':ops,'business':business,'alerts':alerts,'config':config,
                'models':sorted({s['model_version'] for s in states}|{current['model_version']}),'sandboxes':self.sandboxes(),
                'limits':['Mục tiêu WAPE 18% là học thuật, ngưỡng drift chưa được nghiệm thu production.','Không tự tắt AI, tạo incident, retrain hay rollback từ tín hiệu drift.',
                          'Ca live chỉ có observed-sales proxy; không tự suy ra lost sales thật.','Sandbox và runtime là hai nguồn riêng; API/DQ vẫn ghi rõ nguồn workspace.'],
                'calculation_ms':round((time.perf_counter()-started)*1000,2)}

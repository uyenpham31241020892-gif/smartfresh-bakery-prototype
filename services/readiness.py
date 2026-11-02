"""Local demo release verification; a GO here never authorizes production deployment."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import sqlite3
from datetime import datetime, timezone
from .engine import ROOT
from .evaluation import reconcile

SCHEMA_CONTRACT={'sessions':['id','state','updated'],'audit':['id','session_id','action','detail','created'],'imports':['id','payload'],'local_users':['id','username','password_hash','salt','role'],'login_sessions':['token_hash','user_id','expires'],'learning_runs':['id','report'],'model_active':['id','version']}

PACKAGES=['fastapi','uvicorn','numpy','pandas','joblib','scikit-learn','openpyxl','python-multipart']

def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def release_check(root=ROOT):
    root=Path(root);path=root/'release_manifest.json'
    if not path.exists():return {'status':'FAIL','reason':'Thiếu release_manifest.json; chưa xác minh bản bàn giao.','manifest':None,'mismatches':[]}
    try:
        m=json.loads(path.read_text());bad=[]
        for name,expected in m['files'].items():
            p=(root/name).resolve()
            if not p.is_relative_to(root.resolve()) or not p.is_file() or hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n') if name.endswith('.cmd') else p.read_bytes()).hexdigest()!=expected:bad.append(name)
        if not m['files']:raise ValueError('empty release')
        return {'status':'FAIL' if bad else 'PASS','reason':'Có file thiếu/khác checksum.' if bad else 'Các file phát hành khớp checksum.','manifest':m,'mismatches':bad}
    except (ValueError,OSError,KeyError,TypeError):return {'status':'FAIL','reason':'Release manifest không đọc được.','manifest':None,'mismatches':[]}


def health(store,learning):
    result={'ok':False,'database':False,'artifact_integrity':False,'model':None,'dependencies':{},'timezone':'Asia/Ho_Chi_Minh'}
    try:
        with store.connect() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            result['database']=db.execute('PRAGMA quick_check').fetchone()[0]=='ok' and set(SCHEMA_CONTRACT)<=tables
            if result['database']:result['database']=all(set(columns)<={r[1] for r in db.execute('PRAGMA table_info('+table+')')} for table,columns in SCHEMA_CONTRACT.items())
    except (sqlite3.Error,OSError):pass
    try:
        e=learning.active();result['model']=e.version;e.require_integrity();e.reload_if_needed();result['artifact_integrity']=True
    except Exception:pass
    for name in PACKAGES:
        try:result['dependencies'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:result['dependencies'][name]=None
    result['ok']=result['database'] and result['artifact_integrity'] and all(result['dependencies'].values())
    return result


class Readiness:
    def __init__(self,store,learning,workflow,root=ROOT):self.store,self.learning,self.workflow,self.root=store,learning,workflow,Path(root)
    def snapshot(self,sid):
        s=self.store.get(sid);h=health(self.store,self.learning);r=release_check(self.root);a=reconcile(s)
        conditions=[]
        def check(id,label,ok,evidence):conditions.append({'id':id,'label':label,'status':'PENDING' if ok is None else 'PASS' if ok else 'FAIL','evidence':evidence})
        check('G01_DB','Database đọc/ghi và quick_check',h['database'],'SQLite transaction + quick_check')
        check('G01_MODEL','Artifact model active nguyên vẹn',h['artifact_integrity'],h['model'])
        try:
            pinned=self.learning.resolve(s['model_version']);pinned.require_integrity()
            pinned_ok=pinned.manifest['native_model_hashes']==s.get('model_hashes')
        except Exception:pinned_ok=False
        check('G01_PINNED','Model ghim của ca nguyên vẹn',pinned_ok,s['model_version'])
        check('G01_DEPS','Dependencies hiện có',all(h['dependencies'].values()),h['dependencies'])
        check('G07_RELEASE','Source/model/data khớp release',r['status']=='PASS',{'reason':r['reason'],'mismatches':r['mismatches']})
        check('F_RECONCILIATION','Ca đã đóng và đối soát khớp',a['publishable'] if s['phase']=='closed' or a['errors'] else None,{'status':a['status'],'errors':a['errors'],'state_sha256':a['state_sha256']})
        with self.store.connect() as db:
            receipt=db.execute("SELECT payload FROM reconciliation_receipts WHERE session_id=? AND id=?",(sid,a['state_sha256'])).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='reconciliation_receipts'").fetchone() else None
            qa_path=self.root/'docs/V4_QA_RESULTS.json'
        check('F_RECEIPT','Manager đã xác nhận snapshot đối soát',True if receipt else None,json.loads(receipt['payload']).get('actor') if receipt else 'Chưa có biên bản hiện hành.')
        supply=[p.get('supply',{}) for p in s['plan']]
        feasible=all(p.get('capacity_feasible',False) for p in supply) and all(p.get('approved',p['prepared'])<=p.get('supply',{}).get('capacity',0) for p in s['plan'])
        check('S_CAPACITY','Kế hoạch đủ công suất theo kịch bản đã khai báo',feasible,supply)
        observed=bool(s['products']) and all('stock_at_2130' in p for p in s['products'].values())
        service=all(p.get('stock_at_2130',0)>0 and p.get('first_stockout_minute',1320)>=1290 for p in s['products'].values())
        early_out=any(p.get('first_stockout_minute',1320)<1290 for p in s['products'].values())
        check('S_2130','Từng SKU còn hàng đến 21:30',False if early_out else service if observed else None,{sku:{'stock_at_2130':p.get('stock_at_2130'),'first_stockout_minute':p.get('first_stockout_minute')} for sku,p in s['products'].items()})
        incidents=[i for i in self.workflow.safety.incidents(sid) if i['status']!='resolved']
        incidents=list({i['id']:i for i in incidents}.values())
        check('E_INCIDENT','Không có sự cố mở ở ca/hệ thống',not incidents,[{'id':i['id'],'kind':i['kind'],'status':i['status']} for i in incidents])
        try:
            qa=json.loads(qa_path.read_text());expected=(r['manifest'] or {}).get('release_id')
            qa_ok=qa.get('release_id')==expected and bool(expected) and qa.get('failed')==0 and qa.get('pytest_exit_code')==0 and qa.get('passed',0)>0 and qa.get('e2e',{}).get('passed') is True
        except (OSError,ValueError):qa={};qa_ok=False
        check('G06_QA','Bằng chứng QA đúng release',qa_ok,{k:qa.get(k) for k in ['release_id','passed','failed','created']})
        return {'scope':'LOCAL_PROTOTYPE_DEMO','decision':'NO_GO' if any(c['status']=='FAIL' for c in conditions) else 'PENDING' if any(c['status']=='PENDING' for c in conditions) else 'GO','production_decision':'NOT_ASSESSED','checked_at':datetime.now(timezone.utc).isoformat(),'session_id':sid,'conditions':conditions,'release_id':(r['manifest'] or {}).get('release_id'),'notes':['GO chỉ áp dụng demo local của ca đang chọn, không phải cho phép triển khai AEON/Internet.','GitHub workflow được bàn giao; chưa có bằng chứng job chạy trên repository của bạn.','BigQuery adapter chưa tích hợp: cần quyền truy cập, project và hợp đồng dữ liệu thực.','Backup/restore là công cụ offline; cần dừng server và diễn tập trên bản sao trước phục hồi.','Release manifest là checksum phát hiện thay đổi, không phải chữ ký số hay bằng chứng chống kẻ có quyền sửa toàn bộ project.']}

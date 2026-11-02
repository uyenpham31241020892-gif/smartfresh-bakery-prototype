"""SmartFresh local inference, approvals, uploads and OpenAI tools."""
import os
for _thread_var in ["OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"]:os.environ[_thread_var]="1"
import csv
import io
import json
import os
from pathlib import Path
import sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import uuid
import zipfile
import time
from contextlib import asynccontextmanager

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import pandas as pd
from services.engine import DATA, Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow
from services.ingestion import MAX_BYTES, inspect
from services.quality import sales_quality, POLICY
from services.workflow import now
from services.identity import Identity, actor, AccessError, request_trace
from services.safety import GuardError
from services.monitoring import Monitoring
from services.assistant import Assistant
from services.learning import Learning, DAILY, PROMO, demo_data
from services.evaluation import Evaluation, reconcile
from services.realtime import Realtime
from services.readiness import Readiness, health as detailed_health
from services.http_limits import BodySizeLimit
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

engine = Engine(allow_degraded=True)
simulator = Simulator(engine)
store = Store(os.environ.get('SMARTFRESH_DB') or ROOT/'runtime/smartfresh_v4.sqlite3')
identity = Identity(store)
workflow = Workflow(engine, simulator, store)
learning = Learning(store, engine, os.environ.get('SMARTFRESH_LEARNING_DIR'))
workflow.active_engine = learning.active
workflow.version_engine = learning.resolve
workflow.observed_history = learning.history_before
workflow.observed_outcomes = learning.outcomes_before
assistant = Assistant()
from services.explanations import Explanations
explanations = Explanations()
realtime = Realtime(workflow,store)
if engine.artifact_error:
    workflow.safety.report('__system__','STARTUP_ARTIFACT',engine.artifact_error)


@asynccontextmanager
async def lifespan(application):
    Monitoring.recover_jobs(store)
    realtime.start()
    try:yield
    finally:realtime.stop()


app = FastAPI(title='SmartFresh Bakery', docs_url='/api/docs',lifespan=lifespan)
app.add_middleware(BodySizeLimit)
app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')


@app.middleware('http')
async def local_origin(request: Request, call_next):
    from urllib.parse import urlparse
    origin=request.headers.get('origin')
    if request.url.hostname not in ['127.0.0.1','localhost','testserver']:
        return JSONResponse({'error':'Chỉ phục vụ workspace loopback local.','code':'HOST_DENIED'},status_code=403)
    if request.method not in ['GET','HEAD'] and request.headers.get('sec-fetch-site')=='cross-site':
        return JSONResponse({'error':'Không nhận thao tác từ trang ngoài.','code':'ORIGIN_DENIED'},status_code=403)
    if request.method not in ['GET','HEAD'] and origin and (urlparse(origin).netloc!=request.url.netloc or urlparse(origin).scheme!=request.url.scheme):
        return JSONResponse({'error':'Chỉ nhận thao tác từ dashboard local.','code':'ORIGIN_DENIED'},status_code=403)
    path=request.url.path
    if path in ['/api/learning/train','/api/learning/demo'] or path.startswith('/api/learning/') and path.endswith('/promote') or path.startswith('/api/learning/') and path.endswith('/holdout'):
        return JSONResponse({'error':'V4 đã khóa: không train/tune hay promotion model mới trong app.'},status_code=409)
    public=path in ['/api/health','/api/auth/status','/api/auth/login','/api/auth/setup']
    user=None
    if path.startswith('/api/') and not public:
        user=identity.authenticate(request.cookies.get('smartfresh_auth'))
        if not user:return JSONResponse({'error':'Cần đăng nhập để dùng workspace.','code':'AUTH_REQUIRED'},status_code=401)
        try:identity.authorize(user,path,request.method)
        except AccessError as exc:
            with store.connect() as db:
                db.execute('INSERT INTO audit(session_id,action,detail) VALUES (NULL,?,?)',('ACCESS_DENIED',json.dumps({'actor':user,'path':path,'method':request.method})))
            return JSONResponse({'error':str(exc),'code':'ROLE_DENIED'},status_code=403)
    token=actor.set(user or {'id':'anonymous','username':'anonymous','role':'anonymous'})
    try:
        response=await call_next(request)
        if user and request.method not in ['GET','HEAD']:
            with store.connect() as db:
                db.execute('INSERT INTO audit(session_id,action,detail) VALUES (NULL,?,?)',('API_ACTION',json.dumps({'actor':user,'path':path,'status':response.status_code,'request_id':request_trace.get(),'at':now()})))
        return response
    finally:actor.reset(token)


@app.middleware('http')
async def monitoring_telemetry(request: Request, call_next):
    started=time.perf_counter();status=500;request_id=uuid.uuid4().hex
    request.state.request_id=request_id;trace_token=request_trace.set(request_id)
    try:
        try:response=await call_next(request)
        except Exception as exc:
            import logging
            logging.getLogger('smartfresh.api').error('Unhandled %s request_id=%s',type(exc).__name__,request_id)
            response=JSONResponse({'error':'Lỗi nội bộ; dùng Request ID để đối chiếu nhật ký.','code':'INTERNAL_ERROR'},status_code=500)
        status=response.status_code
        if status>=400 and 'application/json' in response.headers.get('content-type',''):
            chunks=b''.join([part async for part in response.body_iterator]) if hasattr(response,'body_iterator') else response.body
            try:payload=json.loads(chunks)
            except ValueError:payload={}
            health_fields={k:v for k,v in payload.items() if k in ['ok','database','artifact_integrity','model','dependencies','timezone']} if request.url.path=='/api/health' else {}
            payload={**health_fields,'error':payload.get('error','Yêu cầu không được thực hiện.'),'code':payload.get('code',{400:'INVALID_REQUEST',401:'AUTH_REQUIRED',403:'ACCESS_DENIED',404:'NOT_FOUND',405:'METHOD_NOT_ALLOWED',413:'PAYLOAD_TOO_LARGE',422:'VALIDATION_ERROR',503:'NOT_READY'}.get(status,'REQUEST_FAILED')),'request_id':request_id,**({'details':payload['details']} if 'details' in payload else {})}
            headers={k:v for k,v in response.headers.items() if k.lower() not in ['content-length','content-type']}
            response=JSONResponse(payload,status_code=status,headers=headers)
        response.headers['X-Request-ID']=request_id
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response
    finally:
        request_trace.reset(trace_token)
        if request.url.path.startswith('/api/') and not (request.method=='GET' and request.url.path=='/api/monitoring' and status<400):
            route=getattr(request.scope.get('route'),'path','__unmatched__')
            try:
                await run_in_threadpool(Monitoring.record_http,store,route,request.method,status,(time.perf_counter()-started)*1000,request_id)
            except Exception:
                # Observation must never turn a successful business action into a failed response.
                import logging
                logging.getLogger('smartfresh.monitoring').exception('Telemetry write failed; workflow response preserved')


@app.exception_handler(AccessError)
async def access_error(request,exc):
    return JSONResponse({'error':str(exc),'code':'ACCESS_DENIED'},status_code=403)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=400)


@app.exception_handler(zipfile.BadZipFile)
async def bad_archive(request, exc):
    return JSONResponse({'error': 'Tệp ZIP/Excel bị hỏng hoặc không đúng định dạng.'}, status_code=400)


@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse({'error':'Dữ liệu yêu cầu không đúng schema.','code':'VALIDATION_ERROR','details':[{'field':'.'.join(map(str,e['loc'])),'type':e['type']} for e in exc.errors()]},status_code=422)

@app.exception_handler(StarletteHTTPException)
async def http_error(request,exc):
    return JSONResponse({'error':'Không tìm thấy tài nguyên.' if exc.status_code==404 else 'Yêu cầu HTTP không hợp lệ.','code':{404:'NOT_FOUND',405:'METHOD_NOT_ALLOWED'}.get(exc.status_code,'HTTP_ERROR')},status_code=exc.status_code)

@app.get('/api/trace/{rid}')
def trace_request(rid:str):
    if len(rid)!=32 or any(c not in '0123456789abcdef' for c in rid):raise ValueError('Request ID không hợp lệ.')
    with store.connect() as db:
        events=[dict(r) for r in db.execute("SELECT id,session_id,action,detail,created FROM audit WHERE json_extract(detail,'$.request_id')=? ORDER BY id",(rid,))]
        requests=[dict(r) for r in db.execute('SELECT route,method,status,elapsed_ms,created FROM monitoring_http WHERE request_id=?',(rid,))] if db.execute("SELECT 1 FROM sqlite_master WHERE name='monitoring_http'").fetchone() else []
        sales=[{'session_id':r['id'],'transaction':json.loads(r['value'])} for r in db.execute("SELECT s.id,j.value FROM sessions s,json_each(s.state,'$.ledger') j WHERE json_extract(j.value,'$.request_id')=?",(rid,))]
    return {'request_id':rid,'events':events,'requests':requests,'transactions':sales,'note':'Chỉ dữ liệu local còn lưu. Giao dịch/nhật ký trước GD9 có thể chưa có Request ID.'}

@app.get('/api/readiness')
def deployment_readiness(session_id:str):
    return Readiness(store,learning,workflow).snapshot(session_id)

@app.get('/')
def home():
    return FileResponse(ROOT / 'web/index.html')


class Credentials(BaseModel):
    username: str = Field(min_length=3,max_length=40)
    password: str = Field(min_length=1,max_length=128)


class NewUser(Credentials):
    role: str = 'staff'


@app.get('/api/auth/status')
def auth_status(request: Request):
    return {'setup_needed':identity.setup_needed(),'user':identity.authenticate(request.cookies.get('smartfresh_auth'))}


def auth_response(token,user):
    r=JSONResponse({'user':user})
    r.set_cookie('smartfresh_auth',token,httponly=True,samesite='strict',max_age=8*3600,path='/')
    return r


@app.post('/api/auth/setup')
def setup(body:Credentials):
    identity.create(body.username,body.password,'staff',bootstrap=True)
    token,user=identity.login(body.username,body.password)
    return auth_response(token,user)


@app.post('/api/auth/login')
def login(body:Credentials):
    token,user=identity.login(body.username,body.password)
    return auth_response(token,user)


@app.post('/api/auth/logout')
def logout(request:Request):
    identity.logout(request.cookies.get('smartfresh_auth'))
    r=JSONResponse({'logged_out':True});r.delete_cookie('smartfresh_auth',path='/');return r


@app.post('/api/auth/users')
def add_user(body:NewUser):
    return identity.create(body.username,body.password,body.role)


@app.get('/api/auth/users')
def users():
    if actor.get()['role']!='manager':raise AccessError('Chỉ Manager xem danh sách tài khoản.')
    with store.connect() as db:return [dict(r) for r in db.execute('SELECT id,username,role FROM local_users ORDER BY username')]


class SafetyRequest(BaseModel):
    session_id: str
    revision: int
    action: str
    reason: str = Field(min_length=3,max_length=500)
    value: str = ''


@app.get('/api/safety')
def safety_status(session_id:str):
    s=store.get(session_id)
    e=workflow.version_engine(s['model_version'])
    try:e.require_integrity();integrity={'passed':True,'message':'Checksum khớp manifest đã nạp.'}
    except (ValueError,OSError) as exc:
        workflow.safety.report(s['id'],'ARTIFACT_MISMATCH',str(exc))
        integrity={'passed':False,'message':str(exc)}
    return {'control':workflow.safety.control(session_id),'incidents':workflow.safety.incidents(session_id),
            'integrity':integrity,'user':actor.get(),'roles':{'manager':'Duyệt, áp giá, chế độ, sự cố và tài khoản','staff':'Nhập dữ liệu, vận hành ca; không duyệt giá/sản lượng','viewer':'Chỉ xem'},
            'notice':'RBAC và incident local; chưa có SSO/POS. Diễn tập chỉ trên ca mô phỏng.'}


@app.post('/api/safety/control')
def safety_control(body:SafetyRequest):
    if body.action=='mode':
        result=workflow.safety.set_mode(body.session_id,body.value,body.reason,body.revision)
        if result['phase']=='plan_pending':result=workflow.mutate(result['id'],result['revision'],'replan',{'reason':body.reason})
        elif result['products'] and 1170<=result['minute']<1320:
            result=workflow.mutate(result['id'],result['revision'],'refresh_price',{'reason':body.reason})
    elif body.action=='drill':
        result=workflow.safety.fault(body.session_id,body.value,body.reason,body.revision)
        if body.value=='m2_error':result=workflow.mutate(result['id'],result['revision'],'replan',{'reason':body.reason})
        elif body.value in ['m1_error','stale_stock'] and result['minute']>=1170:
            result=workflow.mutate(result['id'],result['revision'],'refresh_price',{'reason':body.reason})
    elif body.action=='rollback_drill':
        s=store.get(body.session_id)
        if s['revision']!=body.revision:raise ValueError('Dữ liệu đã thay đổi; tải lại.')
        if s['mode']!='simulation':raise ValueError('Chỉ diễn tập rollback trên ca mô phỏng.')
        engine.require_integrity();engine.reload_if_needed()
        h={(r['date'],r['sku']):r['sold'] for r in s['input_history']}
        plans=engine.plan(s['day'],h,s['weather'])
        if not all(p['prepared']%4==0 and p['prepared']>=p['floor'] for p in plans):raise GuardError('Rollback smoke test thất bại.')
        j=max(0,min(4,sum(s['minute']>=t for t in [1170,1200,1230,1260,1290])-1))
        from services.engine import LADDER,CAPS,FLOORS
        for p in plans:
            current=s['products'].get(p['sku'],{'stock':p['prepared'],'prepared':p['prepared'],'discount':0,'forecast':p['forecast']})
            r=engine.price(p['sku'],j,current['stock'],current['prepared'],current['discount'],0,0,current['forecast'],s['weather'],as_of=max(1170,min(1290,1170+30*((s['minute']-1170)//30))))
            if r['discount'] not in LADDER or not max(current['discount'],FLOORS[j])<=r['discount']<=CAPS[j]:raise GuardError('Rollback M1 smoke test thất bại.')
        receipt={'passed':True,'changed_active_model':False,'candidate':engine.version,'at':now(),
                 'steps':['Ghim ca và phiên bản hiện tại','Nạp bundle V4 đã khóa','Kiểm SHA256','Smoke test M2 batch/floor và M1 ladder/cap/floor','Lưu bằng chứng drill','Giữ nguyên active model; phục hồi thật cần Manager duyệt'],
                 'model_hashes':engine.manifest['native_model_hashes']}
        with store.connect() as db:workflow.safety.audit(db,s['id'],'ROLLBACK_DRILL',{'reason':body.reason,'receipt':receipt})
        return {'drill':receipt,'state':snapshot(s)}
    else:raise ValueError('Thao tác an toàn không hợp lệ.')
    return {'state':snapshot(result)}


class IncidentAction(BaseModel):
    action: str
    reason: str = Field(min_length=3,max_length=500)


@app.post('/api/safety/incidents/{iid}')
def incident_action(iid:str,body:IncidentAction):
    return workflow.safety.transition(iid,body.action,body.reason)


def monitoring_service(session_id=None):
    e=workflow.version_engine(store.get(session_id)['model_version']) if session_id else learning.active()
    return Monitoring(store,e,simulator,workflow)


@app.get('/api/monitoring')
def monitoring_dashboard(session_id:str,source:str='runtime',sandbox_id:str='',date_from:str='',date_to:str='',mode:str='',sku:str='',model_version:str=''):
    return monitoring_service(session_id).snapshot(session_id,source,sandbox_id,date_from,date_to,mode,sku,model_version)


class MonitoringDemo(BaseModel):
    session_id:str


@app.post('/api/monitoring/sandbox')
def monitoring_sandbox(body:MonitoringDemo):
    with Monitoring.job(store,'MONITORING_SANDBOX',body.session_id):
        return monitoring_service(body.session_id).sandbox()


class MonitoringConfig(BaseModel):
    expected_version:int
    psi_threshold:float | None = None
    performance_delta_pp:float | None = None
    calibration_note:str = Field(min_length=8,max_length=500)


@app.post('/api/monitoring/config')
def monitoring_config(body:MonitoringConfig):
    return monitoring_service().configure(body.model_dump())


class MonitoringAck(BaseModel):
    evidence_hash:str
    note:str = Field(min_length=3,max_length=500)


@app.post('/api/monitoring/alerts/{aid}/acknowledge')
def monitoring_acknowledge(aid:str,body:MonitoringAck):
    return monitoring_service().acknowledge(aid,body.evidence_hash,body.note)


@app.get('/api/health')
def health():
    result=detailed_health(store,learning)
    return JSONResponse(result,status_code=200 if result['ok'] else 503)


def evidence(s, sku):
    plan = next((p for p in s['plan'] if p['sku'] == sku), None)
    if plan is None:
        raise ValueError('SKU không hợp lệ.')
    current=s['pending'] or {}
    pricing = next((p for p in current.get('rows', [])+current.get('held_rows',[]) if p['sku'] == sku), None)
    if pricing is None and s['decisions']:
        last=s['decisions'][-1]
        pricing = next((p for p in last['rows']+last.get('held_rows',[]) if p['sku'] == sku), None)
    manifest = learning.resolve(s['model_version']).manifest
    return {'sku': sku, 'model_version': s['model_version'], 'session_id': s['id'], 'revision': s['revision'],
            'training': {'parent': manifest.get('parent'), 'component_retrained': manifest.get('learning_kind'),
                         'data_cutoff': manifest.get('trained_until', '2022-08-15'),
                         'source': 'provided_V4_locked_model_and_validation_inputs',
                         'review':engine.training_review},
            'm2': plan, 'm1': pricing, 'm2_origin':s.get('prediction_origin','LEGACY'),
            'm1_origin':(s.get('pending') or (s['decisions'][-1] if s['decisions'] else {})).get('origin','LEGACY'), 'explanation_type': 'Observed-state risk forecast and declared pricing policy; no causal uplift or SHAP claim'}


def snapshot(s):
    accounting=reconcile(s)
    products = list(s['products'].values())
    prepared = sum(p['prepared'] for p in products)
    sold = sum(p['sold'] for p in products)
    revenue = sum(p['revenue'] for p in products)
    from services.costs import estimate
    financial=estimate(s['products'],closed=s['phase']=='closed');cost=financial['preparation_cost']
    s = dict(s)
    s['live_products'] = []
    for sku,p in s['products'].items():
        tx=[t for t in s['ledger'] if t['sku']==sku]
        sales30=sum(t['qty'] for t in tx if s['minute']-30<=t['minute']<s['minute'])
        sales60=sum(t['qty'] for t in tx if s['minute']-60<=t['minute']<s['minute'])
        s['live_products'].append(dict(sku=sku,name=p['name'],prepared=p['prepared'],sold=p['sold'],stock=p['stock'],
            sales30=sales30,sales60=sales60,transactions=len(tx),revenue=p['revenue'],
            projected_stockout_minute=s['minute']+60*p['stock']/sales60 if sales60 else None,
            stock_at_2130=p.get('stock_at_2130'),first_stockout_minute=p.get('first_stockout_minute')))
    s['feed_status'] = dict(as_of_minute=s['minute'],revision=s['revision'],transaction_rows=len(s['ledger']),
                          cumulative_sold=sold,last_transaction_minute=max((t['minute'] for t in s['ledger']),default=None))
    s.pop('keys', None)
    s.pop('input_history', None)
    s.pop('input_outcomes',None)
    s['totals'] = {'prepared': prepared, 'sold': sold, 'stock': prepared - sold, 'revenue': revenue,
        'waste': prepared - sold if s['phase'] == 'closed' else None,
        'lost_simulator_only': sum(p['lost'] for p in products) if s['mode'] == 'simulation' else None,
        'cost_assumed': cost, 'contribution_before_overhead': financial['contribution_before_overhead'],
        'sell_through_pct': 100 * sold / prepared if prepared else 0,
        'proposed_prepared': sum(p['prepared'] for p in s['plan']), 'forecast': sum(p['forecast'] for p in s['plan'])}
    s['data_quality'] = {**s.get('data_quality', {'status':'LEGACY','message':'Ca cũ chưa có snapshot GD5; tạo ca mới để kiểm tra.'}), 'sales':sales_quality(s)}
    s['financial_estimate']=financial
    s['safety'] = {**workflow.safety.control(s['id']),'open_incidents':sum(i['status']!='resolved' for i in workflow.safety.incidents(s['id']))}
    s['ai'] = assistant.status()
    s['realtime']=realtime.status(s['id'])
    s['sales_feed']={'type':s.get('simulator_version') if s['mode']=='simulation' else 'manual_import',
                     'has_transactions':bool(s['ledger']),'missing':s['mode']=='live' and not s['ledger'] and not s.get('confirmed_zero_sales'),
                     'confirmed_zero':bool(s.get('confirmed_zero_sales'))}
    if s['sales_feed']['missing'] and s['pending']:
        s['pending']={**s['pending'],'rows':[],'status':'missing_data','blocked_reason':'Chưa có nguồn giao dịch; không coi thiếu dữ liệu là bán bằng 0.'}
    s['reconciliation']=accounting
    if accounting['errors']:
        for key in ['revenue','cost_assumed','contribution_before_overhead','waste','sell_through_pct']:s['totals'][key]=None
    s['totals']['forecast_units']=sum(int(p['forecast']+.5) for p in s['plan'])
    from services.proposal_narrative import prepare,immediate
    component='m1' if s['minute']>=1170 else 'm2'
    s['proposal_explanation']=dict(component=component,answer=immediate(prepare(s,component,lambda sku:evidence(s,sku))),
        evidence_delivery='SERVER_EXECUTED_READ_ONLY_TOOLS_BEFORE_GENERATION',ai_status='pending')
    return s


@app.get('/api/state')
def state(session_id: str | None = None):
    try:
        s = store.get(session_id)
    except ValueError:
        if session_id:
            raise
        if actor.get()['role']=='viewer':raise AccessError('Chưa có ca để xem; cần Staff/Manager tạo ca đầu tiên.')
        s = workflow.create(auto_run=True)
    return snapshot(s)


@app.get('/api/proposal-explanation/{sid}')
def proposal_explanation(sid: str, component: str = 'm2',retry: bool=False):
    if retry:explanations.invalidate_errors()
    return explanations.get(store.get(sid),component,assistant,evidence)


@app.get('/api/report-explanation/{sid}')
def report_explanation(sid: str, days: int=30, section: str='overview', sku: str='all', refresh_revision: int|None=None, retry: bool=False):
    from services.business_reports import report,analysis_context
    s=store.get(sid)
    if refresh_revision is not None and not 0<=refresh_revision<=s['revision']:raise ValueError('Invalid report refresh revision')
    if section=='baseline':
        from services.baseline_history import report as baseline_report
        data=baseline_report(s['day'],days)
    else:data=report(store,sid,days,selected=s)
    context=analysis_context(data,section,sku,refresh_revision)
    if retry:explanations.invalidate_errors()
    return explanations.get(s,'reports',assistant,evidence,context)


class NewSession(BaseModel):
    day: str = '2022-05-02'
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    mode: str = 'simulation'
    auto_run: bool = True
    operation_mode: str = 'assisted'
    market_version: str | None = None


@app.post('/api/sessions')
def create_session(body: NewSession):
    if body.operation_mode!='assisted' and actor.get()['role']!='manager':raise AccessError('Chỉ Manager chọn chế độ vận hành đặc biệt.')
    return snapshot(workflow.create(**body.model_dump()))


@app.get('/api/sessions')
def sessions():
    return [{'id': s['id'], 'day': s['day'], 'phase': s['phase'], 'mode': s['mode'], 'created': s['created']} for s in store.sessions()]


class Action(BaseModel):
    revision: int
    payload: dict = Field(default_factory=dict)
    key: str = Field(default_factory=lambda: uuid.uuid4().hex)


@app.post('/api/sessions/{sid}/{action}')
def act(sid: str, action: str, body: Action):
    if action not in ['plan_approve', 'plan_reject', 'prepared', 'advance', 'price_approve', 'price_reject', 'price_apply', 'sales', 'close','confirm_zero_sales','refresh_price','replan']:
        raise ValueError('Thao tác không hợp lệ.')
    result = workflow.mutate(sid, body.revision, action, body.payload, body.key)
    if action=='prepared' and result.get('auto_run'):
        realtime.configure(sid,True)
        result=store.get(sid)
    if action == 'close' and result['mode'] == 'live':
        try:
            result['learning_collection'] = learning.collect(result)
        except ValueError as exc:
            # Closing an accounting ledger must succeed even if training data is ineligible.
            result['learning_collection'] = {'warning': str(exc)}
            with store.connect() as db:
                db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)', (sid, 'LEARNING_COLLECTION_SKIPPED', json.dumps({'reason': str(exc)})))
    if action=='close':
        try:
            with Monitoring.job(store,'CLOSED_EVALUATION',sid):monitoring_service(sid).closed_evaluation(result)
        except Exception as exc:
            # A monitoring failure must not roll back an already closed accounting ledger.
            with store.connect() as db:
                workflow.safety.audit(db,sid,'MONITORING_EVALUATION_SKIPPED',{'reason':str(exc)[:500]})
    return snapshot(result)


class ClockRequest(BaseModel):
    enabled: bool
    speed: float = 30.
    pause_confirm: bool = True


@app.post('/api/realtime/{sid}')
def clock_control(sid: str,body: ClockRequest):
    realtime.configure(sid,body.enabled,body.speed,body.pause_confirm)
    return snapshot(store.get(sid))


@app.get('/api/simulator')
def simulator_report():
    return simulator.arrivals.report()


@app.post('/api/scenarios/{sid}/fork')
def fork_scenario(sid: str):
    return snapshot(workflow.fork_simulation(sid))


class NextDayRequest(BaseModel):
    weather: dict | None = None


@app.post('/api/day-chain/{sid}')
def next_day(sid: str,body: NextDayRequest):
    weather=body.weather
    if weather is not None:
        from datetime import date,timedelta
        day=(date.fromisoformat(store.get(sid)['day'])+timedelta(days=1)).isoformat()
        preview=inspect('weather.csv',pd.DataFrame([{'date':day,**weather}]).to_csv(index=False).encode(),day,engine.master)
        if not preview['valid']:raise ValueError('; '.join(preview['errors']))
        weather=preview['weather']
    return snapshot(workflow.next_day(sid,weather))


class ReconciliationRequest(BaseModel):
    revision:int
    state_sha256:str
    reason:str=Field(min_length=3,max_length=2000)

@app.get('/api/evaluation/{sid}')
def evaluation_report(sid:str):
    return Evaluation(store,learning).report(sid)

@app.post('/api/evaluation/{sid}/certify')
def certify_report(sid:str,body:ReconciliationRequest):
    return Evaluation(store,learning).certify(sid,body.revision,body.state_sha256,body.reason)

@app.get('/api/evaluation/{sid}/sensitivity')
def evaluation_sensitivity(sid:str):
    return Evaluation(store,learning).sensitivity(sid)


class LifecycleRequest(BaseModel):
    reason: str = Field(min_length=3,max_length=2000)
    checkpoint_id: str | None = None

@app.post('/api/registry/checkpoint')
def registry_checkpoint(body:LifecycleRequest):
    if actor.get()['role']!='manager':raise AccessError('Chỉ Manager quản lý snapshot model.')
    return learning.checkpoint(body.reason)

@app.post('/api/registry/restore')
def registry_restore(body:LifecycleRequest):
    if actor.get()['role']!='manager':raise AccessError('Chỉ Manager khôi phục model.')
    return learning.rollback(engine.version,body.reason,body.checkpoint_id)

@app.get('/api/registry')
def model_registry():
    return learning.registry()

@app.post('/api/learning/{version}/holdout')
def fresh_holdout(version:str):
    with Monitoring.job(store,'FRESH_HOLDOUT'):
        return learning.fresh_holdout(version)

@app.get('/api/learning')
def learning_status():
    return learning.status()


@app.post('/api/learning/upload')
async def learning_upload(file: UploadFile = File(...), kind: str = Form('m2'), origin: str = Form('real')):
    raw = await file.read(MAX_BYTES + 1)
    return await run_in_threadpool(learning.ingest, file.filename or 'upload.csv', raw, kind, origin)


class TrainingRequest(BaseModel):
    kind: str = 'm2'
    origin: str = 'real'


@app.post('/api/learning/train')
def learning_train(body: TrainingRequest):
    with Monitoring.job(store,'MODEL_TRAIN_'+body.kind.upper()):
        learning.active().require_integrity()
        return learning.train(body.kind, body.origin)


@app.post('/api/learning/demo')
def learning_demo(body: TrainingRequest):
    if body.kind not in ['m1', 'm2']:
        raise ValueError('Loại demo không hợp lệ.')
    learning.ingest('DEMO.csv', demo_data(body.kind, engine.master), body.kind, 'demo')
    return learning.train(body.kind, 'demo')


class PromotionRequest(BaseModel):
    expected_active: str
    reason: str = Field(min_length=3, max_length=2000)


@app.post('/api/learning/{version}/promote')
def learning_promote(version: str, body: PromotionRequest):
    return learning.promote(version, body.expected_active, body.reason)


@app.post('/api/learning/rollback')
def learning_rollback(body: PromotionRequest):
    return learning.rollback(body.expected_active, body.reason)


@app.get('/api/learning/template/{kind}')
def learning_template(kind: str):
    if kind not in ['m1', 'm2']:
        raise ValueError('Loại mẫu không hợp lệ.')
    columns = DAILY if kind == 'm2' else PROMO
    return Response(','.join(columns) + '\n', media_type='text/csv', headers={'Content-Disposition': f'attachment; filename={"daily_outcomes" if kind == "m2" else "promo_trials"}.csv'})


@app.get('/api/evidence/{sid}/{sku}')
def get_evidence(sid: str, sku: str):
    return evidence(store.get(sid), sku)


@app.get('/api/audit/{sid}')
def audit(sid: str):
    return store.audit(sid)


@app.get('/api/metadata')
def metadata():
    active = learning.active()
    return {'model':active.version,'original_frozen_model':engine.version,'skus':engine.skus,'selection':active.selection,'archive':'V4 locked model + V4 Validation inputs','archive_sha256':__import__('hashlib').sha256((ROOT/'MODEL_DATA_HASHES.json').read_bytes()).hexdigest(),'original_observations_available':False,'reference_run':{},'ai':assistant.status(),'training_review':engine.training_review,'simulation_scenarios':simulator.report()['scenarios'],'demo_dates':sorted(simulator.calendar),'model_manifest':engine.manifest}


@app.get('/api/history')
def historical(session_id: str | None = None):
    try:
        s=store.get(session_id)
        h=pd.DataFrame([{'date':r['date'],'sold_qty':r['sold']} for r in s['input_history'] if r['date']<s['day']])
    except ValueError:
        h = pd.DataFrame(engine.seed_rows)
    if h.empty:return []
    rows = h.groupby('date').sold_qty.sum().tail(14)
    return [{'day': d, 'sold': int(v)} for d, v in rows.items()]


@app.get('/api/business-report/{sid}')
def business_report(sid: str, days: int = 30):
    from services.business_reports import report
    return report(store, sid, days)


@app.get('/api/simulation-comparison')
def simulation_comparison(day: str = '2022-05-02', seed: int = 42):
    return simulator.comparison(day,seed)


@app.get('/api/baseline-history/{sid}')
def baseline_history(sid: str,days: int=180):
    from services.baseline_history import report
    return report(store.get(sid)['day'],days)


@app.get('/api/reference')
def reference():
    return {'source':'V4 locked 62-day evaluation · POST_TEST_DEVELOPMENT_ITERATION · read-only reference, not current session','systems':pd.read_csv(ROOT/'reference/v4/BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv').to_dict('records'),'daily':[],'metrics':{}}


@app.get('/api/quality')
def quality(session_id: str):
    s = store.get(session_id)
    return {'session_id':s['id'], 'feature_snapshot_id':s.get('feature_snapshot_id'),
            'quality':snapshot(s)['data_quality'], 'source':s['source'], 'policy':POLICY}


@app.get('/api/imports')
def import_history():
    with store.connect() as db:
        rows = db.execute('SELECT id,payload FROM imports ORDER BY rowid DESC LIMIT 100').fetchall()
    result=[]
    for row in rows:
        p=json.loads(row['payload'])
        result.append({'import_id':row['id'], **{k:p.get(k) for k in
            ['filename','sha256','day','created_at','confirmed_at','source_name','confirmed_session','feature_snapshot_id']},
            'status':p.get('status') or ('CONFIRMED' if p.get('confirmed_session') else 'PREVIEW' if p.get('valid') else 'QUARANTINED'),
            'confirmation_error':p.get('confirmation_error'),'error_count':len(p.get('errors',[])) + bool(p.get('confirmation_error')), 'warnings':p.get('warnings',[]), 'errors':p.get('errors',[]),
            'history_rows':len(p.get('history',[])),'transaction_rows':len(p.get('transactions',[]))})
    return {'imports':result,'limit':100,'note':'100 lượt mới nhất; bản gốc giữ trong SQLite local.'}


@app.post('/api/imports')
async def upload(file: UploadFile = File(...), day: str = Form(...), source_name: str = Form('Người dùng nhập; chưa xác thực')):
    raw = await file.read(MAX_BYTES + 1)
    try:
        preview = await run_in_threadpool(inspect, file.filename or 'upload', raw, day, engine.master)
    except (ValueError, zipfile.BadZipFile, UnicodeError) as exc:
        import hashlib
        rejected = {'filename':Path(file.filename or 'upload').name,'day':day,'sha256':hashlib.sha256(raw).hexdigest(),
                    'created_at':now(),'source_name':source_name[:200], 'status':'QUARANTINED','valid':False,
                    'errors':[{'row':1,'message':str(exc)}], 'history':[],'transactions':[], 'weather':None}
        with store.connect() as db:
            db.execute('INSERT INTO imports(id,payload) VALUES (?,?)',(uuid.uuid4().hex,json.dumps(rejected,ensure_ascii=False)))
        raise
    unknown = [t for t in preview['tables'] if t['kind'] == 'unknown']
    if unknown and assistant.status()['configured'] and len(preview['tables']) == 1:
        mapping = await run_in_threadpool(assistant.map_columns, unknown[0]['columns'])
        preview = await run_in_threadpool(inspect, file.filename or 'upload', raw, day, engine.master, mapping)
        preview['ai_column_mapping'] = mapping
    preview.update({'created_at':now(),'source_name':source_name[:200],'status':'PREVIEW' if preview['valid'] else 'QUARANTINED'})
    iid = uuid.uuid4().hex
    with store.connect() as db:
        db.execute('INSERT INTO imports(id,payload) VALUES (?,?)', (iid, json.dumps(preview, ensure_ascii=False, allow_nan=False)))
    return {**preview, 'import_id': iid, 'history': preview['history'][:5], 'transactions': preview['transactions'][:5],
            'history_rows': len(preview['history']), 'transaction_rows': len(preview['transactions'])}


class ImportConfirm(BaseModel):
    session_id: str | None = None
    revision: int | None = None
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


@app.post('/api/imports/{iid}/confirm')
def confirm_import(iid: str, body: ImportConfirm):
    try:
        return _confirm_import(iid,body)
    except ValueError as exc:
        with store.connect() as db:
            row=db.execute('SELECT payload FROM imports WHERE id=?',(iid,)).fetchone()
            if row:
                p=json.loads(row['payload'])
                if not p.get('confirmed_session'):
                    p.update({'status':'BLOCKED' if p.get('valid') else 'QUARANTINED','confirmation_error':str(exc)})
                    db.execute('UPDATE imports SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),iid))
        raise


def _confirm_import(iid: str, body: ImportConfirm):
    with store.connect() as db:
        row = db.execute('SELECT payload FROM imports WHERE id=?', (iid,)).fetchone()
    if not row:
        raise ValueError('Không tìm thấy bản nhập.')
    p = json.loads(row['payload'])
    if not p['valid']:
        raise ValueError('Hãy sửa các lỗi dữ liệu trước khi xác nhận.')
    if p.get('confirmed_session'):
        return snapshot(store.get(p['confirmed_session']))
    if p['transactions']:
        if not body.session_id or body.revision is None:
            raise ValueError('Cần chọn ca đang nhận giao dịch.')
        s = store.get(body.session_id)
        with store.connect() as db:
            duplicate=db.execute("SELECT id FROM imports WHERE id<>? AND json_extract(payload,'$.sha256')=? AND json_extract(payload,'$.confirmed_session')=? LIMIT 1",(iid,p['sha256'],s['id'])).fetchone()
        if duplicate:
            raise ValueError('Tệp giao dịch cùng SHA256 đã được nhập vào ca này; chặn nhập trùng.')
        if s['day'] != p['day']:
            raise ValueError('Ngày nhập khác ngày của ca.')
        s = workflow.mutate(s['id'], body.revision, 'sales', {'rows': p['transactions']}, iid)
    else:
        visible = {(r['date'], r['sku_code']): r['sold_qty'] for r in p['history']} if p['history'] else None
        feature_demo=bool(p.get('feature_rows')) and p['weather'] is None
        if feature_demo:
            if p['day'] not in simulator.calendar:raise ValueError('Ngày ngoài lịch mẫu V4 cần weather.csv có issued_at; không tự tạo forecast.')
            p['weather']={**simulator.calendar[p['day']],'v4_features':{x['sku_code']:x for x in p['feature_rows']}}

        s = workflow.create(day=p['day'], seed=body.seed, mode='simulation' if feature_demo else 'live', history=visible, weather=p['weather'],outcome_snapshot={(x['date'],x['sku_code']):x for x in p.get('outcomes',[])} or None, identifier='import-' + iid,
                            source=p['filename'] + ' · SHA256 ' + p['sha256'][:12],
                            provenance={'type':'upload','import_id':iid,'filename':p['filename'],'file_sha256':p['sha256'],
                                        'source':p.get('source_name','User upload'),'availability':p.get('history_availability','date_only_unverified'),
                                        'imported_at':p.get('created_at'),'assurance':p.get('source_assurance')})
    p['confirmed_session'] = s['id']
    p.pop('confirmation_error',None)
    p['status'] = 'CONFIRMED'
    p['confirmed_at'] = now()
    p['feature_snapshot_id'] = s.get('feature_snapshot_id')
    with store.connect() as db:
        db.execute('UPDATE imports SET payload=? WHERE id=?', (json.dumps(p, ensure_ascii=False), iid))
    return snapshot(s)


@app.get('/api/templates/{kind}')
def template(kind: str):
    if kind=='history':
        sample=pd.DataFrame(engine.observed)
        sample=sample[sample['date']<'2022-05-02'][['date','sku_code','sold_qty','prepared_qty','censored_demand_flag']]
        content=sample.to_csv(index=False)
    elif kind=='features':
        return FileResponse(ROOT/'data/v4/import_example.csv',filename='morning_features_V4.csv')
    elif kind=='weather':
        content='date,forecast_rain_mm_previous_day1,forecast_temperature_max_c_previous_day1,is_public_holiday,is_festival_non_public,issued_at,weather_reference_date\n2022-05-02,0,28,0,0,2022-05-01T23:00:00+07:00,2022-05-01\n'
    elif kind=='transactions':
        content='sku_code,minute,quantity\nTP-DN-001,480,2\n'
    else:raise ValueError('Loại file mẫu không hợp lệ.')
    return Response(content, media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{kind}.csv"'})


@app.get('/api/export/{sid}')
def export(sid: str):
    s = store.get(sid)
    out = io.StringIO()
    writer = csv.DictWriter(out, extrasaction='ignore', fieldnames=['sku', 'minute', 'qty', 'discount', 'unit_price', 'paid', 'origin'])
    writer.writeheader()
    writer.writerows(s['ledger'])
    return Response('\ufeff' + out.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="ledger-{s["day"]}-{sid[:8]}.csv"'})


class AISettings(BaseModel):
    api_key: str = ''
    model: str = 'gpt-4.1-mini'
    provider: str = 'OpenAI'


@app.post('/api/ai/models')
def ai_models(body: AISettings):
    if body.provider != 'Gemini':
        raise ValueError('Kiểm tra danh sách model hiện dành cho Gemini.')
    from services.providers import list_gemini_models
    candidate = Assistant()
    candidate.configure(body.api_key.strip(), body.model.strip(), 'Gemini')
    return list_gemini_models(candidate)


@app.post('/api/ai/settings')
def ai_settings(body: AISettings):
    return assistant.configure(body.api_key, body.model, body.provider)


class Chat(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    report_days: int|None=None
    report_section: str='overview'
    report_sku: str='all'


class AIConnection(AISettings):
    session_id: str


def verify_ai(client, s):
    sku=s['plan'][0]['sku']
    result = client.chat('Verify connection: call get_session_context and get_model_evidence for '+sku+'. Explain raw M2 forecast, supply plan, current cumulative sales and stock in Vietnamese. State missing evidence explicitly.',s,lambda sku:evidence(s,sku))
    with store.connect() as db:
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                   (s['id'], client.provider.upper() + '_CONNECTION_TEST', json.dumps({
                       'response_id': result['response_id'], 'model': result['model'], 'provider': client.provider,
                       'tools': result['tools_used'], 'revision': s['revision']})))
    return result


@app.post('/api/ai/connect')
def ai_connect(body: AIConnection):
    if body.provider != 'Ollama' and not body.api_key.strip():
        raise ValueError('Cần nhập API key của nhà cung cấp đã chọn. Ollama local không cần key.')
    candidate = Assistant()
    candidate.configure(body.api_key.strip(), body.model.strip(), body.provider)
    try:
        result = verify_ai(candidate, store.get(body.session_id))
    except ValueError:
        # Expose only a sanitized diagnosis; a rejected key is never retained.
        assistant.last_error = candidate.last_error
        raise
    # Replace the current connection only after a real Responses/tool loop succeeds.
    assistant.configure(candidate.key, candidate.model, candidate.provider)
    explanations.invalidate_errors()
    assistant.verified, assistant.last_response_id = True, result['response_id']
    return {'ai': assistant.status(), 'verification': result}


@app.post('/api/ai/verify')
def ai_verify(body: Chat):
    result = verify_ai(assistant, store.get(body.session_id))
    return {'ai': assistant.status(), 'verification': result}


@app.post('/api/chat')
def chat(body: Chat):
    s = store.get(body.session_id)
    report_context=None
    if body.report_days is not None:
        from services.business_reports import report,analysis_context
        report_context=analysis_context(report(store,s['id'],body.report_days,selected=s),body.report_section,body.report_sku)
    result = assistant.chat(body.message, s, lambda sku: evidence(s, sku),report_context)
    with store.connect() as db:
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                   (s['id'], assistant.provider.upper() + '_EXPLANATION', json.dumps({'response_id': result['response_id'], 'model': result['model'], 'provider': assistant.provider, 'tools': result['tools_used'], 'revision': s['revision']})))
    return result


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', '8000'))
    print(f'SmartFresh: http://127.0.0.1:{port} | V4 locked models + original prototype + V4 POS replay | Ctrl+C để dừng')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')

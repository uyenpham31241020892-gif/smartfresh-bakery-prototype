"""SmartFresh local inference, approvals, uploads and OpenAI tools."""
import csv
import io
import json
import os
from pathlib import Path
import sys
import uuid
import zipfile
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
from services.assistant import Assistant
from services.learning import Learning, DAILY, PROMO, demo_data
from services.realtime import Realtime

engine = Engine()
simulator = Simulator(engine)
store = Store(os.environ.get('SMARTFRESH_DB'))
workflow = Workflow(engine, simulator, store)
learning = Learning(store, engine, os.environ.get('SMARTFRESH_LEARNING_DIR'))
workflow.active_engine = learning.active
workflow.version_engine = learning.resolve
workflow.observed_history = learning.history_before
workflow.observed_outcomes = learning.outcomes_before
assistant = Assistant()
realtime = Realtime(workflow,store)


@asynccontextmanager
async def lifespan(application):
    realtime.start()
    try:yield
    finally:realtime.stop()


app = FastAPI(title='SmartFresh Bakery', docs_url='/api/docs',lifespan=lifespan)
app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')


@app.middleware('http')
async def local_origin(request: Request, call_next):
    from urllib.parse import urlparse
    origin = request.headers.get('origin')
    if request.method != 'GET' and origin and urlparse(origin).hostname not in ['127.0.0.1', 'localhost', 'testserver']:
        return JSONResponse({'error': 'Chỉ nhận thao tác từ dashboard local.'}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=400)


@app.exception_handler(zipfile.BadZipFile)
async def bad_archive(request, exc):
    return JSONResponse({'error': 'Tệp ZIP/Excel bị hỏng hoặc không đúng định dạng.'}, status_code=400)


@app.get('/')
def home():
    return FileResponse(ROOT / 'web/index.html')


@app.get('/api/health')
def health():
    return {'ok': True, 'model': learning.active().version, 'ai': assistant.status(), 'timezone': 'Asia/Ho_Chi_Minh'}


def evidence(s, sku):
    plan = next((p for p in s['plan'] if p['sku'] == sku), None)
    if plan is None:
        raise ValueError('SKU không hợp lệ.')
    pricing = next((p for p in (s['pending'] or {}).get('rows', []) if p['sku'] == sku), None)
    if pricing is None and s['decisions']:
        pricing = next((p for p in s['decisions'][-1]['rows'] if p['sku'] == sku), None)
    manifest = learning.resolve(s['model_version']).manifest
    return {'sku': sku, 'model_version': s['model_version'], 'session_id': s['id'], 'revision': s['revision'],
            'training': {'parent': manifest.get('parent'), 'component_retrained': manifest.get('learning_kind'),
                         'data_cutoff': manifest.get('trained_until', '2022-08-15'),
                         'source': 'uploaded_real_outcomes' if manifest.get('parent') else 'provided_V9_synthetic_bundle'},
            'm2': plan, 'm1': pricing, 'explanation_type': 'exact_tree_contributions_M2_and_optimizer_candidates_M1'}


def snapshot(s):
    products = list(s['products'].values())
    prepared = sum(p['prepared'] for p in products)
    sold = sum(p['sold'] for p in products)
    revenue = sum(p['revenue'] for p in products)
    cost = sum(round(p['prepared'] * p['price'] * .45) for p in products)
    s = dict(s)
    s.pop('keys', None)
    s.pop('input_history', None)
    s.pop('input_outcomes',None)
    s['totals'] = {'prepared': prepared, 'sold': sold, 'stock': prepared - sold, 'revenue': revenue,
        'waste': prepared - sold if s['phase'] == 'closed' else None,
        'lost_simulator_only': sum(p['lost'] for p in products) if s['mode'] == 'simulation' else None,
        'cost_assumed': cost, 'contribution_before_overhead': revenue - cost,
        'sell_through_pct': 100 * sold / prepared if prepared else 0,
        'proposed_prepared': sum(p['prepared'] for p in s['plan']), 'forecast': sum(p['forecast'] for p in s['plan'])}
    s['ai'] = assistant.status()
    s['realtime']=realtime.status(s['id'])
    s['sales_feed']={'type':'trained_simulator' if s['mode']=='simulation' else 'manual_import',
                     'has_transactions':bool(s['ledger']),'missing':s['mode']=='live' and not s['ledger'] and not s.get('confirmed_zero_sales'),
                     'confirmed_zero':bool(s.get('confirmed_zero_sales'))}
    if s['sales_feed']['missing'] and s['pending']:
        s['pending']={**s['pending'],'rows':[],'status':'missing_data','blocked_reason':'Chưa có nguồn giao dịch; không coi thiếu dữ liệu là bán bằng 0.'}
    s['totals']['forecast_units']=sum(int(p['forecast']+.5) for p in s['plan'])
    return s


@app.get('/api/state')
def state(session_id: str | None = None):
    try:
        s = store.get(session_id)
    except ValueError:
        if session_id:
            raise
        s = workflow.create()
    return snapshot(s)


class NewSession(BaseModel):
    day: str = '2022-08-16'
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    mode: str = 'simulation'
    auto_run: bool = False


@app.post('/api/sessions')
def create_session(body: NewSession):
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
    if action not in ['plan_approve', 'plan_reject', 'prepared', 'advance', 'price_approve', 'price_reject', 'price_apply', 'sales', 'close','confirm_zero_sales']:
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
    return snapshot(result)


class ClockRequest(BaseModel):
    enabled: bool
    speed: float = 5.
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
    provenance = json.loads((DATA / 'provenance.json').read_text())
    summary = json.loads((ROOT / 'reference/drive_v9/summary.json').read_text())
    return {'model': active.version, 'original_frozen_model': engine.version, 'skus': engine.skus, 'selection': active.selection,
            'archive': provenance['archive'], 'archive_sha256': provenance['archive_sha256'],
            'original_observations_available': False, 'reference_run': summary, 'ai': assistant.status()}


@app.get('/api/history')
def historical(session_id: str | None = None):
    try:
        s=store.get(session_id)
        h=pd.DataFrame([{'date':r['date'],'sold_qty':r['sold']} for r in s['input_history'] if r['date']<s['day']])
    except ValueError:
        h = pd.read_csv(DATA / 'history_through_aug15_synthetic.csv')
    if h.empty:return []
    rows = h.groupby('date').sold_qty.sum().tail(14)
    return [{'day': d, 'sold': int(v)} for d, v in rows.items()]


@app.get('/api/reference')
def reference():
    results = []
    for system in ['BASELINE', 'M1_M2_SELECTED']:
        frame = pd.read_csv(DATA / 'outputs' / f'{system}_daily_sep.csv')
        sums = {k: int(frame[k].sum()) for k in ['prepared_qty', 'sold_qty', 'waste_qty', 'lost_sales_qty', 'revenue_vnd', 'production_cost_assumed_vnd', 'contribution_before_overhead_vnd']}
        sums['system'] = system
        results.append(sums)
    daily = pd.read_csv(DATA / 'outputs/M1_M2_SELECTED_daily_sep.csv').groupby('date')[['revenue_vnd', 'waste_qty', 'lost_sales_qty']].sum().reset_index().to_dict('records')
    return {'source': 'Archived V9 run d8b621a5; read-only reference', 'systems': results, 'daily': daily,
            'metrics': json.loads((ROOT / 'reference/drive_v9/summary.json').read_text())['m2_metrics']}


@app.post('/api/imports')
async def upload(file: UploadFile = File(...), day: str = Form(...)):
    raw = await file.read(MAX_BYTES + 1)
    preview = await run_in_threadpool(inspect, file.filename or 'upload', raw, day, engine.master)
    unknown = [t for t in preview['tables'] if t['kind'] == 'unknown']
    if unknown and assistant.status()['configured'] and len(preview['tables']) == 1:
        mapping = await run_in_threadpool(assistant.map_columns, unknown[0]['columns'])
        preview = await run_in_threadpool(inspect, file.filename or 'upload', raw, day, engine.master, mapping)
        preview['ai_column_mapping'] = mapping
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
        if s['day'] != p['day']:
            raise ValueError('Ngày nhập khác ngày của ca.')
        s = workflow.mutate(s['id'], body.revision, 'sales', {'rows': p['transactions']}, iid)
    else:
        visible = {(r['date'], r['sku_code']): r['sold_qty'] for r in p['history']} if p['history'] else None
        s = workflow.create(day=p['day'], seed=body.seed, mode='live', history=visible, weather=p['weather'], identifier='import-' + iid,
                            source=p['filename'] + ' · SHA256 ' + p['sha256'][:12])
    p['confirmed_session'] = s['id']
    with store.connect() as db:
        db.execute('UPDATE imports SET payload=? WHERE id=?', (json.dumps(p, ensure_ascii=False), iid))
    return snapshot(s)


@app.get('/api/templates/{kind}')
def template(kind: str):
    if kind == 'history':
        return FileResponse(DATA / 'history_through_aug15_synthetic.csv', filename='history.csv')
    if kind == 'weather':
        content = 'date,forecast_rain_mm_previous_day1,forecast_temperature_max_c_previous_day1,is_public_holiday,is_festival_non_public,issued_at\n2026-10-21,5,31,0,0,2026-10-20T18:00:00+07:00\n'
    elif kind == 'transactions':
        content = 'sku_code,minute,quantity\nBK-001,480,2\n'
    else:
        raise ValueError('Loại file mẫu không hợp lệ.')
    return Response(content, media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{kind}.csv"'})


@app.get('/api/export/{sid}')
def export(sid: str):
    s = store.get(sid)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['sku', 'minute', 'qty', 'discount', 'unit_price', 'paid', 'origin'])
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


class AIConnection(AISettings):
    session_id: str


def verify_ai(client, s):
    result = client.chat(
        'Kiểm tra kết nối SmartFresh: gọi công cụ đọc ca và bằng chứng của BK-001, '
        'sau đó trả lời ngắn gọn bằng tiếng Việt về nhu cầu dự báo và sản lượng đề xuất của BK-001. '
        'Nêu bước nào đang chờ quản lý xác nhận.',
        s, lambda sku: evidence(s, sku))
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
    assistant.verified, assistant.last_response_id = True, result['response_id']
    return {'ai': assistant.status(), 'verification': result}


@app.post('/api/ai/verify')
def ai_verify(body: Chat):
    result = verify_ai(assistant, store.get(body.session_id))
    return {'ai': assistant.status(), 'verification': result}


@app.post('/api/chat')
def chat(body: Chat):
    s = store.get(body.session_id)
    result = assistant.chat(body.message, s, lambda sku: evidence(s, sku))
    with store.connect() as db:
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                   (s['id'], assistant.provider.upper() + '_EXPLANATION', json.dumps({'response_id': result['response_id'], 'model': result['model'], 'provider': assistant.provider, 'tools': result['tools_used'], 'revision': s['revision']})))
    return result


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', '8000'))
    print(f'SmartFresh: http://127.0.0.1:{port} | V9 inference + SQLite | Ctrl+C để dừng')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')

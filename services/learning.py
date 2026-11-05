"""V4-only lifecycle: evidence, data collection, immutable deployment snapshots and recovery.
Training remains locked, as in the supplied prototype, per the V4 freeze decision.
"""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,io,json,math,threading,uuid,zipfile,shutil
import pandas as pd
from .engine import ROOT,Engine,LADDER,CAPS,FLOORS,MODEL_VERSION
from .ingestion import tables,integer,MAX_BYTES
from .identity import actor
WEATHER=['forecast_rain_mm_previous_day1','forecast_temperature_max_c_previous_day1','is_public_holiday','is_festival_non_public','issued_at']
DAILY=['date','sku_code','prepared_qty','sold_qty','waste_qty','stockout','discounted_qty']+WEATHER
PROMO=['date','sku_code','slot','discount_pct','incremental_promo_qty','measurement_method','experiment_id']+WEATHER

def weather(row: dict) -> dict:
    """Extract the weather / calendar fields from a learning row dict.
    Returns a dict suitable for passing as *weather* to Workflow.create()."""
    return {k: row[k] for k in WEATHER if k in row}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
class Learning:
    def __init__(self,store,frozen,directory=None):
        self.store,self.frozen=store,frozen;self.root=Path(directory or ROOT/'runtime/v4_lifecycle');self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS learning_rows(kind TEXT,origin TEXT,row_key TEXT,payload TEXT,PRIMARY KEY(kind,origin,row_key));
            CREATE TABLE IF NOT EXISTS learning_datasets(id TEXT PRIMARY KEY,report TEXT);
            CREATE TABLE IF NOT EXISTS learning_runs(id TEXT PRIMARY KEY,report TEXT);
            CREATE TABLE IF NOT EXISTS model_holdouts(id TEXT PRIMARY KEY,version TEXT,report TEXT);
            CREATE TABLE IF NOT EXISTS model_active(id INTEGER PRIMARY KEY CHECK(id=1),version TEXT);
            CREATE TABLE IF NOT EXISTS v4_checkpoints(id TEXT PRIMARY KEY,payload TEXT);''')
            db.execute('INSERT OR IGNORE INTO model_active VALUES(1,?)',(MODEL_VERSION,))
            current=db.execute('SELECT version FROM model_active WHERE id=1').fetchone()['version']
            from .volume_scenario import MODEL_VERSION as OPERATING_MODEL,LEGACY_MODEL_VERSION
            if current not in (MODEL_VERSION,OPERATING_MODEL,LEGACY_MODEL_VERSION):raise ValueError('Database chứa phiên bản không được hỗ trợ.')
            self.resolve(OPERATING_MODEL).require_integrity()
            if current!=OPERATING_MODEL:
                db.execute('UPDATE model_active SET version=? WHERE id=1',(OPERATING_MODEL,))
                db.execute('INSERT INTO audit(action,detail) VALUES (?,?)',('MODEL_DEFAULT_UPGRADED',json.dumps(dict(previous=current,current=OPERATING_MODEL,reason='User requested joint policy as primary configuration; historical sessions retain pinned versions'))))
    def resolve(self,version):
        from .volume_scenario import MODEL_VERSION as VOLUME_MODEL, LEGACY_MODEL_VERSION
        if version in (VOLUME_MODEL,LEGACY_MODEL_VERSION):
            with self.lock:
                if not hasattr(self,'operating_engines'):self.operating_engines={}
                if version not in self.operating_engines:
                    from .volume_engine import VolumeEngine
                    self.operating_engines[version]=VolumeEngine(version)
                return self.operating_engines[version]
        if version!=MODEL_VERSION:raise ValueError('Không nạp phiên bản/data cũ trong workspace V4.')
        return self.frozen
    def active(self):
        from .volume_scenario import MODEL_VERSION as OPERATING_MODEL
        return self.resolve(OPERATING_MODEL)
    def rows(self,kind,origin):
        with self.store.read() as db:return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM learning_rows WHERE kind=? AND origin=? ORDER BY row_key',(kind,origin))]
    def history_before(self,day):return {(r['date'],r['sku_code']):r['sold_qty'] for r in self.rows('m2','real') if r['date']<day}
    def outcomes_before(self,day):return {(r['date'],r['sku_code']):r for r in self.rows('m2','real') if r['date']<day}
    def ingest(self, name, raw, kind, origin='real', allow_closed_today=False):
        if kind not in ['m2', 'm1'] or origin not in ['real', 'demo']:
            raise ValueError('Loại dữ liệu học không hợp lệ.')
        if len(raw) > MAX_BYTES:
            raise ValueError('Tệp vượt quá 20 MB.')
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if len(archive.infolist()) > 100 or sum(x.file_size for x in archive.infolist()) > 80 * 1024 * 1024:
                    raise ValueError('ZIP học quá lớn.')
                frames = []
                for member in archive.namelist():
                    if Path(member).name in ['daily_outcomes.csv', 'promo_trials.csv']:
                        frames.extend(tables(member, archive.read(member)))
        else:
            frames = tables(name, raw)
        required = DAILY if kind == 'm2' else PROMO
        selected = [frame for _, frame in frames if set(required) <= set(frame.columns)]
        if not selected:
            raise ValueError('Thiếu cột dữ liệu học: ' + ', '.join(required))
        records = pd.concat(selected).to_dict('records')
        if not 1 <= len(records) <= 50000:
            raise ValueError('Cần từ 1 đến 50.000 dòng dữ liệu.')
        clean, keys = [], set()
        today = datetime.now(timezone(timedelta(hours=7))).date()
        for i, source in enumerate(records, 2):
            r = {k: source[k] for k in required}
            try:
                value = r['date']
                r['date'] = (value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value))).isoformat()
                if date.fromisoformat(r['date']) > today or (date.fromisoformat(r['date']) == today and not allow_closed_today):
                    raise ValueError('Chỉ học từ ngày đã kết thúc.')
                if r['sku_code'] not in self.frozen.master:
                    raise ValueError('SKU chưa có trong danh mục V4; cần quy trình thêm SKU riêng.')
                issued = datetime.fromisoformat(str(r['issued_at']))
                cutoff = datetime.fromisoformat(r['date'] + 'T06:00:00+07:00')
                if issued.tzinfo is None or issued > cutoff:
                    raise ValueError('Dự báo thời tiết phải có múi giờ và phát hành trước 06:00 ngày đó.')
                r['issued_at'] = issued.isoformat()
                for k in WEATHER[:2]:
                    r[k] = float(r[k])
                    if not math.isfinite(r[k]):
                        raise ValueError('Thời tiết không hữu hạn.')
                if not 0 <= r[WEATHER[0]] <= 1000 or not -30 <= r[WEATHER[1]] <= 60:
                    raise ValueError('Thời tiết ngoài khoảng hợp lệ.')
                for k in WEATHER[2:4]:
                    r[k] = integer(r[k], k)
                    if r[k] not in [0, 1]:
                        raise ValueError(k + ' phải là 0 hoặc 1.')
                if kind == 'm2':
                    for k in ['prepared_qty', 'sold_qty', 'waste_qty', 'stockout', 'discounted_qty']:
                        r[k] = integer(r[k], k)
                    if r['stockout'] not in [0, 1] or r['prepared_qty'] != r['sold_qty'] + r['waste_qty']:
                        raise ValueError('Đối soát: chuẩn bị = bán + hủy, stockout phải là 0/1.')
                    if r['discounted_qty'] > r['sold_qty']:
                        raise ValueError('Số bán giảm giá không được vượt tổng bán.')
                    if 'incremental_promo_qty_estimated' in source:
                        incremental=float(source['incremental_promo_qty_estimated'])
                        if not math.isfinite(incremental) or not 0<=incremental<=r['discounted_qty']:
                            raise ValueError('Lượng kích cầu ước tính phải nằm trong lượng bán giảm giá.')
                        r['incremental_promo_qty_estimated']=incremental
                        r['organic_sales_estimated']=r['sold_qty']-incremental
                    r['eligible'] = not r['stockout'] and r['sold_qty'] < r['prepared_qty'] and r['discounted_qty'] == 0
                    key = (r['date'], r['sku_code'])
                else:
                    r['slot'] = integer(r['slot'], 'slot')
                    r['discount_pct'] = integer(r['discount_pct'], 'discount_pct')
                    j, tier = r['slot'], r['discount_pct']
                    if j not in range(5) or tier not in LADDER or not FLOORS[j] <= tier <= CAPS[j]:
                        raise ValueError('Slot 0–4 hoặc mức giảm không đúng policy.')
                    r['incremental_promo_qty'] = float(r['incremental_promo_qty'])
                    if not math.isfinite(r['incremental_promo_qty']) or not 0 <= r['incremental_promo_qty'] <= 10000:
                        raise ValueError('Incremental promo phải hữu hạn, không âm.')
                    if tier == 0 and r['incremental_promo_qty'] != 0:
                        raise ValueError('Mức giảm 0 phải có incremental promo bằng 0.')
                    if r['measurement_method'] != 'controlled_increment' or pd.isna(r['experiment_id']) or not str(r['experiment_id']).strip():
                        raise ValueError('M1 cần controlled_increment và experiment_id; không dùng doanh số thô làm uplift.')
                    r['experiment_id'] = str(r['experiment_id']).strip()
                    key = (r['date'], r['sku_code'], j, tier, r['experiment_id'])
                encoded = json.dumps(key)
                if encoded in keys:
                    raise ValueError('Trùng khóa quan sát trong tệp.')
                keys.add(encoded)
                clean.append((encoded, r))
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f'Dòng {i}: {exc}') from None
        identity = digest({'kind': kind, 'origin': origin, 'rows': sorted(clean)})
        report = {'id': identity, 'kind': kind, 'origin': origin, 'filename': name, 'rows': len(clean),
                  'excluded_stockout': sum(bool(r.get('stockout')) or r.get('sold_qty', -1) == r.get('prepared_qty', -2) for _, r in clean),
                  'excluded_discounted_days': sum(r.get('discounted_qty', 0) > 0 for _, r in clean),
                  'excluded_labels': sum(not r.get('eligible', True) for _, r in clean), 'sha256': hashlib.sha256(raw).hexdigest()}
        with self.store.connect() as db:
            added = 0
            for key, row in clean:
                old = db.execute('SELECT payload FROM learning_rows WHERE kind=? AND origin=? AND row_key=?', (kind, origin, key)).fetchone()
                payload = json.dumps(row, sort_keys=True, allow_nan=False)
                if old and old['payload'] != payload:
                    raise ValueError('Dữ liệu xung đột với quan sát đã lưu; không tự ghi đè.')
                if not old:
                    db.execute('INSERT INTO learning_rows VALUES (?,?,?,?)', (kind, origin, key, payload))
                    added += 1
            report['added'] = added
            db.execute('INSERT OR IGNORE INTO learning_datasets VALUES (?,?)', (identity, json.dumps(report)))
            db.execute('INSERT INTO audit(action,detail) VALUES (?,?)', ('LEARNING_UPLOAD', json.dumps(report)))
        return report

    def collect(self, s):
        if s['mode']=='simulation':return self.collect_simulation(s)
        if s['phase'] != 'closed' or s['mode'] != 'live' or s.get('minute') != 1320:
            raise ValueError('Chỉ thu kết quả từ ca dữ liệu thật đã chốt.')
        records = []
        for sku, p in s['products'].items():
            records.append({'date': s['day'], 'sku_code': sku, 'prepared_qty': p['prepared'], 'sold_qty': p['sold'],
                            'waste_qty': p['stock'], 'stockout': int(p['stock'] == 0 or bool(p.get('stockout_intervals')) or p.get('stockout_since') is not None),
                            'incremental_promo_qty_estimated':p.get('incremental_promo_qty_estimated',0),
                            'discounted_qty': sum(t['qty'] for t in s['ledger'] if t['sku'] == sku and t['discount'] > 0),
                            **{k: s['weather'].get(k) for k in WEATHER}})
        if any(r['issued_at'] is None for r in records):
            raise ValueError('Ca thiếu thời điểm phát hành dự báo; bổ sung qua tệp kết quả thực tế.')
        return self.ingest('closed-' + s['id'] + '.csv', pd.DataFrame(records).to_csv(index=False).encode(), 'm2', 'real', True)

    def collect_simulation(self,s):
        """Observed POS labels only; no unserved requests or future oracle input."""
        from .volume_scenario import VERSION,LEGACY_VOLUME_VERSION
        if s['phase']!='closed' or s['minute']!=1320 or s.get('simulator_version') not in (VERSION,LEGACY_VOLUME_VERSION):
            raise ValueError('Chỉ thu dữ liệu mô phỏng ×10 đã chốt.')
        records=[]
        for sku,p in s['products'].items():
            plan=next(r for r in s['plan'] if r['sku']==sku)
            records.append(('m2',sku,dict(date=s['day'],sku_code=sku,features=plan['features'],
                prepared_qty=p['prepared'],sold_qty=p['sold'],waste_qty=p['stock'],
                incremental_promo_qty_estimated=p.get('incremental_promo_qty_estimated',0),organic_sales_estimated=p.get('organic_sales_estimated',p['sold']),
                censored=bool(p.get('stockout_intervals') or p.get('stockout_since') is not None or any(i['censored'] for i in p.get('observed_intervals',[]))),
                label_available_at=s['day']+'T22:00:00+07:00')))
        seen=set()
        for proposal in s['decisions']:
            minute=proposal['minute']
            if minute in seen or not 1170<=minute<=1290 or proposal['status'] not in ('applied','auto_hold','rejected','shadow_only'):continue
            seen.add(minute)
            for row in proposal['rows']:
                if not row.get('model_features'):continue
                transactions=[t for t in s['ledger'] if t['sku']==row['sku'] and minute<=t['minute']<minute+30]
                discounts={t['discount'] for t in transactions}
                actual=row.get('approved',row['previous']) if proposal['status']=='applied' else row['previous']
                if discounts and discounts!={actual}:continue  # mixed-price window is not one action label
                records.append(('m1_window',row['sku']+':'+str(minute),dict(date=s['day'],sku_code=row['sku'],
                    features=row['model_features'],action_discount_pct=actual,sold_next30_observed=sum(t['qty'] for t in transactions),
                    censored=any(i['censored'] for i in s['products'][row['sku']].get('observed_intervals',[]) if minute<=i['minute']<minute+30),
                    label_available_at=s['day']+f'T{(minute+30)//60:02}:{(minute+30)%60:02}:00+07:00')))
        with self.store.connect() as db:
            for kind,key,row in records:
                row.update(source_session_id=s['id'],model_version=s['model_version'],simulator_hash=s['simulator_hash'],seed=s['seed'],volume_scale=10,origin='simulation_x10',eligible_for_real_training=False)
                db.execute('INSERT OR IGNORE INTO learning_rows VALUES (?,?,?,?)',(kind,'simulation_x10',s['id']+':'+key,json.dumps(row)))
        return dict(rows=len(records),origin='simulation_x10',auto_retrained=False,note='POS đã chốt dùng cho vòng train mô phỏng tiếp theo; không tự trộn vào dữ liệu thật hay thay trọng số đang chạy.')

    def status(self):
        active = self.active()
        with self.store.connect() as db:
            counts = [dict(r) for r in db.execute('SELECT kind,origin,COUNT(*) AS rows FROM learning_rows GROUP BY kind,origin')]
            runs = [json.loads(r['report']) for r in db.execute('SELECT report FROM learning_runs ORDER BY rowid DESC LIMIT 30')]
            datasets = [json.loads(r['report']) for r in db.execute('SELECT report FROM learning_datasets ORDER BY rowid DESC LIMIT 20')]
            events = [dict(r) for r in db.execute('SELECT id,action,detail,created FROM audit WHERE session_id IS NULL ORDER BY id DESC LIMIT 30')]
        from .volume_scenario import MODEL_VERSION as VOLUME_MODEL
        simulation=self.resolve(VOLUME_MODEL)
        return {'active': active.version, 'simulation_model':simulation.version,'simulation_training':simulation.manifest,'frozen': self.frozen.version, 'counts': counts, 'runs': runs, 'datasets': datasets, 'events': events,
                'minimum_days': {'m2': 63, 'm1': 42}, 'trained_until': active.manifest.get('trained_until', '2022-08-15')}

    def train(self,*args,**kwargs):raise ValueError('V4 đã khóa; ứng dụng không train/tune lại.')
    def fresh_holdout(self,*args,**kwargs):raise ValueError('Không tạo nhãn holdout mù mới cho kết quả V4 đã khóa. Xem hồ sơ kiểm định V4.')
    def promote(self,*args,**kwargs):raise ValueError('V4 là phiên bản duy nhất đã chốt; không có ứng viên khác để promotion.')
    def registry(self):
        e=self.active()
        try:e.require_integrity();integrity=True;error=None
        except Exception as exc:integrity=False;error=str(exc)
        with self.store.read() as db:
            checkpoints=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM v4_checkpoints ORDER BY rowid DESC')]
            events=[dict(r) for r in db.execute("SELECT * FROM audit WHERE action LIKE 'MODEL_%' ORDER BY id DESC LIMIT 100")]
        from .volume_scenario import MODEL_VERSION as VOLUME_MODEL
        simulation=self.resolve(VOLUME_MODEL)
        simulation.require_integrity()
        return dict(active=e.version,simulation_model=simulation.version,simulation_manifest=simulation.manifest,versions=[dict(version=e.version,active=True,frozen=True,integrity=integrity,error=error,manifest_sha256=digest(e.manifest),parent=self.frozen.version,origin='primary_joint_operating_model',status='active',report=None,compatibility={},holdouts=[]),dict(version=self.frozen.version,active=False,frozen=True,integrity=True,error=None,manifest_sha256=digest(self.frozen.manifest),parent=None,origin='historical_archive',status='archived',report=None,compatibility={},holdouts=[])],checkpoints=checkpoints,events=events,
            protocol='POST_TEST_DEVELOPMENT_ITERATION',manifest=e.manifest,
            note='JOINT là model mặc định cho ca mới và dữ liệu POS nhập. Quy mô cơ sở đã cập nhật; không có chế độ ×1/×10 riêng. Mỗi ca ghim model/hash; bản V4 cũ chỉ phục vụ lịch sử.')
    def checkpoint(self,reason):
        if len(reason.strip())<3:raise ValueError('Cần lý do tạo snapshot.')
        with self.lock:
            active=self.active();active.require_integrity();ident=uuid.uuid4().hex;target=self.root/ident;target.mkdir()
            for rel,h in active.manifest['native_model_hashes'].items():
                p=target/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,p)
            payload=dict(id=ident,model_version=active.version,created=datetime.now(timezone.utc).isoformat(),actor=actor.get()['username'],reason=reason,hashes=active.manifest['native_model_hashes'])
            with self.store.connect() as db:
                db.execute('INSERT INTO v4_checkpoints VALUES(?,?)',(ident,json.dumps(payload)))
                db.execute('INSERT INTO audit(action,detail) VALUES(?,?)',('MODEL_CHECKPOINT',json.dumps(payload)))
            return self.registry()
    def rollback(self,expected_active,reason,checkpoint_id=None):
        active=self.active()
        if expected_active!=active.version or len(reason.strip())<3:raise ValueError('Cần đúng phiên bản active và lý do khôi phục.')
        with self.lock:
            with self.store.read() as db:
                row=db.execute('SELECT payload FROM v4_checkpoints WHERE id=?',(checkpoint_id,)).fetchone() if checkpoint_id else db.execute('SELECT payload FROM v4_checkpoints ORDER BY rowid DESC LIMIT 1').fetchone()
            if row is None:raise ValueError('Tạo snapshot V4 nguyên vẹn trước khi khôi phục.')
            snap=json.loads(row['payload']);target=self.root/snap['id']
            if snap['hashes']!=active.manifest['native_model_hashes']:raise ValueError('Snapshot không khớp model đang dùng.')
            for rel,h in snap['hashes'].items():
                if hashlib.sha256((target/rel).read_bytes()).hexdigest()!=h:raise ValueError('Snapshot hỏng: '+rel)
            for rel in snap['hashes']:
                p=ROOT/rel;temp=p.with_suffix(p.suffix+'.restore');shutil.copyfile(target/rel,temp);temp.replace(p)
            active.require_integrity();active.reload_if_needed()
            with self.store.connect() as db:db.execute('INSERT INTO audit(action,detail) VALUES(?,?)',('MODEL_ROLLBACK',json.dumps(dict(checkpoint=snap['id'],from_version=active.version,to_version=active.version,reason=reason,actor=actor.get(),verified_hashes=snap['hashes']))))
        return self.registry()

def demo_data(kind,skus):raise ValueError('V4 đã khóa; không sinh data huấn luyện cũ trong ứng dụng.')

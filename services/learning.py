"""Auditable local training, chronological evaluation and explicit model promotion."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import io
import json
import math
import threading
import uuid
import zipfile
import lightgbm as lgb
import numpy as np
import pandas as pd
from .engine import ROOT, Engine, encode, LADDER, CAPS, FLOORS, OUTCOME_FEATURES, outcome_features
from .ingestion import tables, integer, MAX_BYTES

WEATHER = ['forecast_rain_mm_previous_day1', 'forecast_temperature_max_c_previous_day1',
           'is_public_holiday', 'is_festival_non_public', 'issued_at']
DAILY = ['date', 'sku_code', 'prepared_qty', 'sold_qty', 'waste_qty', 'stockout', 'discounted_qty'] + WEATHER
PROMO = ['date', 'sku_code', 'slot', 'discount_pct', 'incremental_promo_qty',
         'measurement_method', 'experiment_id'] + WEATHER


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def weather(row):
    d = date.fromisoformat(row['date'])
    return {**{k: row[k] for k in WEATHER if k != 'issued_at'}, 'weekday_iso': d.isoweekday(),
            'is_weekend': int(d.weekday() >= 5), 'month': d.month, 'day_of_year': d.timetuple().tm_yday}


class Learning:
    def __init__(self, store, frozen, directory=None):
        self.store, self.frozen = store, frozen
        self.root = Path(directory or ROOT / 'runtime/learning')
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.cache = {frozen.version: frozen}
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS learning_rows(kind TEXT, origin TEXT, row_key TEXT, payload TEXT,
                    PRIMARY KEY(kind,origin,row_key));
                CREATE TABLE IF NOT EXISTS learning_datasets(id TEXT PRIMARY KEY, report TEXT);
                CREATE TABLE IF NOT EXISTS learning_runs(id TEXT PRIMARY KEY, report TEXT);
                CREATE TABLE IF NOT EXISTS model_active(id INTEGER PRIMARY KEY CHECK(id=1), version TEXT);
            ''')

    def resolve(self, version):
        if version not in self.cache:
            if not version.startswith('learn-') or not version.removeprefix('learn-').isalnum():
                raise ValueError('Phiên bản model không hợp lệ.')
            try:
                self.cache[version] = Engine(self.root / version)
            except OSError:
                raise ValueError('Không tìm thấy đầy đủ artifact của phiên bản model.') from None
        return self.cache[version]

    def active(self):
        with self.store.connect() as db:
            row = db.execute('SELECT version FROM model_active WHERE id=1').fetchone()
        return self.resolve(row['version']) if row else self.frozen

    def rows(self, kind, origin):
        with self.store.connect() as db:
            return [json.loads(r['payload']) for r in db.execute(
                'SELECT payload FROM learning_rows WHERE kind=? AND origin=? ORDER BY row_key', (kind, origin))]

    def history_before(self, day):
        return {(r['date'], r['sku_code']): r['sold_qty'] for r in self.rows('m2', 'real') if r['date'] < day}

    def outcomes_before(self,day):
        return {(r['date'],r['sku_code']):r for r in self.rows('m2','real') if r['date']<day}

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
                    raise ValueError('SKU chưa có trong danh mục V9; cần quy trình thêm SKU riêng.')
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
        if s['phase'] != 'closed' or s['mode'] != 'live' or s.get('minute') != 1320:
            raise ValueError('Chỉ thu kết quả từ ca dữ liệu thật đã chốt.')
        records = []
        for sku, p in s['products'].items():
            records.append({'date': s['day'], 'sku_code': sku, 'prepared_qty': p['prepared'], 'sold_qty': p['sold'],
                            'waste_qty': p['stock'], 'stockout': int(p['stock'] == 0),
                            'discounted_qty': sum(t['qty'] for t in s['ledger'] if t['sku'] == sku and t['discount'] > 0),
                            **{k: s['weather'].get(k) for k in WEATHER}})
        if any(r['issued_at'] is None for r in records):
            raise ValueError('Ca thiếu thời điểm phát hành dự báo; bổ sung qua tệp kết quả thực tế.')
        return self.ingest('closed-' + s['id'] + '.csv', pd.DataFrame(records).to_csv(index=False).encode(), 'm2', 'real', True)

    def status(self):
        active = self.active()
        with self.store.connect() as db:
            counts = [dict(r) for r in db.execute('SELECT kind,origin,COUNT(*) AS rows FROM learning_rows GROUP BY kind,origin')]
            runs = [json.loads(r['report']) for r in db.execute('SELECT report FROM learning_runs ORDER BY rowid DESC LIMIT 30')]
            datasets = [json.loads(r['report']) for r in db.execute('SELECT report FROM learning_datasets ORDER BY rowid DESC LIMIT 20')]
            events = [dict(r) for r in db.execute('SELECT id,action,detail,created FROM audit WHERE session_id IS NULL ORDER BY id DESC LIMIT 30')]
        return {'active': active.version, 'frozen': self.frozen.version, 'counts': counts, 'runs': runs, 'datasets': datasets, 'events': events,
                'minimum_days': {'m2': 63, 'm1': 42}, 'trained_until': active.manifest.get('trained_until', '2022-08-15')}

    def train(self, kind, origin='real'):
        if kind not in ['m1', 'm2'] or origin not in ['real', 'demo']:
            raise ValueError('Loại huấn luyện không hợp lệ.')
        if not self.lock.acquire(blocking=False):
            raise ValueError('Đang có một lần huấn luyện hoặc đổi model; thử lại khi hoàn tất.')
        try:
            parent, rows = (self.frozen if origin == 'demo' else self.active()), self.rows(kind, origin)
            dates = sorted({r['date'] for r in rows})
            minimum = 63 if kind == 'm2' else 42
            if len(dates) < minimum:
                raise ValueError(f'{kind.upper()} cần ít nhất {minimum} ngày khác nhau; hiện có {len(dates)}. Không bịa dữ liệu để train.')
            fingerprint = digest({'rows': rows, 'parent': parent.version, 'kind': kind, 'origin': origin, 'recipe': 2})
            with self.store.connect() as db:
                prior = [json.loads(r['report']) for r in db.execute('SELECT report FROM learning_runs')]
            same = next((r for r in prior if r.get('fingerprint') == fingerprint), None)
            if same:
                if same['status'] == 'promoted':
                    raise ValueError('Báo cáo này đã được áp dụng trước đó. Sau rollback, cần dữ liệu kiểm tra mới để đánh giá lại.')
                return same
            test_start, calibration_start = dates[-7], dates[-14]
            if test_start <= parent.manifest.get('trained_until', '2022-08-15'):
                raise ValueError('Holdout phải nằm sau dữ liệu model hiện tại đã học/đánh giá. Cần dữ liệu thực tế mới hơn.')
            previous_tests = [r['evaluated_until'] for r in prior if r['kind'] == kind and r['origin'] == origin]
            if previous_tests and test_start <= max(previous_tests):
                raise ValueError('Cần 7 ngày kiểm tra mới chưa dùng trong lần đánh giá trước. Không lặp holdout để chọn model.')
            if kind == 'm2':
                expected = {s for s in parent.master}
                by_day = {d: {r['sku_code'] for r in rows if r['date'] == d} for d in dates}
                if any(v != expected for v in by_day.values()) or any((date.fromisoformat(b) - date.fromisoformat(a)).days != 1 for a, b in zip(dates, dates[1:])):
                    raise ValueError('M2 cần ngày liên tục và đủ 8 SKU mỗi ngày để dựng lag đúng.')
            features, targets, meta, visible = [], [], [], {}
            outcomes={(r['date'],r['sku_code']):r for r in rows} if kind=='m2' else {}
            for row in sorted(rows, key=lambda r: (r['date'], r['sku_code'])):
                d, sku, w = row['date'], row['sku_code'], weather(row)
                if kind == 'm2':
                    f = parent.features(d, sku, visible, w,outcomes)
                    f.update(outcome_features(d,sku,outcomes))
                    visible[(d, sku)] = row['sold_qty']
                    if not row['eligible'] or f['history_days'] < 35:
                        continue
                    y = row['sold_qty']
                else:
                    f = {'sku_code': sku, 'slot': row['slot'], 'discount_pct': row['discount_pct'],
                         'weekday': w['weekday_iso'], 'is_weekend': w['is_weekend'], 'is_holiday': w['is_public_holiday'],
                         'rain_jma': w[WEATHER[0]], 'temp_jma': w[WEATHER[1]]}
                    y = row['incremental_promo_qty']
                features.append(f)
                targets.append(y)
                meta.append(row)
            splits = [np.array([r['date'] < calibration_start for r in meta]),
                      np.array([calibration_start <= r['date'] < test_start for r in meta]),
                      np.array([r['date'] >= test_start for r in meta])]
            for label, mask in zip(['train', 'calibration', 'test'], splits):
                for sku in parent.master:
                    if sum(bool(m) and r['sku_code'] == sku for r, m in zip(meta, mask)) < (10 if label == 'train' else 5):
                        raise ValueError(f'{label}: {sku} chưa đủ quan sát không bị giới hạn tồn kho.')
                if kind == 'm1':
                    required = {(s, j, t) for s in parent.master for j in range(5) for t in LADDER if FLOORS[j] <= t <= CAPS[j]}
                    available = {(r['sku_code'], r['slot'], r['discount_pct']) for r, m in zip(meta, mask) if m}
                    if not required <= available:
                        raise ValueError(label + ': M1 thiếu độ phủ SKU/slot/mức giảm hợp lệ; chưa đủ bằng chứng học phản ứng giá.')
            cols = list(parent.manifest['COLS' if kind == 'm2' else 'MCOLS'])
            if kind=='m2':
                cols += [n for n in OUTCOME_FEATURES if n not in cols]
            X, y = encode(features, cols), np.asarray(targets, dtype=float)
            parent_X=encode(features,parent.manifest['COLS' if kind=='m2' else 'MCOLS'])
            train_mask, calibration_mask, test_mask = splits
            parameters = {'objective': 'regression_l1', 'verbosity': -1, 'num_threads': 2,
                               'num_leaves': 7, 'min_data_in_leaf': 8, 'learning_rate': .05,
                               'seed': 42, 'deterministic': True, 'force_col_wise': True}
            model = lgb.train(parameters,
                              lgb.Dataset(X[train_mask], label=y[train_mask], feature_name=cols), num_boost_round=160)
            version = 'learn-' + uuid.uuid4().hex
            directory = self.root / version
            directory.mkdir()
            snapshot = directory / 'training_data.json'
            snapshot.write_text(json.dumps(rows, sort_keys=True, allow_nan=False), encoding='utf-8')
            manifest = deepcopy(parent.manifest)
            if kind=='m2':
                manifest['COLS']=cols
                manifest['M2FEATURES']=list(dict.fromkeys(manifest.get('M2FEATURES',[])+OUTCOME_FEATURES))
            manifest.update(version=version, parent=parent.version, trained_until=max(dates[-1], parent.manifest.get('trained_until', '2022-08-15')),
                            evaluated_until=dates[-1], training_fingerprint=fingerprint, learning_kind=kind)
            manifest['training_data_sha256'] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            manifest['trainer'] = {'lightgbm': lgb.__version__, 'numpy': np.__version__, 'recipe': 2,
                                   'parameters': parameters, 'boost_rounds': 160}
            model.save_model(str(directory / (kind + '.txt')))
            (parent.m1 if kind == 'm2' else parent.m2).save_model(str(directory / ('m1.txt' if kind == 'm2' else 'm2.txt')))
            if kind == 'm2':
                predictions = np.maximum(0, model.predict(X[calibration_mask], num_threads=2))
                residuals = {s: [] for s in parent.master}
                for row, actual, pred in zip([r for r, m in zip(meta, calibration_mask) if m], y[calibration_mask], predictions):
                    residuals[row['sku_code']].append(float(actual - pred))
                q = parent.selection['selected_q']
                for entry in manifest['residual_offsets']:
                    if entry['key'][0] == q:
                        entry['value'] = max(0., float(np.quantile(residuals[entry['key'][1]], q)))
            else:
                grouped = {}
                for row, m in zip(meta, train_mask):
                    if m:
                        grouped.setdefault((row['sku_code'], row['slot'], row['discount_pct']), []).append(row['incremental_promo_qty'])
                for entry in manifest['emp']:
                    key = tuple(entry['key'])
                    if key in grouped:
                        entry['value'] = float(np.mean(grouped[key]))
                    elif key[2] < FLOORS[key[1]]:
                        # Illegal lower tiers must not propagate stale uplift through monotonic accumulation.
                        entry['value'] = 0.
            manifest['native_model_hashes'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ['m1.txt', 'm2.txt']}
            (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            candidate = Engine(directory)
            test_rows = [r for r, m in zip(meta, test_mask) if m]
            if kind == 'm2':
                old_pred = np.maximum(0, parent.m2.predict(parent_X[test_mask], num_threads=2))
                new_pred = np.maximum(0, candidate.m2.predict(X[test_mask], num_threads=2))
                naive = np.array([f['lag7_sales'] for f, m in zip(features, test_mask) if m])
            else:
                def response(engine, observations=test_rows):
                    cache = {}
                    result = []
                    for row in observations:
                        key = (row['date'], row['sku_code'])
                        if key not in cache:
                            cache[key] = engine.promo(row['sku_code'], weather(row))
                        result.append(cache[key][row['slot'], LADDER.index(row['discount_pct'])])
                    return np.asarray(result)
                old_pred, new_pred = response(parent), response(candidate)
                naive = np.array([parent.emp.get((r['sku_code'], r['slot'], r['discount_pct']), 0.) for r in test_rows])
            actual = y[test_mask]
            def metrics(pred, actual=actual, test_rows=test_rows):
                mae = float(np.mean(np.abs(pred - actual)))
                return {'mae': mae, 'wape_pct': float(np.abs(pred - actual).sum() / actual.sum() * 100) if actual.sum() > 0 else None,
                        'by_sku_mae': {s: float(np.mean(np.abs(pred[[r['sku_code'] == s for r in test_rows]] - actual[[r['sku_code'] == s for r in test_rows]]))) for s in parent.master}}
            old, new, baseline = metrics(old_pred), metrics(new_pred), metrics(naive)
            calibration_rows = [r for r, m in zip(meta, calibration_mask) if m]
            if kind == 'm2':
                old_cal = np.maximum(0, parent.m2.predict(parent_X[calibration_mask], num_threads=2))
                new_cal = np.maximum(0, candidate.m2.predict(X[calibration_mask], num_threads=2))
            else:
                old_cal, new_cal = response(parent, calibration_rows), response(candidate, calibration_rows)
            validation = {'current': metrics(old_cal, y[calibration_mask], calibration_rows),
                          'candidate': metrics(new_cal, y[calibration_mask], calibration_rows)}
            gates = {'mae_improves_at_least_5pct': new['mae'] < old['mae'] * .95,
                     'beats_naive': new['mae'] <= baseline['mae'] + 1e-8,
                     'no_sku_regression_over_10pct_or_half_unit': all(new['by_sku_mae'][s] <= old['by_sku_mae'][s] * 1.1 + .5 for s in parent.master)}
            if kind == 'm2':
                # Evaluate the actual proposed quantities, including buffer and preparation floor.
                quantities = []
                for eng, pred in [(parent, old_pred), (candidate, new_pred)]:
                    qties = []
                    for row, forecast in zip(test_rows, pred):
                        past = {(r['date'], r['sku_code']): r['sold_qty'] for r in rows if r['date'] < row['date']}
                        floor = 4 * math.ceil(eng.selection['selected_prep_floor'] * eng.baseline(row['date'], row['sku_code'], past) / 4)
                        qties.append(max(4, floor, 4 * math.ceil((forecast + eng.offsets[(eng.selection['selected_q'], row['sku_code'])]) / 4)))
                    residual = actual - np.asarray(qties)
                    quantities.append(float(np.mean(np.maximum(.85 * residual, -.15 * residual))))
                old['prepared_pinball_loss'], new['prepared_pinball_loss'] = quantities
                gates['preparation_loss_no_regression'] = quantities[1] <= quantities[0] * 1.05 + .1
            report = {'id': version, 'kind': kind, 'origin': origin, 'parent': parent.version, 'fingerprint': fingerprint,
                      'evaluated_until': dates[-1], 'train_until': max(r['date'] for r, m in zip(meta, train_mask) if m),
                      'calibration_from': calibration_start, 'test_from': test_start, 'test_rows': len(test_rows),
                      'training_rows': int(train_mask.sum()), 'excluded_rows': len(rows) - len(meta),
                      'current': old, 'candidate': new, 'naive': baseline, 'validation': validation, 'gates': gates,
                      'passed': all(gates.values()), 'status': 'awaiting_confirmation' if all(gates.values()) and origin == 'real' else 'demo_only' if origin == 'demo' else 'rejected',
                      'limitation': 'Offline errors on observed outcomes; not proof of profit or counterfactual policy improvement.'}
            (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            with self.store.connect() as db:
                db.execute('INSERT INTO learning_runs VALUES (?,?)', (version, json.dumps(report)))
                db.execute('INSERT INTO audit(action,detail) VALUES (?,?)', ('MODEL_TRAIN_EVALUATE', json.dumps(report)))
            return report
        finally:
            self.lock.release()

    def promote(self, version, expected_active, reason):
        if not reason.strip():
            raise ValueError('Cần lý do xác nhận đổi model.')
        with self.lock:
            if not version.startswith('learn-') or not version.removeprefix('learn-').isalnum():
                raise ValueError('Chỉ được áp dụng phiên bản ứng viên đã đánh giá.')
            self.resolve(version)  # validate the version name before constructing a filesystem path
            candidate = Engine(self.root / version)  # recheck hashes even if a preview was cached
            snapshot = self.root / version / 'training_data.json'
            if not snapshot.exists() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != candidate.manifest.get('training_data_sha256'):
                raise ValueError('Checksum dữ liệu huấn luyện không khớp.')
            with self.store.connect() as db:
                row = db.execute('SELECT report FROM learning_runs WHERE id=?', (version,)).fetchone()
                if not row:
                    raise ValueError('Không có báo cáo đánh giá model.')
                report = json.loads(row['report'])
                active_row = db.execute('SELECT version FROM model_active WHERE id=1').fetchone()
                active = active_row['version'] if active_row else self.frozen.version
                if active != expected_active or report['parent'] != active:
                    raise ValueError('Model đang dùng đã thay đổi; cần đánh giá lại trên parent mới.')
                if report['origin'] != 'real' or not report['passed'] or report['status'] != 'awaiting_confirmation':
                    raise ValueError('Model demo, không đạt hoặc đã xử lý không được đưa vào dùng thật.')
                report['status'] = 'promoted'
                db.execute('UPDATE learning_runs SET report=? WHERE id=?', (json.dumps(report), version))
                db.execute('INSERT INTO model_active VALUES (1,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version', (candidate.version,))
                db.execute('INSERT INTO audit(action,detail) VALUES (?,?)', ('MODEL_PROMOTE', json.dumps({'from': active, 'to': version, 'reason': reason})))
                self.cache[version] = candidate
        return self.status()


    def rollback(self, expected_active, reason):
        if not reason.strip():
            raise ValueError('Cần lý do quay về model trước.')
        with self.lock:
            active = self.active()
            if active.version != expected_active or active.version == self.frozen.version:
                raise ValueError('Model đã thay đổi hoặc đang ở bản gốc.')
            previous = self.resolve(active.manifest['parent'])
            with self.store.connect() as db:
                row = db.execute('SELECT version FROM model_active WHERE id=1').fetchone()
                if not row or row['version'] != expected_active:
                    raise ValueError('Model đang dùng đã thay đổi.')
                db.execute('UPDATE model_active SET version=? WHERE id=1', (previous.version,))
                db.execute('INSERT INTO audit(action,detail) VALUES (?,?)', ('MODEL_ROLLBACK', json.dumps({'from': active.version, 'to': previous.version, 'reason': reason})))
        return self.status()


def demo_data(kind, skus):
    """Synthetic fixtures for an explicitly requested demo, never a source of real labels."""
    rows = []
    for i in range(63 if kind == 'm2' else 42):
        d = date(2024, 1, 1) + timedelta(days=i)
        for sku in skus:
            base = {'date': d.isoformat(), 'sku_code': sku, 'forecast_rain_mm_previous_day1': 2,
                    'forecast_temperature_max_c_previous_day1': 28, 'is_public_holiday': 0,
                    'is_festival_non_public': 0, 'issued_at': (d-timedelta(days=1)).isoformat()+'T18:00:00+07:00'}
            if kind == 'm2':
                rows.append({**base, 'prepared_qty': 120, 'sold_qty': 80, 'waste_qty': 40, 'stockout': 0, 'discounted_qty': 0})
            else:
                for j in range(5):
                    for tier in LADDER:
                        if FLOORS[j] <= tier <= CAPS[j]:
                            rows.append({**base, 'slot': j, 'discount_pct': tier, 'incremental_promo_qty': 0,
                                         'measurement_method': 'controlled_increment', 'experiment_id': f'DEMO-{i}-{sku}-{j}-{tier}'})
    return pd.DataFrame(rows).to_csv(index=False).encode()

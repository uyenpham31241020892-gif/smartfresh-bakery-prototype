"""Approval boundaries, revision control, inventory and transaction accounting."""
from datetime import datetime, timezone, timedelta
import json
import hashlib
import uuid
from .engine import SLOTS, END, LADDER, FLOORS, CAPS


def now():
    return datetime.now(timezone(timedelta(hours=7))).isoformat()


class Workflow:
    def __init__(self, engine, simulator, store):
        self.engine, self.simulator, self.store = engine, simulator, store
        self.active_engine = lambda: self.engine
        self.version_engine = lambda version: self.engine
        self.observed_history = lambda day: {}
        self.observed_outcomes = lambda day: {}

    def create(self, day='2022-08-16', seed=42, mode='simulation', history=None, weather=None, source='V9 sample', identifier=None,auto_run=False,engine_version=None,apply_closed_history=True,outcome_snapshot=None):
        engine = self.version_engine(engine_version) if engine_version else self.active_engine()
        if identifier:
            try:return self.store.get(identifier)
            except ValueError:pass
        if day <= engine.manifest.get('trained_until', '2022-08-15'):
            raise ValueError('Ngày dự báo phải sau dữ liệu huấn luyện của model đang dùng: ' + engine.manifest.get('trained_until', '2022-08-15'))
        if day <= '2022-08-15':
            raise ValueError('Ngày vận hành phải sau thời điểm khóa huấn luyện 15/08/2022.')
        if mode not in ['simulation', 'live']:
            raise ValueError('Chế độ không hợp lệ.')
        weather = weather or self.simulator.calendar.get(day)
        if weather is None:
            raise ValueError('Cần tải dự báo thời tiết có thời điểm phát hành cho ngày mục tiêu.')
        known = self.observed_history(day) if mode == 'live' and history is None else {}
        visible = history if history is not None else known or self.simulator.history_before(day, seed=seed)
        visible = {k: v for k, v in visible.items() if k[0] < day}
        # Only closed local sessions released before the target date may override source history.
        outcomes=outcome_snapshot if outcome_snapshot is not None else self.observed_outcomes(day) if mode=='live' else {}
        closed=self.store.closed_before(day,mode,seed if mode=='simulation' else None) if apply_closed_history else []
        for old in closed:
            if old['day'] < day:
                for sku, p in old['products'].items():
                    visible[(old['day'], sku)] = p['sold']
                    outcomes[(old['day'],sku)]={'date':old['day'],'sku_code':sku,'prepared_qty':p['prepared'],'sold_qty':p['sold'],
                        'waste_qty':p['stock'],'stockout':int(p['stock']==0),'discounted_qty':sum(t['qty'] for t in old['ledger'] if t['sku']==sku and t['discount']>0)}
        outcomes={k:v for k,v in outcomes.items() if k[0]<day}
        previous_day=str((datetime.fromisoformat(day)-timedelta(days=1)).date())
        if 'lag1_waste_qty' in engine.manifest['COLS'] and any((previous_day,sku) not in outcomes for sku in engine.master):
            raise ValueError('Model M2 mới cần sổ kết quả bán/tồn hủy ngày trước cho đủ SKU; không tự coi dữ liệu thiếu là 0.')
        plans = engine.plan(day, visible, weather,outcomes)
        input_history = [{'date': d, 'sku': sku, 'sold': v} for (d, sku), v in sorted(visible.items())]
        input_outcomes=list(outcomes.values())
        input_hash = hashlib.sha256(json.dumps({'history': input_history, 'weather': weather,'outcomes':input_outcomes}, sort_keys=True).encode()).hexdigest()
        s = {'id': identifier or uuid.uuid4().hex, 'day': day, 'seed': seed, 'mode': mode, 'revision': 0,
             'minute': 360, 'phase': 'plan_pending', 'created': now(), 'model_version': engine.version,
             'input_hash': input_hash, 'input_history': input_history, 'model_hashes': engine.manifest['native_model_hashes'],
             'weather': weather, 'source': source, 'plan': plans, 'products': {}, 'ledger': [], 'decisions': [],
             'pending': None, 'keys': [], 'simulator_version': self.simulator.version if mode == 'simulation' else None,
             'simulator_hash':self.simulator.arrivals.hash if mode=='simulation' else None,'auto_run':bool(auto_run and mode=='simulation'),
             'input_outcomes':input_outcomes,'history_source':'uploaded_or_observed' if history is not None or known else 'seeded_demo_history',
             'day_context':{'lag1_day':str((datetime.fromisoformat(day)-timedelta(days=1)).date()),
                            'same_weekday_day':str((datetime.fromisoformat(day)-timedelta(days=7)).date()),
                            'past_closed_days':len(closed),'inventory_features_active':any('waste' in n for n in engine.manifest['COLS']),
                            'previous_day_outcomes':[r for (d,sku),r in outcomes.items() if d==str((datetime.fromisoformat(day)-timedelta(days=1)).date())]}}
        with self.store.connect() as db:
            existing = db.execute('SELECT state FROM sessions WHERE id=?', (s['id'],)).fetchone()
            if existing:
                return json.loads(existing['state'])
            self.store.save(db, s, 'M2_PROPOSED', {'model': engine.version, 'source': source, 'input_hash': input_hash})
        return s

    def fork_simulation(self,sid):
        old=self.store.get(sid)
        history={(r['date'],r['sku']):r['sold'] for r in old['input_history']}
        return self.create(day=old['day'],seed=old['seed'],mode='simulation',history=history,weather=old['weather'],
                           source='Mô phỏng riêng từ ca '+sid,auto_run=True,engine_version=old['model_version'],apply_closed_history=False,
                           outcome_snapshot={(r['date'],r['sku_code']):r for r in old.get('input_outcomes',[])})

    def next_day(self,sid,weather=None):
        old=self.store.get(sid)
        if old['phase']!='closed':
            raise ValueError('Cần chốt ngày hiện tại trước khi lập kế hoạch hôm sau.')
        day=str((datetime.fromisoformat(old['day'])+timedelta(days=1)).date())
        history={(r['date'],r['sku']):r['sold'] for r in old['input_history']}
        for sku,p in old['products'].items():
            history[(old['day'],sku)]=p['sold']
        return self.create(day=day,seed=old['seed'],mode=old['mode'],history=history,weather=weather,
                           source='Kế hoạch sau chốt ca '+sid,auto_run=old.get('auto_run',False),identifier='next-'+sid)

    def mutate(self, sid, revision, action, payload=None, key=None):
        payload = payload or {}
        with self.store.connect() as db:
            row = db.execute('SELECT state FROM sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                raise ValueError('Không tìm thấy ca vận hành.')
            s = json.loads(row['state'])
            if key and key in s['keys']:
                return s
            if s['revision'] != revision:
                raise ValueError('Dữ liệu đã thay đổi. Hãy tải lại trước khi xác nhận.')
            if s['phase'] == 'closed':
                raise ValueError('Ngày đã chốt; hãy tạo ca mới.')
            getattr(self, 'do_' + action)(s, payload)
            s['revision'] += 1
            if key:
                s['keys'] = (s['keys'] + [key])[-100:]
            self.assert_accounts(s)
            self.store.save(db, s, action.upper(), {'payload': payload, 'revision': s['revision'], 'at': now()})
        return s

    def do_plan_approve(self, s, payload):
        if s['phase'] != 'plan_pending':
            raise ValueError('Kế hoạch không ở trạng thái chờ duyệt.')
        overrides = payload.get('quantities', {})
        if set(overrides) - {p['sku'] for p in s['plan']}:
            raise ValueError('SKU không hợp lệ.')
        for p in s['plan']:
            qty = overrides.get(p['sku'], p['prepared'])
            if type(qty) is not int or qty < max(4, p['floor']) or qty % 4 or qty > 100000:
                raise ValueError(f"{p['sku']}: số lượng phải là bội số 4 và không nhỏ hơn sàn {p['floor']}.")
            if qty != p['prepared'] and not payload.get('reason', '').strip():
                raise ValueError('Cần lý do khi điều chỉnh sản lượng.')
            p['approved'] = qty
        s['phase'] = 'plan_approved'

    def do_plan_reject(self, s, payload):
        if s['phase'] != 'plan_pending' or not payload.get('reason', '').strip():
            raise ValueError('Cần kế hoạch chờ duyệt và lý do từ chối.')
        s['phase'] = 'plan_rejected'

    def do_prepared(self, s, payload):
        if s['phase'] != 'plan_approved':
            raise ValueError('Hãy duyệt kế hoạch trước khi xác nhận chuẩn bị.')
        for p in s['plan']:
            s['products'][p['sku']] = {'name': p['name'], 'price': p['price'], 'forecast': p['forecast'],
                'prepared': p['approved'], 'stock': p['approved'], 'sold': 0, 'revenue': 0, 'discount': 0, 'lost': 0}
        s['phase'] = 'running'

    def proposals(self, s):
        j = max(i for i,t in enumerate(SLOTS) if t<=s['minute'])
        if s['mode']=='live' and not s['ledger'] and not s.get('confirmed_zero_sales'):
            return {'id':uuid.uuid4().hex,'minute':SLOTS[j],'as_of_minute':s['minute'],'rows':[],
                    'status':'missing_data','blocked_reason':'Chưa có nguồn giao dịch. Không được coi thiếu dữ liệu là bán bằng 0.','created':now()}
        rows = []
        for sku, p in s['products'].items():
            times = [(tx['minute'], tx['qty']) for tx in s['ledger'] if tx['sku'] == sku]
            s30 = sum(q for t, q in times if s['minute']-30<=t<=s['minute'])
            s60 = sum(q for t, q in times if s['minute']-60<=t<=s['minute'])
            rows.append(self.version_engine(s['model_version']).price(sku, j, p['stock'], p['prepared'], p['discount'], s30, s60, p['forecast'], s['weather'],as_of=s['minute']))
        return {'id': uuid.uuid4().hex, 'minute': SLOTS[j], 'as_of_minute':s['minute'],'rows': rows, 'status': 'pending', 'created': now()}

    def consume(self,s,destination):
        if s['mode']!='simulation':
            return
        if s.get('simulator_hash') and s['simulator_hash']!=self.simulator.arrivals.hash:
            raise ValueError('Artifact mô phỏng đã đổi; cần tạo ca mới để tránh thay nguồn lượt mua giữa ngày.')
        for ev in self.simulator.events(s['day'],s['seed'],s['weather'],s.get('simulator_version','new_seeded_demo_v1')):
            if not s['minute']<=ev['minute']<destination:
                continue
            p=s['products'][ev['sku']]
            if ev['promo'] and (ev['required']>p['discount'] or ev['draw']>.6):
                continue
            if p['stock']:
                self.sale(s,ev['sku'],ev['minute'],1,'SIMULATED')
            else:
                p['lost']+=1

    def do_tick(self,s,payload):
        if s['mode']!='simulation' or s['phase'] not in ['running','price_pending','price_approved']:
            raise ValueError('Chỉ chạy đồng hồ bán tự động trong ca mô phỏng đã chuẩn bị.')
        target=payload.get('target')
        if type(target) is not int or not s['minute']<target<=END:
            raise ValueError('Mốc đồng hồ không hợp lệ.')
        future=[t for t in SLOTS+[END] if s['minute']<t<=target]
        destination=future[0] if future else target
        had_pending=s['pending'] is not None
        self.consume(s,destination)
        s['minute']=destination
        if destination==END:
            if s['pending']:
                s['pending']['status']='expired'
                s['decisions'].append(s['pending'])
            s['pending']=None;s['phase']='close_pending'
        elif destination>=SLOTS[0] and (destination in SLOTS or had_pending):
            s['pending']=self.proposals(s);s['phase']='price_pending'

    def do_advance(self, s, payload):
        if s['phase'] != 'running':
            raise ValueError('Cần hoàn tất bước xác nhận đang chờ trước khi chuyển thời gian.')
        target = payload.get('target', s['minute'] + 30)
        if type(target) is not int or not s['minute'] < target <= END:
            raise ValueError('Thời gian đích không hợp lệ.')
        future = [t for t in SLOTS if s['minute'] < t <= target]
        destination = future[0] if future else target
        self.consume(s,destination)
        s['minute'] = destination
        if destination in SLOTS:
            s['pending'] = self.proposals(s)
            s['phase'] = 'price_pending'
        elif destination == END:
            s['phase'] = 'close_pending'

    def do_price_approve(self, s, payload):
        if s['phase'] != 'price_pending' or payload.get('proposal_id') != s['pending']['id']:
            raise ValueError('Đề xuất đã hết hiệu lực hoặc không còn chờ duyệt.')
        if s['pending'].get('status')=='missing_data' or s['mode']=='live' and not s['ledger'] and not s.get('confirmed_zero_sales'):
            raise ValueError('Cần nạp giao dịch hoặc xác nhận thực tế chưa có bán; không duyệt giá từ dữ liệu thiếu.')
        overrides = payload.get('discounts', {})
        if set(overrides) - set(s['products']):
            raise ValueError('SKU không hợp lệ.')
        for p in s['pending']['rows']:
            tier = overrides.get(p['sku'], p['discount'])
            if type(tier) is not int or tier not in LADDER or not max(p['previous'], p['floor']) <= tier <= p['cap']:
                raise ValueError(f"{p['sku']}: mức giảm phải tuân thủ thang giá, sàn, trần và không giảm ngược.")
            if tier != p['discount'] and not payload.get('reason', '').strip():
                raise ValueError('Cần lý do khi điều chỉnh mức giảm.')
            p['approved'] = tier
        s['pending']['status'] = 'approved'
        s['phase'] = 'price_approved'

    def do_price_reject(self, s, payload):
        if s['phase'] != 'price_pending' or payload.get('proposal_id') != s['pending']['id'] or not payload.get('reason', '').strip():
            raise ValueError('Cần đề xuất hiện tại và lý do từ chối.')
        if any(p['previous'] < p['floor'] for p in s['pending']['rows']):
            raise ValueError('Giá hiện tại vi phạm sàn từ 21:00. Hãy điều chỉnh về mức hợp lệ rồi xác nhận.')
        s['pending']['status'] = 'rejected'
        s['decisions'].append(s['pending'])
        s['pending'] = None
        s['phase'] = 'running'

    def do_price_apply(self, s, payload):
        if s['phase'] != 'price_approved' or payload.get('proposal_id') != s['pending']['id']:
            raise ValueError('Cần duyệt đề xuất trước khi áp dụng.')
        for p in s['pending']['rows']:
            s['products'][p['sku']]['discount'] = p['approved']
        s['pending']['status'] = 'applied'
        s['pending']['applied_at'] = now()
        s['decisions'].append(s['pending'])
        s['pending'] = None
        s['phase'] = 'running'

    def sale(self, s, sku, minute, qty, origin):
        p = s['products'][sku]
        if qty > p['stock']:
            raise ValueError(f'{sku}: số lượng bán vượt tồn.')
        paid = int(round(p['price'] * (1 - p['discount'] / 100)))
        s['ledger'].append({'sku': sku, 'minute': minute, 'qty': qty, 'discount': p['discount'],
                            'unit_price': paid, 'paid': paid * qty, 'origin': origin})
        p['stock'] -= qty
        p['sold'] += qty
        p['revenue'] += paid * qty

    def do_sales(self, s, payload):
        if s['mode'] != 'live' or s['phase'] not in ['running', 'price_pending', 'price_approved']:
            raise ValueError('Giao dịch nhập chỉ dành cho ca dữ liệu nhập đang hoạt động.')
        rows = payload.get('rows', [])
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
            raise ValueError('Cần từ 1 đến 20.000 dòng giao dịch.')
        for tx in rows:
            if not isinstance(tx, dict) or not {'sku_code', 'minute', 'quantity'} <= set(tx):
                raise ValueError('Giao dịch thiếu SKU, phút hoặc số lượng.')
            sku, minute, qty = tx['sku_code'], tx['minute'], tx['quantity']
            if sku not in s['products'] or type(qty) is not int or qty <= 0 or qty > 100000 or type(minute) is not int or minute != s['minute']:
                raise ValueError('Giao dịch phải có SKU hợp lệ, số nguyên dương và đúng phút hiện tại; không ghi ngược thời gian.')
            self.sale(s, sku, minute, qty, 'UPLOADED')
        if s['pending']:
            s['pending'] = self.proposals(s)
            s['phase'] = 'price_pending'

    def do_confirm_zero_sales(self,s,payload):
        if s['mode']!='live' or s['ledger'] or not payload.get('confirmed') or not payload.get('reason','').strip():
            raise ValueError('Cần xác nhận có lý do rằng thực tế chưa có lượt bán; chỉ dành cho ca live chưa có giao dịch.')
        s['confirmed_zero_sales']=True
        if s['pending']:
            s['pending']=self.proposals(s);s['phase']='price_pending'

    def do_close(self, s, payload):
        if s['phase'] != 'close_pending' or s['minute'] != END:
            raise ValueError('Chỉ chốt ngày khi đã xử lý đủ các mốc và đến 22:00.')
        s['phase'] = 'closed'
        s['closed'] = now()

    @staticmethod
    def assert_accounts(s):
        for sku, p in s['products'].items():
            tx = [t for t in s['ledger'] if t['sku'] == sku]
            if p['prepared'] != p['stock'] + p['sold'] or p['stock'] < 0 or p['revenue'] != sum(t['paid'] for t in tx) or p['sold'] != sum(t['qty'] for t in tx):
                raise ValueError('Đối soát tồn hoặc doanh thu thất bại.')

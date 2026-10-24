"""Approval boundaries, revision control, inventory and transaction accounting."""
from datetime import datetime, timezone, timedelta
import json
import hashlib
import uuid
from .quality import build_snapshot, sales_quality, digest
from .safety import Safety, GuardError
from .identity import request_trace,actor,AccessError
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
        self.safety = Safety(store,lambda version: self.version_engine(version) if version else self.active_engine())

    def create(self, day='2022-07-01', seed=42, mode='simulation', history=None, weather=None, source='V606 TEST-DATE busy synthetic 4x ASSUMED; not official private market', identifier=None,auto_run=False,engine_version=None,apply_closed_history=True,outcome_snapshot=None,provenance=None,operation_mode="assisted",market_version=None):
        engine = self.version_engine(engine_version) if engine_version else self.active_engine()
        market_version=market_version or self.simulator.version
        market_hash=self.simulator.hash_for(market_version) if hasattr(self.simulator,'hash_for') else self.simulator.arrivals.hash
        if identifier:
            try:return self.store.get(identifier)
            except ValueError:pass
        cutoff=engine.manifest.get('trained_until','2022-08-15')
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_holdouts'").fetchone():
                periods=[json.loads(r['report'])['through'] for r in db.execute('SELECT report FROM model_holdouts WHERE version=?',(engine.version,))]
                cutoff=max([cutoff]+periods)
        if day <= cutoff:
            raise ValueError('Ngày dự báo phải sau dữ liệu huấn luyện/đánh giá model: ' + cutoff)
        if day <= '2022-06-30':
            raise ValueError('Ngày vận hành phải sau thời điểm khóa huấn luyện 15/08/2022.')
        if mode not in ['simulation', 'live']:
            raise ValueError('Chế độ không hợp lệ.')
        trusted_demo_weather = weather is None
        weather = weather or self.simulator.calendar.get(day)
        if weather is None:
            raise ValueError('Cần tải dự báo thời tiết có thời điểm phát hành cho ngày mục tiêu.')
        if weather == self.simulator.calendar.get(day):
            trusted_demo_weather = True
        weather=dict(weather)
        from .clearance import SCENARIO
        if mode=='simulation' and market_version==SCENARIO:
            weather['price_response_scenario']=SCENARIO
        else:
            weather.pop('price_response_scenario',None)
        if not getattr(engine,'legacy',True) and mode=='live' and weather.get('weather_provenance',{}).get('vintage_verified') is False:
            raise ValueError('Thời tiết reanalysis chỉ dùng mô phỏng; vận hành thật cần forecast có issued_at trước quyết định.')
        known = self.observed_history(day) if mode == 'live' and history is None else {}
        visible = history if history is not None else known or self.simulator.history_before(day, seed=seed)
        if any(k[0] >= day for k in visible):
            raise ValueError('Data leakage: lịch sử hiện tại/tương lai bị chặn, không tự bỏ qua.')
        visible = dict(visible)
        # Only closed local sessions released before the target date may override source history.
        outcomes=outcome_snapshot if outcome_snapshot is not None else self.observed_outcomes(day) if mode=='live' else {}
        closed=self.store.closed_before(day,mode,seed if mode=='simulation' else None) if apply_closed_history else []
        if mode=='simulation':
            closed=[s for s in closed if s.get('simulator_version')==market_version and s.get('simulator_hash')==market_hash]
        for old in closed:
            if old['day'] < day:
                for sku, p in old['products'].items():
                    visible[(old['day'], sku)] = p['sold']
                    outcomes[(old['day'],sku)]={'date':old['day'],'sku_code':sku,'prepared_qty':p['prepared'],'sold_qty':p['sold'],
                        'waste_qty':p['stock'],'stockout':int(p['stock']==0),'discounted_qty':sum(t['qty'] for t in old['ledger'] if t['sku']==sku and t['discount']>0),
                        'observation_scale':4 if old['mode']=='simulation' and old.get('simulator_version','').startswith('V606_busy4') else 1,
                        'sold_to_2130':sum(t['qty'] for t in old['ledger'] if t['sku']==sku and t['minute']<1290),
                        'source_session_id':old['id']}
        outcomes={k:v for k,v in outcomes.items() if k[0]<day}
        previous_day=str((datetime.fromisoformat(day)-timedelta(days=1)).date())
        if 'lag1_waste_qty' in engine.manifest['COLS'] and any((previous_day,sku) not in outcomes for sku in engine.master):
            raise ValueError('Model M2 mới cần sổ kết quả bán/tồn hủy ngày trước cho đủ SKU; không tự coi dữ liệu thiếu là 0.')
        lineage = dict(provenance or {'type':'bundled_demo' if history is None and not known else 'session_or_observed',
                                     'source':source, 'availability':'date_only_unverified'})
        lineage['history_origin'] = 'provided_history' if history is not None else 'observed_local_history' if known else 'seeded_synthetic_demo'
        lineage['weather_origin'] = 'bundled_V606_lagged_reanalysis' if trusted_demo_weather else 'provided_forecast_declared_timestamps'
        lineage['closed_session_ids'] = [c['id'] for c in closed]
        lineage['seed'] = seed if mode=='simulation' else None
        # Validate before model invocation; features are computed deterministically, then bound to the snapshot.
        feature_rows = [{'sku':sku,'features':engine.features(day,sku,visible,weather,outcomes)} for sku in engine.master]
        quality = build_snapshot(day,visible,weather,engine,feature_rows,outcomes,lineage,trusted_demo_weather)
        identifier = identifier or uuid.uuid4().hex
        if operation_mode not in ['assisted','shadow','manual']:raise ValueError('Chế độ vận hành không hợp lệ.')
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO safety_controls(sid,mode) VALUES (?,?)',(identifier,operation_mode))
        plans,origin = self.safety.safe_plan(identifier,engine,day,visible,weather,outcomes)
        for p in plans:p['prediction_origin']=origin
        input_history = [{'date': d, 'sku': sku, 'sold': v} for (d, sku), v in sorted(visible.items())]
        input_outcomes=list(outcomes.values())
        input_hash = hashlib.sha256(json.dumps({'history': input_history, 'weather': weather,'outcomes':input_outcomes}, sort_keys=True).encode()).hexdigest()
        s = {'id': identifier, 'day': day, 'seed': seed, 'mode': mode, 'revision': 0,
             'minute': 360, 'phase': 'plan_pending', 'created': now(), 'model_version': engine.version,
             'data_quality':quality, 'feature_snapshot_id':quality['snapshot_id'], 'input_hash': input_hash, 'input_history': input_history, 'model_hashes': engine.manifest['native_model_hashes'],
             'prediction_origin':origin, 'weather': weather, 'source': source, 'plan': plans, 'products': {}, 'ledger': [], 'decisions': [],
             'pending': None, 'keys': [], 'simulator_version': market_version if mode == 'simulation' else None,
             'simulator_hash':market_hash if mode=='simulation' else None,'auto_run':bool(auto_run and mode=='simulation'),
             'input_outcomes':input_outcomes,'history_source':'uploaded_or_observed' if history is not None or known else 'seeded_demo_history',
             'day_context':{'lag1_day':str((datetime.fromisoformat(day)-timedelta(days=1)).date()),
                            'same_weekday_day':str((datetime.fromisoformat(day)-timedelta(days=7)).date()),
                            'past_closed_days':len({r['date'] for r in outcomes.values()}),'inventory_features_active':any('waste' in n for n in engine.manifest['COLS']),
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
                           outcome_snapshot={(r['date'],r['sku_code']):r for r in old.get('input_outcomes',[])},
                           provenance={**old.get('data_quality',{}).get('lineage',{}),'parent_session':sid},market_version=old.get('simulator_version'))

    def next_day(self,sid,weather=None):
        old=self.store.get(sid)
        if old['phase']!='closed':
            raise ValueError('Cần chốt ngày hiện tại trước khi lập kế hoạch hôm sau.')
        day=str((datetime.fromisoformat(old['day'])+timedelta(days=1)).date())
        history={(r['date'],r['sku']):r['sold'] for r in old['input_history']}
        for sku,p in old['products'].items():
            history[(old['day'],sku)]=p['sold']
        scale=4 if old['mode']=='simulation' and old.get('simulator_version','').startswith('V606_busy4') else 1
        outcomes={(r['date'],r['sku_code']):{**r,'observation_scale':r.get('observation_scale',scale)} for r in old.get('input_outcomes',[])}
        for sku,p in old['products'].items():
            outcomes[(old['day'],sku)]=dict(date=old['day'],sku_code=sku,prepared_qty=p['prepared'],sold_qty=p['sold'],
                waste_qty=p['stock'],stockout=int(p['stock']==0),discounted_qty=sum(t['qty'] for t in old['ledger'] if t['sku']==sku and t['discount']>0),
                observation_scale=4 if old['mode']=='simulation' and old.get('simulator_version','').startswith('V606_busy4') else 1,
                sold_to_2130=sum(t['qty'] for t in old['ledger'] if t['sku']==sku and t['minute']<1290),source_session_id=old['id'])
        return self.create(day=day,seed=old['seed'],mode=old['mode'],history=history,weather=weather,
                           source='Kế hoạch sau chốt ca '+sid,auto_run=old.get('auto_run',False),identifier='next-'+sid,
                           apply_closed_history=False,outcome_snapshot=outcomes,provenance={'type':'own_completed_branch','parent_session':sid,'availability':'date_only_unverified'})

    def mutate(self, sid, revision, action, payload=None, key=None):
        try:
            return self._mutate(sid,revision,action,payload,key)
        except GuardError as exc:
            # Write AFTER rollback so the incident survives the failed action.
            self.safety.report(sid,'HARD_RULE_BLOCK',str(exc))
            raise
        except ValueError as exc:
            if any(k in str(exc).lower() for k in ['checksum','artifact']):self.safety.report(sid,'ARTIFACT_MISMATCH',str(exc))
            raise

    def _mutate(self, sid, revision, action, payload=None, key=None):
        payload = payload or {}
        with self.store.connect() as db, self.safety.bind(db):
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
        if not isinstance(overrides,dict):raise ValueError('Số duyệt phải theo từng SKU.')
        if set(overrides) - {p['sku'] for p in s['plan']}:
            raise ValueError('SKU không hợp lệ.')
        reason=payload.get('reason','')
        if not isinstance(reason,str) or len(reason)>2000:raise ValueError('Lý do phải là văn bản tối đa 2.000 ký tự.')
        reason=reason.strip();decisions=[]
        for p in s['plan']:
            qty = overrides.get(p['sku'], p['prepared'])
            if p.get('supply') and qty>p['supply']['capacity']:
                raise GuardError('Approved quantity exceeds declared scenario capacity: '+p['sku'])
            if type(qty) is not int or qty < 4 or qty % 4 or qty > 100000:
                raise GuardError(f"{p['sku']}: số lượng phải là số nguyên dương, bội số 4, tối thiểu 4; giới hạn nhập liệu 100.000 bánh.")
            below=qty<p['floor']
            if below and actor.get()['role']!='manager':raise AccessError('Chỉ Manager được duyệt thấp hơn sàn khuyến nghị.')
            if (qty != p['prepared'] or below) and not reason:
                raise ValueError('Cần lý do khi điều chỉnh sản lượng hoặc duyệt dưới sàn khuyến nghị.')
            decisions.append({'sku':p['sku'],'recommended_quantity':p['prepared'],'recommended_floor':p['floor'],
                              'approved_quantity':qty,'below_recommended_floor':below,'difference_from_recommendation':qty-p['prepared']})
        for p,d in zip(s['plan'],decisions):p['approved']=d['approved_quantity']
        s['production_approval']={'policy':'GD9.2-soft-recommended-floor-v1','actor':actor.get(),'reason':reason,'at':now(),
                                  'rows':decisions,'below_floor_skus':[d['sku'] for d in decisions if d['below_recommended_floor']],
                                  'note':'Sàn 90% baseline là khuyến nghị. Chưa cấu hình công suất/giới hạn sản xuất thật; 100.000 là giới hạn nhập liệu kỹ thuật.'}
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
        gate=self.safety.price_gate(s)
        if gate=='blocked':
            return {'id':uuid.uuid4().hex,'minute':SLOTS[j],'as_of_minute':s['minute'],'rows':[],
                    'status':'missing_data','blocked_reason':'Nguồn giao dịch thiếu hoặc quá 30 phút. Hãy nhập bán hàng hoặc xác nhận không có bán mới.','created':now()}
        rows = []
        if gate=='manual':
            rows=self.safety.manual_rows(s,j)
        for sku, p in ([] if rows else s['products'].items()):
            times = [(tx['minute'], tx['qty']) for tx in s['ledger'] if tx['sku'] == sku]
            s30 = sum(q for t, q in times if s['minute']-30<=t<=s['minute'])
            s60 = sum(q for t, q in times if s['minute']-60<=t<=s['minute'])
            try:
                active=self.version_engine(s['model_version']);kwargs={}
                if getattr(active,'cautious_pricing',False):
                    from .price_history import context
                    kwargs['observed_context']=context(self.store,s,sku,db=self.safety.bound.get())
                r=active.price(sku, j, p['stock'], p['prepared'], p['discount'], s30, s60, p['forecast'], s['weather'],as_of=s['minute'],**kwargs)
                if r['discount'] not in LADDER or not max(p['discount'],FLOORS[j])<=r['discount']<=CAPS[j]:
                    raise GuardError('Model M1 vi phạm hard rules.')
                rows.append(r)
            except Exception as exc:
                self.safety.report(s['id'],'M1_UNAVAILABLE',str(exc))
                rows=self.safety.manual_rows(s,j);gate='manual'
                break
        return {'id': uuid.uuid4().hex, 'minute': SLOTS[j], 'as_of_minute':s['minute'],'rows': rows, 'status': 'pending', 'created': now(),
                'feature_snapshot_id':digest({'m2':s.get('feature_snapshot_id'),'minute':s['minute'],'ledger':s['ledger'],
                    'stock':s['products'],'model':s['model_hashes']}), 'sales_quality':sales_quality(s), 'origin':'MANUAL_RULE' if gate=='manual' else 'AI_M1'}

    def consume(self,s,destination):
        if s['mode']!='simulation':
            return
        market_hash=self.simulator.hash_for(s['simulator_version']) if hasattr(self.simulator,'hash_for') else self.simulator.arrivals.hash
        if s.get('simulator_hash') and s['simulator_hash']!=market_hash:
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

    def pricing_checkpoint(self,s):
        proposal=self.proposals(s)
        if proposal.get('status')=='missing_data':
            s['pending']=proposal;s['phase']='price_pending';return
        held=[];changed=[]
        for row in proposal['rows']:
            p=s['products'][row['sku']]
            current=round(p['price']*(1-p['discount']/100))
            (changed if p['stock']>0 and row['new_price']!=current else held).append(row)
        proposal['held_rows']=held
        proposal['requires_approval']=bool(changed)
        if changed:
            proposal['rows']=changed;s['pending']=proposal;s['phase']='price_pending'
        else:
            proposal['status']='no_change'
            s['decisions'].append(proposal)
            s['pending']=None;s['phase']='running'

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
        if destination==1290:
            for p in s['products'].values():p['stock_at_2130']=p['stock']
        if destination==END:
            if s['pending']:
                s['pending']['status']='expired'
                s['decisions'].append(s['pending'])
            s['pending']=None;s['phase']='close_pending'
        elif destination>=SLOTS[0] and (destination in SLOTS or had_pending):
            self.pricing_checkpoint(s)

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
        if destination==1290:
            for p in s['products'].values():p['stock_at_2130']=p['stock']
        if destination in SLOTS:
            self.pricing_checkpoint(s)
        elif destination == END:
            s['phase'] = 'close_pending'

    def do_price_approve(self, s, payload):
        if s['phase'] != 'price_pending' or payload.get('proposal_id') != s['pending']['id']:
            raise ValueError('Đề xuất đã hết hiệu lực hoặc không còn chờ duyệt.')
        if s['pending'].get('status')=='missing_data' or s['mode']=='live' and not s['ledger'] and not s.get('confirmed_zero_sales'):
            raise ValueError('Cần nạp giao dịch hoặc xác nhận thực tế chưa có bán; không duyệt giá từ dữ liệu thiếu.')
        c=self.safety.control(s['id'])
        if 'stale_stock' in c['faults'] or sales_quality(s)['status']=='BLOCK':
            raise GuardError('Nguồn tồn/bán không đáng tin; không được duyệt giá.')
        if c['mode']=='manual' and s['pending'].get('origin')=='AI_M1':
            raise GuardError('Gợi ý AI đã bị vô hiệu hóa; tạo lại đề xuất thủ công.')
        if s['pending'].get('origin')=='AI_M1':self.version_engine(s['model_version']).require_integrity()
        overrides = payload.get('discounts', {})
        if set(overrides) - {p['sku'] for p in s['pending']['rows']}:
            raise ValueError('SKU không hợp lệ.')
        for p in s['pending']['rows']:
            tier = overrides.get(p['sku'], p['discount'])
            self.require_price_benefit(s,p,tier)
            if type(tier) not in (int,float) or tier not in LADDER or not max(p['previous'], p['floor']) <= tier <= p['cap']:
                raise GuardError(f"{p['sku']}: mức giảm phải tuân thủ thang giá, sàn, trần và không giảm ngược.")
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

    def do_refresh_price(self,s,payload):
        if not 1170<=s['minute']<END or s['phase'] not in ['running','price_pending','price_approved']:
            raise ValueError('Làm mới gợi ý giá chỉ từ 19:30 đến trước 22:00.')
        if s.get('pending'):
            s['pending']['status']='superseded_refresh';s['decisions'].append(s['pending'])
        self.pricing_checkpoint(s)

    @staticmethod
    def require_price_benefit(s,row,tier):
        if s['pending'].get('origin')!='AI_M1' or tier<=s['products'][row['sku']]['discount']:return
        gate=row.get('economic_gate',{})
        from .clearance import SCENARIO,POLICY
        from .cautious_pricing import POLICY as CAUTIOUS_POLICY
        if (s['mode']=='simulation' and s.get('simulator_version')==SCENARIO
            and gate.get('status')=='SIMULATION_ASSUMED_CLEARANCE_BENEFIT' and gate.get('evidence_id') in (POLICY,CAUTIOUS_POLICY)
            and tier==row['discount'] and gate.get('assumed_net_revenue_change',-1)>=0
            and gate.get('assumed_extra_units',0)>=1):return
        if gate.get('status')!='VERIFIED_POSITIVE_BENEFIT' or not gate.get('evidence_id'):
            raise GuardError('Đề xuất giảm chưa có lợi ích tăng thêm được xác minh. Đánh giá lại đề xuất để giữ giá.')

    def do_review_price_benefit(self,s,payload):
        if s['phase'] not in ('price_pending','price_approved') or not s.get('pending') or s['pending'].get('origin')!='AI_M1':
            raise ValueError('Chỉ đánh giá lại đề xuất AI chưa áp dụng.')
        s['pending']['status']='superseded_economic_review'
        s['decisions'].append(s['pending']);s['pending']=None
        self.pricing_checkpoint(s)

    def do_adopt_price_policy(self,s,payload):
        """Internal, audited policy-only upgrade; preserve market, stock and receipts."""
        from .v606 import TRAINED_CLEARANCE_VERSION,CURRENT_VERSION
        target=self.active_engine()
        if s['model_version']!=TRAINED_CLEARANCE_VERSION or target.version!=CURRENT_VERSION or s['phase'] in ('closed','close_pending'):
            raise ValueError('Policy upgrade only applies to an open v7 session')
        target.require_integrity()
        if target.manifest['native_model_hashes']!=s['model_hashes']:raise GuardError('Policy-only upgrade cannot change trained weights')
        before=s['model_version']
        if s.get('pending'):
            s['pending']['status']='superseded_late_first_policy';s['decisions'].append(s['pending']);s['pending']=None
            if s['phase'] in ('price_pending','price_approved'):s['phase']='running'
        s['model_version']=target.version
        s.setdefault('policy_updates',[]).append(dict(previous=before,current=target.version,at_minute=s['minute'],reason='User requested late-first pricing and pre-approval explanations; trained weights and market unchanged'))
        if s['minute']>=1170 and s['products']:self.pricing_checkpoint(s)

    def do_replan(self,s,payload):
        if s['phase']!='plan_pending':raise ValueError('Chỉ tính lại sản lượng khi chưa duyệt kế hoạch.')
        h={(r['date'],r['sku']):r['sold'] for r in s['input_history']}
        o={(r['date'],r['sku_code']):r for r in s.get('input_outcomes',[])}
        s['plan'],s['prediction_origin']=self.safety.safe_plan(s['id'],self.version_engine(s['model_version']),s['day'],h,s['weather'],o)
        for p in s['plan']:p['prediction_origin']=s['prediction_origin']

    def do_price_apply(self, s, payload):
        if s['phase'] != 'price_approved' or payload.get('proposal_id') != s['pending']['id']:
            raise ValueError('Cần duyệt đề xuất trước khi áp dụng.')
        if sales_quality(s)['status']=='BLOCK' or 'stale_stock' in self.safety.control(s['id'])['faults']:
            raise GuardError('Tồn/bán không còn đáng tin; không áp giá.')
        if s['pending'].get('origin')=='AI_M1':
            if self.safety.control(s['id'])['mode']=='manual':raise GuardError('AI đã tạm dừng; tạo lại đề xuất thủ công.')
            self.version_engine(s['model_version']).require_integrity()
        for p in s['pending']['rows']:
            self.require_price_benefit(s,p,p['approved'])
            if p['approved'] not in LADDER or not max(s['products'][p['sku']]['discount'],p['floor'])<=p['approved']<=p['cap']:
                raise GuardError('Hard rules không còn hợp lệ ở lúc áp dụng.')
        if self.safety.control(s['id'])['mode']=='shadow':
            s['pending']['status']='shadow_only';s['pending']['applied_at']=None
            s['decisions'].append(s['pending']);s['pending']=None;s['phase']='running'
            return
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
            raise GuardError(f'{sku}: số lượng bán vượt tồn.')
        paid = int(round(p['price'] * (1 - p['discount'] / 100)))
        s['ledger'].append({'transaction_id':uuid.uuid4().hex,'request_id':request_trace.get(),'model_version':s['model_version'],'feature_snapshot_id':s.get('feature_snapshot_id'),'proposal_id':next((d['id'] for d in reversed(s['decisions']) if d.get('status')=='applied'),None),'sku': sku, 'minute': minute, 'qty': qty, 'discount': p['discount'],
                            'unit_price': paid, 'paid': paid * qty, 'origin': origin})
        p['stock'] -= qty
        p['sold'] += qty
        p['revenue'] += paid * qty
        if p['stock']==0 and 'first_stockout_minute' not in p:p['first_stockout_minute']=minute

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
            self.pricing_checkpoint(s)

    def do_confirm_zero_sales(self,s,payload):
        if s['mode']!='live' or not payload.get('confirmed') or not payload.get('reason','').strip():
            raise ValueError('Cần xác nhận có lý do rằng thực tế chưa có lượt bán; chỉ dành cho ca live chưa có giao dịch.')
        s['confirmed_zero_sales']=not bool(s['ledger'])
        s['sales_verified_minute']=s['minute']
        if s['pending']:
            self.pricing_checkpoint(s)

    def do_close(self, s, payload):
        if s['phase'] != 'close_pending' or s['minute'] != END:
            raise ValueError('Chỉ chốt ngày khi đã xử lý đủ các mốc và đến 22:00.')
        from .evaluation import reconcile
        check=reconcile(s)
        if check['errors']:raise GuardError('Đối soát thất bại: '+'; '.join(check['errors']))
        s['phase'] = 'closed'
        s['closed'] = now()

    @staticmethod
    def assert_accounts(s):
        for sku, p in s['products'].items():
            tx = [t for t in s['ledger'] if t['sku'] == sku]
            if p['prepared'] != p['stock'] + p['sold'] or p['stock'] < 0 or p['revenue'] != sum(t['paid'] for t in tx) or p['sold'] != sum(t['qty'] for t in tx):
                raise GuardError('Đối soát tồn hoặc doanh thu thất bại.')

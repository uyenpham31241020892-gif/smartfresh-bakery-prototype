"""V606 adapters for the existing prototype. Synthetic POS is not model input."""
from pathlib import Path
from datetime import date, timedelta
from types import SimpleNamespace
import csv
import hashlib
import json
import math
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'v606/03_TEST_POS_RUNTIME'
BUSY_FACTOR = 4
SERVICE_RESERVE = 4
SERVICE_Z = 1.64  # Declared planning buffer, not a validated service guarantee.
LEGACY_POLICY_VERSION = 'busy4-evening75-service2130-v3'
from .planning import adaptive_supply, POLICY_VERSION
ADAPTIVE_M2_VERSION = 'V606-frozen-prototype-adaptive-v4'
CONTEXTUAL_PRICE_VERSION = 'V606-frozen-prototype-contextual-price-v5'
BENEFIT_GUARD_VERSION = 'V606-frozen-prototype-benefit-guard-v6'
TRAINED_CLEARANCE_VERSION = 'V606-trained-remaining-clearance-v7'
CURRENT_VERSION = 'V606-late-first-budgeted-clearance-v8'
LEGACY_VERSION = 'V606-frozen-prototype-service2130-v3'
# Freeze customer draws across supply policy revisions: policy changes must not change customers.
MARKET_VERSION = 'V606_busy4-evening75-service2130-v2'
sys.path.insert(0, str(ROOT / 'v606'))
sys.path.insert(0, str(PUBLIC / 'code'))
import model_adapter as adapter
from features_asof import m2_features
from context_tools import event_context

def read(name):
    with (PUBLIC / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

class Engine:
    def __init__(self, *args, version=None, **kwargs):
        self.model_dir = adapter.MODELS
        self.version = version or CURRENT_VERSION
        if self.version not in (CURRENT_VERSION,TRAINED_CLEARANCE_VERSION,BENEFIT_GUARD_VERSION,CONTEXTUAL_PRICE_VERSION,ADAPTIVE_M2_VERSION,LEGACY_VERSION):raise ValueError('Unsupported V606 engine version')
        self.legacy = self.version == LEGACY_VERSION
        self.trained_clearance=self.version in (CURRENT_VERSION,TRAINED_CLEARANCE_VERSION)
        self.cautious_pricing=self.version==CURRENT_VERSION
        self.contextual_pricing=self.version in (CURRENT_VERSION,TRAINED_CLEARANCE_VERSION,BENEFIT_GUARD_VERSION,CONTEXTUAL_PRICE_VERSION)
        self.artifact_error = None
        self.master = {k:dict(v) for k,v in adapter.MASTER.items()}
        for r in self.master.values():
            r['unit_price_vnd_reference'] = int(r['unit_price_vnd_reference'])
        self.skus = list(self.master.values())
        self.seed_rows = read('history_seed_through_20220630.csv')
        for r in self.seed_rows:
            for k in ['sold_qty','prepared_qty','censored_demand_flag']:
                r[k] = int(r[k])
        self.means = {s:np.mean([r['sold_qty'] for r in self.seed_rows if r['sku_code']==s]) for s in self.master}
        self.selection = {'selected_q':.5,'selected_prep_floor':0,'busy_factor':BUSY_FACTOR,'service_until':'21:30','policy_version':LEGACY_POLICY_VERSION if self.legacy else POLICY_VERSION}
        self.selection['pricing_policy']='OBSERVED_SURPLUS_FROM_1930_V1' if self.contextual_pricing else 'ORIGINAL_LOGGED_ACTION_AFTER_2100'
        self.selection['economic_release_guard']='BENEFIT_REQUIRED_HOLD_WITHOUT_UPLIFT_V1'
        if self.trained_clearance:
            from .clearance import POLICY
            if self.cautious_pricing:
                from .cautious_pricing import POLICY
            self.selection.update(pricing_policy=POLICY,economic_release_guard='MANAGER_REVIEW_ASSUMED_SIMULATION_BENEFIT_ONLY')
        self.manifest = dict(version=self.version,trained_until='2022-06-30',parent='V606',
            COLS=adapter.CONTRACT['m2_predictive_columns'],MCOLS=adapter.CONTRACT['m1_pre_action_columns'],
            native_model_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.model_dir.iterdir() if p.suffix in ('.json','.joblib')})
        if self.trained_clearance:
            from .clearance import DIRECTORY
            self.manifest['remaining_sales_training']=json.loads((DIRECTORY/'training_report.json').read_text())
            self.manifest['native_model_hashes'].update({'remaining/'+k:v for k,v in self.manifest['remaining_sales_training']['artifact_hashes'].items()})
        review=ROOT/'v606/V606_M2_retrained_20261023/training_report.json'
        self.training_review=None
        if review.exists():
            r=json.loads(review.read_text(encoding='utf-8'))
            self.training_review=dict(configurations=sum(len(h['candidates']) for h in r['horizons'].values()),trained_until=r['trained_until'],promoted=r['promoted'],
                scope=r['scope'],day={k:r['horizons']['day'][k] for k in ('selected','original_reproduced','promotion_gate','promotion_eligible')})
        self.require_integrity()
    def require_integrity(self):
        for n,h in self.manifest['native_model_hashes'].items():
            from .clearance import DIRECTORY
            p=DIRECTORY/n.split('/',1)[1] if n.startswith('remaining/') else self.model_dir/n
            if hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('V606 artifact changed')
        if self.trained_clearance:
            from .clearance import DIRECTORY
            report=json.loads((DIRECTORY/'training_report.json').read_text())
            for n,h in report['artifact_hashes'].items():
                if hashlib.sha256((DIRECTORY/n).read_bytes()).hexdigest()!=h:raise ValueError('M1 remaining artifact changed')
        return True
    def reload_if_needed(self):
        self.require_integrity();adapter.models()
    def history(self, day, sku, visible, outcomes=None, normalize=False):
        if any(d>=day for d,s in visible):raise ValueError('Future/same-day observations rejected')
        rows={r['date']:dict(r) for r in self.seed_rows if r['sku_code']==sku and r['date']<day}
        for (d,s),n in visible.items():
            if s==sku and d<day:
                old=rows.get(d)
                outcome=(outcomes or {}).get((d,s))
                if outcome:
                    scale=outcome.get('observation_scale',1) if normalize else 1
                    rows[d]=dict(date=d,sku_code=s,sold_qty=n/scale,prepared_qty=outcome['prepared_qty']/scale,censored_demand_flag=int(outcome.get('stockout',0)))
                elif old is None or n!=old['sold_qty']:
                    raise ValueError('V606 requires completed preparation/censor history, not sales alone')
        return sorted(rows.values(),key=lambda r:r['date'])
    def features(self,day,sku,visible,weather,outcomes=None):
        prev=str(date.fromisoformat(day)-timedelta(days=1))
        if weather.get('weather_reference_date',prev)!=prev:raise ValueError('Weather must reference the previous calendar day')
        f=m2_features(dict(date=day,sku_code=sku,completed_branch_history=self.history(day,sku,visible,outcomes,normalize=not self.legacy),
            decision_at=day+'T06:00:00+07:00',sku_master=self.master[sku],is_public_holiday=weather['is_public_holiday'],
            is_weekend=weather['is_weekend'],is_tet_run_up=0,weather_prior_day=dict(rain_mm=weather.get('prior_day_rain_mm'),temp_c=weather.get('prior_day_temp_c'))))
        if not self.legacy:
            f['history_scale_status']='BUSY_LOCAL_POS_NORMALIZED_TO_TRAIN_SCALE; SEED_UNCHANGED'
            f['weather_provenance']=weather.get('weather_provenance')
        return f
    def baseline(self,day,sku,visible):
        vals=[n*(BUSY_FACTOR if d<='2022-06-30' and not self.legacy else 1) for (d,s),n in sorted(visible.items()) if s==sku and d<day][-7:]
        if not self.legacy:
            return min(int(self.master[sku]['daily_capacity_units_assumed'])*BUSY_FACTOR,4*math.ceil(float(np.mean(vals))*1.12/4))
        return self.supply(sku,float(np.mean(vals))*1.12)['quantity']

    def supply(self,sku,raw_forecast):
        # Public, preregistered scenario assumptions only. Never reads event counts/draws.
        expected=float(self.means[sku])*BUSY_FACTOR
        adjusted=max(0,float(raw_forecast))*BUSY_FACTOR
        sigma=math.sqrt(expected)
        # Censored model is a lower-bound forecast, not a calibrated busy-store point target.
        # Bound its influence to avoid scaling an already buffered fallback a second time.
        model_adjustment=.25*max(-sigma,min(sigma,adjusted-expected))
        target=expected+model_adjustment+SERVICE_Z*sigma+SERVICE_RESERVE
        cap=int(self.master[sku]['daily_capacity_units_assumed'])*BUSY_FACTOR
        required=4*math.ceil(target/4)
        return dict(quantity=min(cap//4*4,required),raw_forecast=float(raw_forecast),scenario_forecast=adjusted,
                    expected_requests_assumed=expected,model_adjustment=model_adjustment,uncertainty_buffer=SERVICE_Z*sigma,
                    service_reserve=SERVICE_RESERVE,required=required,
                    capacity=cap,capacity_feasible=required<=cap,service_until='21:30',
                    policy=LEGACY_POLICY_VERSION,service_status='PLANNING_GOAL_NOT_GUARANTEE',capacity_status='ASSUMED_BUSY_SCENARIO_CAPACITY_NOT_PHYSICAL_SURVEY')
    def plan(self,day,visible,weather,outcomes=None):
        self.require_integrity();plans=[]
        pre,m2,_=adapter.models()
        import xgboost as xgb
        for sku,spec in self.master.items():
            f=self.features(day,sku,visible,weather,outcomes)
            forecast=float(m2.predict(xgb.DMatrix(pre.transform(adapter.frame(f,adapter.CONTRACT['m2_predictive_columns'])).astype(float)))[0])
            p=adapter.prepare(f,self.history(day,sku,visible,outcomes)) if self.legacy else {'policy_status':'ADAPTIVE_MODEL' if not f['ood_flag'] else 'ADAPTIVE_OBSERVED_HISTORY_FALLBACK_MANAGER_REVIEW'}
            if self.legacy:
                supply=self.supply(sku,forecast)
            else:
                observed=[dict(date=r['date'],sku_code=r['sku_code'],sold_qty=visible[(r['date'],r['sku_code'])],
                    prepared_qty=r['prepared_qty'],censored_demand_flag=int(r.get('stockout',0)),sold_to_2130=r.get('sold_to_2130'))
                    for r in (outcomes or {}).values() if r['sku_code']==sku and (r['date'],r['sku_code']) in visible]
                supply=adaptive_supply(sku,forecast,f,self.history(day,sku,visible,outcomes),observed,spec,
                    scale=int(weather.get('planning_demand_scale',1)))
            qty=supply['quantity']
            plans.append(dict(sku=sku,name=spec['product_name_reference'],price=spec['unit_price_vnd_reference'],baseline=self.baseline(day,sku,visible),
                forecast=max(0,forecast),buffer=qty-forecast,floor=0,prepared=qty,batches=qty//4,quantile=.5,features=f,model_bias=0,contributions=[],history_warning=bool(f['ood_flag']),policy_status=p['policy_status'],supply=supply))
        return plans
    def price(self,sku,j,stock,prepared,previous,sales30,sales60,forecast,weather,as_of=None,observed_context=None):
        minute=as_of or [1170,1200,1230,1260,1290][j];t=f'{minute//60:02}:{minute%60:02}'
        f=dict(sku_code=sku,time=t,prepared_qty=prepared,inventory_at_decision=stock,sold_last_30min=sales30,sold_last_60min=sales60,
            shelf_inventory=min(stock,int(self.master[sku]['shelf_capacity_units_assumed'])),backroom_inventory=max(0,stock-int(self.master[sku]['shelf_capacity_units_assumed'])),previous_discount_pct=previous,baseline_announced_2100_pct=None)
        price=self.master[sku]['unit_price_vnd_reference'];current=round(price*(1-previous/100))
        if self.contextual_pricing:
            from .pricing import markdown
            import joblib
            # Normalization is an explicit scenario conversion; model X still follows its allowlist.
            scale=float(weather.get('planning_demand_scale',1))
            if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid declared simulation scale')
            mf=dict(f)
            shelf_cap=int(self.master[sku]['shelf_capacity_units_assumed'])*scale
            mf['shelf_inventory']=min(stock,shelf_cap);mf['backroom_inventory']=max(0,stock-shelf_cap)
            for k in ('prepared_qty','inventory_at_decision','sold_last_30min','sold_last_60min','shelf_inventory','backroom_inventory'):mf[k]/=scale
            x=adapter.frame(mf,adapter.CONTRACT['m1_pre_action_columns']);_,_,m1=adapter.models()
            if self.trained_clearance:
                from .clearance import predict,recommend
                if self.cautious_pricing:
                    from .cautious_pricing import recommend
                predictions=predict(x,scale)
                row=dict(sku=sku,minute=minute,stock=stock,sales30=sales30,sales60=sales60,previous=previous,
                    price=price,cap=max(20,previous) if self.cautious_pricing else 40,floor=0,schedule=[],candidates=[],low_stock=stock<=sales60/2)
                kwargs=dict(scenario=weather.get('price_response_scenario'))
                if self.cautious_pricing:kwargs['history']=observed_context
                return recommend(row,prepared,predictions['close'],predictions['to2130'],**kwargs)
            action=str(m1['classifier'].predict(m1['preprocessor'].transform(x))[0])
            if not hasattr(self,'_outcome_model'):self._outcome_model=joblib.load(self.model_dir/'M1_logged_outcome_forecast.joblib')
            outcome=self._outcome_model
            if outcome['columns']!=adapter.CONTRACT['m1_pre_action_columns'] or m1['columns']!=adapter.CONTRACT['m1_pre_action_columns']:
                raise ValueError('M1 feature contract mismatch')
            expected=float(outcome['regressor'].predict(outcome['preprocessor'].transform(x))[0])*scale
            proposal=markdown(self.master[sku],minute,stock,prepared,previous,sales30,sales60,expected,action)
            row=dict(sku=sku,minute=minute,stock=stock,sales30=sales30,sales60=sales60,previous=previous,
                price=price,cap=50,floor=0,schedule=[],candidates=[],low_stock=stock<=sales60/2,**proposal)
            from .price_benefit import guard
            return guard(row)
        cash=adapter.markdown(dict(model_features=f,price_context=dict(current_unit_price_vnd=current)),weather['date']+'T'+t+':00+07:00')['approved_cash_price_vnd'] if stock else current
        discount=round(100*(price-cash)/price,10)
        row=dict(sku=sku,minute=minute,stock=stock,sales30=sales30,sales60=sales60,previous=previous,discount=discount,price=price,new_price=cash,cap=50,floor=0,schedule=[],candidates=[],low_stock=stock<=sales60/2,reason='V606_LOGGED_ACTION_IMITATION_NOT_CAUSAL_UPLIFT')
        from .price_benefit import guard
        return guard(row)

class Simulator:
    """Declared busy-store stress scenario, never reads private test demand or labels."""
    def __init__(self,engine):
        # Market stream identity stays fixed when only the supply policy changes.
        from .clearance import SCENARIO
        self.engine=engine;self.version=SCENARIO if engine.trained_clearance else 'V606_'+LEGACY_POLICY_VERSION;self.arrivals=SimpleNamespace(hash=hashlib.sha256(self.version.encode()).hexdigest(),version=self.version)
        wx={r['date']:r for r in read('prior_weather_through_20220630.csv')};self.calendar={}
        supplement=ROOT/'v606/public_context/prior_weather_development.json'
        extra=json.loads(supplement.read_text(encoding='utf-8')) if supplement.exists() else {}
        if not engine.legacy:
            for row in extra.get('rows',[]):wx.setdefault(row['date'],row)
        for r in read('calendar_test.csv'):
            d=date.fromisoformat(r['date']);w=wx.get(str(d-timedelta(days=1)),{})
            self.calendar[r['date']]={**r,'date':r['date'],'weekday_iso':d.isoweekday(),'is_weekend':int(d.weekday()>4),'is_public_holiday':int(r['is_public_holiday']),
                'month':d.month,'day_of_year':d.timetuple().tm_yday,'is_festival_non_public':0,'forecast_rain_mm_previous_day1':float(w['rain_mm']) if w else None,
                'forecast_temperature_max_c_previous_day1':float(w['temp_c']) if w else None,'prior_day_rain_mm':float(w['rain_mm']) if w else None,'prior_day_temp_c':float(w['temp_c']) if w else None,
                'planning_demand_scale':BUSY_FACTOR,'weather_reference_date':str(d-timedelta(days=1)),
                'weather_provenance':dict(status='RETROSPECTIVE_PRIOR_DAY_SIMULATION_ONLY_NOT_ISSUED_FORECAST',reference_date=str(d-timedelta(days=1)),
                    source='BUNDLED_V606' if str(d-timedelta(days=1))<='2022-06-30' else extra.get('source'),vintage_verified=False)}
        ext_cal = ROOT / 'v606/public_context/extended_calendar_202209_202301.json'
        if ext_cal.exists() and not engine.legacy:
            for day_str, row in json.loads(ext_cal.read_text(encoding='utf-8')).items():
                self.calendar.setdefault(day_str, row)
        self.seed={(r['date'],r['sku_code']):r['sold_qty'] for r in engine.seed_rows}
        self.arrivals.report=lambda:dict(type='V606 busy scenario ASSUMED 4x past observed mean; no trained arrival model',training_rows=0,train_until='2022-06-30',calibrated_until=None,test_rows=0,test_from='2022-07-01',evaluated_until=None,test_mae=None,sku_mean_baseline_mae=None,sha256=self.arrivals.hash)
    def history_before(self,day,**kwargs):
        if day not in self.calendar:raise ValueError('Use July/August 2022 test scenario dates')
        return dict(self.seed)
    def events(self,day,seed=42,weather=None,version=None):
        entropy=int.from_bytes(hashlib.sha256(f'{MARKET_VERSION}:{day}:{seed}'.encode()).digest()[:8],'little');rng=np.random.default_rng(entropy);events=[]
        for sku in self.engine.master:
            # Fixed public-history-based intensity; no model prediction or future labels.
            count=int(rng.poisson(BUSY_FACTOR*float(self.engine.means[sku])))
            early=int(rng.binomial(count,.25))
            times=np.concatenate([rng.integers(480,1020,early),rng.integers(1020,1320,count-early)])
            for t in times:events.append(dict(id=len(events),sku=sku,minute=int(t),promo=0,required=0,draw=0))
        from .clearance import SCENARIO,ELASTICITY
        version=version or self.version
        if version==SCENARIO:
            # Independent prospective sensitivity scenario. Organic draws above stay identical.
            # At d% discount, expected extra eligible requests = organic * E * d/100.
            rng=np.random.default_rng(int.from_bytes(hashlib.sha256(f'{SCENARIO}:{day}:{seed}'.encode()).digest()[:8],'little'))
            for sku in self.engine.master:
                count=int(rng.poisson(BUSY_FACTOR*float(self.engine.means[sku])*ELASTICITY*.5))
                times=rng.integers(1170,1320,count)
                # Only the evening organic share after 19:30 is exposed to this response.
                for t in times:
                    if rng.random()>.75*.5:continue
                    events.append(dict(id=len(events),sku=sku,minute=int(t),promo=1,required=float(rng.uniform(0,50)),draw=0))
        elif version!='V606_'+LEGACY_POLICY_VERSION:raise ValueError('Unknown pinned V606 market version')
        return sorted(events,key=lambda e:(e['minute'],e['id']))

    def hash_for(self,version):
        from .clearance import SCENARIO
        if version not in (SCENARIO,'V606_'+LEGACY_POLICY_VERSION):raise ValueError('Unknown market version')
        return hashlib.sha256(version.encode()).hexdigest()

    def comparison(self,day='2022-07-01',seed=42):
        """Same synthetic stream for four branches; no retraining or parameter search."""
        visible=self.history_before(day);weather=dict(self.calendar[day])
        from .clearance import SCENARIO
        if self.version==SCENARIO:weather['price_response_scenario']=SCENARIO
        plans=self.engine.plan(day,visible,weather);events=self.events(day,seed)
        result=[]
        for branch in ['BASELINE','M1_ONLY','M2_ONLY','JOINT_M1_M2']:
            products={p['sku']:dict(prepared=p['baseline'] if branch in ('BASELINE','M1_ONLY') else p['prepared'],stock=p['baseline'] if branch in ('BASELINE','M1_ONLY') else p['prepared'],sold=0,revenue=0,lost=0,discount=0,sales=[]) for p in plans}
            for t in range(480,1320):
                if t in (1170,1200,1230,1260,1290):
                    for p in plans:
                        sku=p['sku'];v=products[sku];s30=sum(m>=t-30 for m in v['sales']);s60=sum(m>=t-60 for m in v['sales'])
                        if branch in ('M1_ONLY','JOINT_M1_M2'):
                            v['discount']=self.engine.price(sku,(t-1170)//30,v['stock'],v['prepared'],v['discount'],s30,s60,p['forecast'],weather,t,
                                observed_context=dict(sold_today=v['sold'],past_discount_value=p['price']*v['sold']-v['revenue']))['discount']
                        elif t>=1260 and v['stock']>max(s30/30,s60/60)*(1320-t):
                            ref=self.engine.master[sku]['markdown_price_vnd_reference']
                            if ref:v['discount']=max(v['discount'],100*(p['price']-int(ref))/p['price'])
                for e in (e for e in events if e['minute']==t):
                    v=products[e['sku']]
                    if e['promo'] and (e['required']>v['discount'] or e['draw']>.6):continue
                    if v['stock']:
                        v['stock']-=1;v['sold']+=1;v['sales'].append(t);v['revenue']+=round(self.engine.master[e['sku']]['unit_price_vnd_reference']*(1-v['discount']/100))
                    else:v['lost']+=1
            requested=sum(v['sold']+v['lost'] for v in products.values())
            result.append(dict(branch=branch,eligible_purchase_requests=requested,**{k:sum(v[k] for v in products.values()) for k in ['prepared','sold','stock','revenue','lost']}))
        base=result[0]['revenue']
        for r in result:r['delta_revenue']=r['revenue']-base;r['delta_percent']=100*(r['revenue']-base)/base if base else None
        return dict(day=day,seed=seed,scenario=self.version,potential_purchases=len(events),scope='CUSTOM_SYNTHETIC_BUSY_SCENARIO_NOT_OFFICIAL_MARKET_TEST',branches=result)

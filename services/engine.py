"""Original prototype interface, backed exclusively by the byte-identical V4 adapter."""
import csv,hashlib,importlib.util,json,math,sys,threading
from datetime import date,timedelta
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/v4'
SLOTS=[1170,1200,1230,1260,1290]
LADDER=[0,10,15,20,25,30,35,40,45,50]
CAPS=[40,40,50,50,50]
FLOORS=[0,0,0,0,0]
END=1320
MODEL_VERSION='SMARTFRESH_V4_LOCKED'
MODEL_LOCK=threading.RLock()
def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def clean(row):
    result={}
    for k,v in row.items():
        if v in ('',None):result[k]=None;continue
        try:
            n=float(v);result[k]=None if math.isnan(n) else int(n) if math.isfinite(n) and n.is_integer() else n
        except (ValueError,TypeError):result[k]=v
    return result
def adapter_module():
    name='smartfresh_v4_frozen'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,ROOT/'v4/smartfresh_adapter.py')
        m=importlib.util.module_from_spec(spec);sys.modules[name]=m;sys.modules['smartfresh_adapter']=m;spec.loader.exec_module(m)
    m=sys.modules[name];m._load_artifacts();return m
class Engine:
    legacy=False
    cautious_pricing=True
    trained_clearance=False
    def __init__(self,model_dir=None,allow_degraded=False,version=None):
        if version not in (None,MODEL_VERSION):raise ValueError('Chỉ cho phép model V4 đã khóa.')
        self.version=MODEL_VERSION;self.model_dir=ROOT/'v4/artifacts_build/models'
        self.artifact_error=None;self.training_review=None;self.m1=self.m2=None
        self._hashes=json.loads((ROOT/'MODEL_DATA_HASHES.json').read_text())
        self.manifest=dict(version=self.version,parent=None,trained_until='2022-04-30',validation_through='2022-06-30',evaluated_until='2022-08-31',evaluation_protocol='POST_TEST_DEVELOPMENT_ITERATION',native_model_hashes={k:v for k,v in self._hashes.items() if k.startswith('v4/')},COLS=[],MCOLS=[],no_retraining=True)
        self.skus=[clean(r) for r in read_csv(DATA/'sku_master.csv')];self.master={r['sku_code']:r for r in self.skus}
        self.observed=[clean(r) for r in read_csv(DATA/'warmup_history.csv')+read_csv(DATA/'development_observed.csv')]
        self.seed_rows=[r for r in self.observed if r['date']<'2022-05-01']
        self.means={s:float(np.mean([r['sold_qty'] for r in self.seed_rows if r['sku_code']==s])) for s in self.master}
        self.morning={(r['date'],r['sku_code']):clean(r) for r in read_csv(DATA/'m2_morning_features.csv')}
        self.selection=dict(version='V4_ORIGINAL_ADAPTER',selected_q=None,selected_prep_floor=0,pricing_policy='V4_EXPECTED_NET_GAIN_OVER_HOLD',economic_release_guard='V4_ORIGINAL_ADAPTER',service_until='21:30',batch_size=4,no_busy_multiplier=True)
        try:self.reload_if_needed()
        except Exception as exc:
            if not allow_degraded:raise
            self.artifact_error=str(exc)
    def require_integrity(self):
        for rel,h in self._hashes.items():
            p=ROOT/rel
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('V4 HASH_MISMATCH: '+rel)
        return True
    def reload_if_needed(self):
        self.require_integrity()
        import sklearn
        if sklearn.__version__!='1.9.1':raise ValueError('V4 cần scikit-learn 1.9.1; hiện có '+sklearn.__version__)
        with MODEL_LOCK:
            self.adapter=adapter_module();self.m2=self.adapter._M2_BUNDLE;self.m1=self.adapter._M1_BUNDLE
            if self.m1 is None or self.m2 is None:raise ValueError('Thiếu bundle model V4.')
            self.manifest['COLS']=list(self.m2['preprocessor'].numeric_cols);self.manifest['MCOLS']=list(self.m1['preprocessor'].numeric_cols)
        self.artifact_error=None
    def features(self,day,sku,visible,weather,outcomes=None):
        if sku not in self.master or any(d>=day for d,s in visible):raise ValueError('SKU sai hoặc lịch sử hiện tại/tương lai bị chặn.')
        supplied=weather.get('v4_features',{});template=supplied.get(sku) or self.morning.get((day,sku))
        generated=weather.get('forecast_source') in ('GENERATED_PRIOR_DAY_PROXY','OPEN_METEO_JMA_GSM_PREVIOUS_DAY1')
        if template is None and generated:
            candidates=[(d,r) for (d,s),r in self.morning.items() if s==sku and d<day]
            if candidates:template=max(candidates,key=lambda item:item[0])[1]
        if template is None:raise ValueError('Ngày ngoài bộ mẫu V4 cần đủ morning_features V4 kèm lịch sử/thời tiết; không dùng feature cũ.')
        f=dict(template)
        if generated:
            f.update(date=day,sku_code=sku,is_public_holiday=weather['is_public_holiday'],is_weekend=weather['is_weekend'],
                     weekday_iso=date.fromisoformat(day).isoweekday(),month=date.fromisoformat(day).month,
                     decision_at=day+'T06:00:00+07:00')
        if f.get('ood_reasons') is None:f['ood_reasons']=''
        if f.get('date')!=day or f.get('sku_code')!=sku:raise ValueError('Feature V4 khác ngày/SKU.')
        source={(r['date'],sku):r['sold_qty'] for r in self.observed if r['sku_code']==sku and r['date']<day}
        recent_keys=[(d,s) for d,s in source if (date.fromisoformat(day)-date.fromisoformat(d)).days<=7]
        changed=generated or any(s==sku and source.get((d,s))!=n for (d,s),n in visible.items()) or any(k not in visible for k in recent_keys)
        if changed and not supplied:
            from .v4_features.features_asof import m2_features
            hist=[]
            for (d,s),n in sorted(visible.items()):
                if s!=sku:continue
                o=(outcomes or {}).get((d,s))
                if not o:raise ValueError('V4 cần prepared_qty và cờ censor của lịch sử đã thay đổi; không coi thiếu là 0.')
                hist.append(dict(date=d,sku_code=sku,sold_qty=n,prepared_qty=o['prepared_qty'],censored_demand_flag=int(o.get('censored_demand_flag',o.get('stockout',0)))))
            if not hist:raise ValueError('Thiếu lịch sử V4 cho '+sku)
            rebuilt=m2_features(dict(date=day,sku_code=sku,completed_branch_history=hist,decision_at=day+'T06:00:00+07:00',sku_master=self.master[sku],is_public_holiday=f['is_public_holiday'],is_tet_run_up=f['is_tet_run_up'],is_weekend=f['is_weekend'],weather_prior_day=dict(rain_mm=weather.get('prior_day_rain_mm',weather.get('forecast_rain_mm_previous_day1')),temp_c=weather.get('prior_day_temp_c',weather.get('forecast_temperature_max_c_previous_day1')))))
            f.update(rebuilt)
            if generated and weather['is_public_holiday']:
                f['event_stratum']='public_holiday'
        f.update(prior_day_rain_mm=weather.get('prior_day_rain_mm',weather.get('forecast_rain_mm_previous_day1')),prior_day_temp_c=weather.get('prior_day_temp_c',weather.get('forecast_temperature_max_c_previous_day1')))
        self.validate_features(f,day,sku);return f
    def validate_features(self,f,day,sku):
        from .quality import timestamp,cutoff
        if str(f.get('history_through','9999'))>=day or str(f.get('weather_reference_date','9999'))>=day:raise ValueError('V4: lịch sử/thời tiết phải trước ngày quyết định.')
        ts=timestamp(f.get('decision_at'))
        if ts>cutoff(day) or ts.date().isoformat()!=day:raise ValueError('V4: decision_at cần đúng ngày, không sau cutoff 06:00.')
        for c in self.manifest['COLS']:
            if c in ['sold_calendar_lag1','sold_calendar_lag7'] and f.get(c) is None:
                if f.get(c+'_missing')==1 and f.get(c+'_fallback_observed_sales') is not None and math.isfinite(float(f[c+'_fallback_observed_sales'])):continue
            try:n=float(f[c])
            except (KeyError,ValueError,TypeError):raise ValueError('V4 thiếu/sai feature '+c+' của '+sku)
            if not math.isfinite(n):raise ValueError('V4 feature không hữu hạn: '+c)
        for c in ['sold_calendar_lag1','sold_calendar_lag7','sold_last7_observed_mean','prepared_last_observed','prior_day_rain_mm']:
            if f.get(c) is not None and float(f[c])<0:raise ValueError('V4 feature không được âm: '+c)
        for c in ['operational_daily_capacity_units','operational_lead_minutes','known_unit_production_cost_vnd']:
            if c in f and (f[c] is None or not math.isfinite(float(f[c])) or float(f[c])<=0):raise ValueError('V4 giá vốn/công suất/lead time phải dương: '+c)
        d=date.fromisoformat(day)
        if int(f.get('weekday_iso',0))!=d.isoweekday() or int(f.get('month',0))!=d.month:raise ValueError('V4 sai thứ/tháng của ngày ca.')
    def baseline(self,day,sku,visible,outcomes=None):
        vals=[n for (d,s),n in sorted(visible.items()) if s==sku and 0<(date.fromisoformat(day)-date.fromisoformat(d)).days<=7]
        if not vals:raise ValueError('Thiếu lịch sử để lập khuyến nghị thủ công.')
        return min(int(self.master[sku]['daily_capacity_units_assumed']),max(4,4*math.ceil(sum(vals)/len(vals)/4)))
    def plan(self,day,visible,weather,outcomes=None):
        self.require_integrity();plans=[]
        with MODEL_LOCK:
            for sku,spec in self.master.items():
                f=self.features(day,sku,visible,weather,outcomes);vec=self.m2['preprocessor'].transform_row(f,sku,spec)
                pred={k:float(self.m2.get(k,self.m2['model']).predict([vec])[0]) for k in ['model','model_q75','model_q90']}
                if not all(math.isfinite(x) for x in pred.values()):raise ValueError('M2 trả kết quả không hữu hạn.')
                q75=pred['model_q75'] if pred['model_q75']>pred['model'] else pred['model']*1.15
                q90=pred['model_q90'] if pred['model_q90']>q75 else q75*1.15
                own_history=[dict((outcomes or {}).get((d,s),{}),date=d,sku_code=s,sold_qty=n)
                             for (d,s),n in sorted(visible.items()) if s==sku and d<day] if getattr(self.adapter,'JOINT_POLICY',False) else []
                result=self.adapter.prepare(f,own_history);qty=int(result['initial_qty']+sum(b['qty'] for b in result['production_batches']));cap=int(f.get('operational_daily_capacity_units') or spec['daily_capacity_units_assumed'])
                plans.append(dict(sku=sku,name=spec['product_name_reference'],price=int(spec['unit_price_vnd_reference']),baseline=self.baseline(day,sku,visible,outcomes),forecast=max(0.,pred['model']),buffer=qty-pred['model'],floor=0,prepared=qty,batches=qty//4,quantile=None,features=f,model_bias=None,contributions=[],history_warning=bool(f.get('ood_flag')),policy_status=result['policy_status'],v4_plan=result,supply=dict(quantity=qty,raw_forecast=pred['model'],q75=q75,q90=q90,q75_raw=pred['model_q75'],q90_raw=pred['model_q90'],capacity=cap,required=qty,capacity_feasible=qty<=cap,initial_qty=result['initial_qty'],refills=result['production_batches'],policy='V4_ORIGINAL_ADAPTER',demand_scale=1,service_until='21:30')))
        return plans
    def price(self,sku,j,stock,prepared,previous,sales30,sales60,forecast,weather,as_of=None,observed_context=None):
        self.require_integrity();ctx=observed_context or {};minute=as_of if as_of is not None else SLOTS[j]
        if minute not in SLOTS:raise ValueError('M1 V4 chỉ chạy ở 5 checkpoint 19:30–21:30.')
        spec=self.master[sku];t=f'{minute//60:02}:{minute%60:02}';day=weather['date'];current=round(spec['unit_price_vnd_reference']*(1-previous/100));shelf=min(stock,int(spec['shelf_capacity_units_assumed']))
        from .v4_features.model_features import m1_features
        item=dict(sku_code=sku,prepared_qty=prepared,inventory_at_decision=stock,
            sold_last_30min=sales30,sold_last_60min=sales60,
            shelf_inventory=ctx.get('shelf_inventory',shelf),
            backroom_inventory=ctx.get('backroom_inventory',max(0,stock-shelf)),
            current_discount_pct=previous,baseline_announced_2100_pct=ctx.get('baseline_announced_2100_pct'),
            list_price_vnd=spec['unit_price_vnd_reference'],current_unit_price_vnd=ctx.get('current_unit_price_vnd',current),
            morning_features=ctx.get('morning_features') or self.morning.get((day,sku)) or {},
            unit_production_cost_vnd_assumed=spec['unit_production_cost_vnd_assumed'],
            unit_disposal_cost_vnd_assumed=spec['unit_disposal_cost_vnd_assumed'],
            markdown_action_cost_vnd_assumed=spec['markdown_action_cost_vnd_assumed'],
            qualitative_hot_sku_user_report=spec['qualitative_hot_sku_user_report'],
            observed_buyers_last30=ctx.get('observed_buyers_last30',sales30),
            observed_stockout_last60_minutes=ctx.get('observed_stockout_last60_minutes',0))
        f=m1_features(item,day+'T'+t+':00+07:00')
        if getattr(self.adapter,'JOINT_POLICY',False):
            f.update(history_rate_next30=ctx.get('history_rate_next30'),history_days=ctx.get('history_days',0))
        for c in self.manifest['MCOLS']:
            # The frozen preprocessor imputes undefined inventory cover at zero pace.
            if c in ('inventory_cover_minutes','baseline_announced_2100_pct') and f.get(c) is None:continue
            if f.get(c) is None or not math.isfinite(float(f[c])):raise ValueError('Thiếu/sai feature M1 V4: '+c)
        count=int(ctx.get('daily_count',0))
        with MODEL_LOCK:
            original=self.adapter._DAILY_CHANGE_TRACKER;self.adapter._DAILY_CHANGE_TRACKER={(day,sku):count}
            try:
                action=int(self.adapter.markdown({'model_features':f,'price_context':{'current_discount_pct':previous,'list_price_vnd':spec['unit_price_vnd_reference'],'last_price_change_at':ctx.get('last_price_change_at'),'last_price_change_minute':ctx.get('last_price_change_minute',-9999),'daily_count':count,'markdown_cost':ctx.get('markdown_cost',spec['markdown_action_cost_vnd_assumed'])}},day+'T'+t+':00+07:00'));next_count=self.adapter._DAILY_CHANGE_TRACKER.get((day,sku),count)
            finally:self.adapter._DAILY_CHANGE_TRACKER=original
            hold=min(stock,max(0.,float(self.m1['model'].predict([self.m1['preprocessor'].transform_row(f,previous,sku,spec)])[0])));candidates=[]
            for tier in LADDER:
                if not previous<=tier<=CAPS[j]:continue
                pred=max(0.,float(self.m1['model'].predict([self.m1['preprocessor'].transform_row(f,tier,sku,spec)])[0]))
                if not math.isfinite(pred):raise ValueError('M1 trả kết quả không hữu hạn.')
                candidates.append(dict(discount=tier,expected_sales_next30=min(stock,pred),expected_revenue=round(min(stock,pred)*spec['unit_price_vnd_reference']*(1-tier/100))))
        tier=previous if action==0 else action
        return dict(sku=sku,minute=minute,stock=stock,sales30=sales30,sales60=sales60,previous=previous,discount=tier,price=int(spec['unit_price_vnd_reference']),new_price=round(spec['unit_price_vnd_reference']*(1-tier/100)),cap=CAPS[j],floor=previous if minute>=1260 else 0,schedule=[],candidates=candidates,low_stock=stock<=sales30,reason='V4_EXPECTED_GAIN_OVER_HOLD' if action else 'V4_HOLD',v4_action=action,v4_daily_count=next_count,model_features=f,predicted_hold_next30=hold,pricing_policy=dict(version='V4_ORIGINAL_ADAPTER',projected_closing_stock_at_current_pace=f['projected_surplus_at_current_pace']),economic_gate=dict(status='V4_MODEL_ESTIMATED_GAIN' if action else 'V4_HOLD',evidence_id=self.version,qualification='Ước lượng của model; không phải hiệu quả nhân quả đã đo tại AEON.'))


# ---------------------------------------------------------------------------
# Outcome-feature helpers (used by tests/test_day_loop.py and next-day logic)
# ---------------------------------------------------------------------------
OUTCOME_FEATURES = ['lag1_waste_qty','lag7_waste_qty','lag1_sold_qty','lag7_sold_qty',
                    'lag1_prepared_qty','lag7_prepared_qty','lag1_discounted_qty',
                    'lag1_stockout','lag7_stockout']

def outcome_features(day: str, sku: str, outcomes: dict) -> dict:
    """Return a dict of lagged waste/sales/prepared features for *day* from *outcomes*.

    *outcomes* maps (date_str, sku_code) → dict with keys:
        prepared_qty, waste_qty, sold_qty (optional), stockout (optional),
        discounted_qty (optional), censored_demand_flag (optional)

    Only dates strictly before *day* are used, so there is no future data leakage.
    """
    from datetime import date as _date, timedelta as _td
    d = _date.fromisoformat(day)

    def _get(lag):
        past = str(d - _td(days=lag))
        row = outcomes.get((past, sku)) or outcomes.get((past, sku), {})
        if not isinstance(row, dict):
            row = {}
        return row

    r1 = _get(1); r7 = _get(7)
    return dict(
        lag1_waste_qty=float(r1.get('waste_qty') or 0),
        lag7_waste_qty=float(r7.get('waste_qty') or 0),
        lag1_sold_qty=float(r1.get('sold_qty') or 0),
        lag7_sold_qty=float(r7.get('sold_qty') or 0),
        lag1_prepared_qty=float(r1.get('prepared_qty') or 0),
        lag7_prepared_qty=float(r7.get('prepared_qty') or 0),
        lag1_discounted_qty=float(r1.get('discounted_qty') or 0),
        lag1_stockout=int(bool(r1.get('stockout') or r1.get('censored_demand_flag') or 0)),
        lag7_stockout=int(bool(r7.get('stockout') or r7.get('censored_demand_flag') or 0)),
    )

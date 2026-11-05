"""V4 Validation POS replay, isolated from inference and the 62-day scorer."""
from collections import defaultdict
from types import SimpleNamespace
import hashlib,json,subprocess,sys
from datetime import date,timedelta
from .engine import DATA,ROOT,read_csv
from .volume_scenario import VERSION, LEGACY_GENERATED_VERSION, LEGACY_VOLUME_VERSION, SCALE, PROFILES, scaled
from .seasonal_reference import anchor as seasonal_anchor

V2_HASH='1aa77e5d6ed0dffc2092c3e5e216b420e73527b2de9dacd772e14c156ef16948'
V2_WORKER_SHA256='a4f3f9082af6b0c230d41b08dab667feb8bfafa8ba2dc8b02748a67a92db306f'
class Simulator:
    def __init__(self,engine):
        self.engine=engine;self.version=VERSION;self.original_version='V4_MARKET_WORLD_V1';self.replay_version='V4_VALIDATION_POS_REPLAY_V1'
        self._world_hashes=json.loads((ROOT/'docs/SIMULATOR_INPUT_HASHES.json').read_text())
        self._volume_hashes=json.loads((ROOT/'docs/VOLUME_SIMULATOR_INPUT_HASHES.json').read_text())
        self.arrivals=SimpleNamespace(version=self.version,hash=self.hash_for(self.version),report=self.report)
        self.calendar={}
        for (day,sku),r in engine.morning.items():
            self.calendar.setdefault(day,dict(date=day,weekday_iso=r['weekday_iso'],is_weekend=r['is_weekend'],month=r['month'],day_of_year=date.fromisoformat(day).timetuple().tm_yday,
                is_public_holiday=r['is_public_holiday'],is_festival_non_public=0,prior_day_rain_mm=r['prior_day_rain_mm'],prior_day_temp_c=r['prior_day_temp_c'],
                forecast_rain_mm_previous_day1=r['prior_day_rain_mm'],forecast_temperature_max_c_previous_day1=r['prior_day_temp_c'],
                weather_reference_date=r['weather_reference_date'],forecast_source='V4_BUNDLED_PRIOR_DAY_PROXY',
                weather_provenance={'status':'RETROSPECTIVE_PRIOR_DAY_SIMULATION_ONLY','vintage_verified':False}))
        self.seed=self.history_before(min(self.calendar));self._events=defaultdict(list)
        for index,r in enumerate(read_csv(DATA/'simulated_POS.csv')):
            if r['branch']!='BASELINE':continue
            tm=r['transaction_at'][11:16];h,m=map(int,tm.split(':'));available=r['available_at']
            self._events[r['date']].append(dict(id=index,sku=r['sku_code'],minute=h*60+m,promo=0,required=0,draw=0,
                quantity=int(r['quantity']),available_at=available,transaction_at=r['transaction_at']))
    def hash_for(self,version):
        if version==self.replay_version:
            return hashlib.sha256((version+hashlib.sha256((DATA/'simulated_POS.csv').read_bytes()).hexdigest()).encode()).hexdigest()
        if version==self.version:
            files=[ROOT/'services/generated_market_worker.py',ROOT/'services/volume_scenario.py',ROOT/'services/simulator.py',ROOT/'services/seasonal_reference.py',DATA/'warmup_history.csv',DATA/'development_observed.csv']
            return hashlib.sha256((version+''.join(hashlib.sha256(p.read_bytes()).hexdigest() for p in files)).encode()).hexdigest()
        if version==LEGACY_GENERATED_VERSION:
            actual=hashlib.sha256((ROOT/'services/generated_market_worker_v2.py').read_bytes()).hexdigest()
            if actual!=V2_WORKER_SHA256:raise ValueError('Snapshot POS V2 không khớp.')
            return V2_HASH
        if version not in (LEGACY_VOLUME_VERSION,self.original_version):raise ValueError('Luồng mô phỏng không được hỗ trợ; tạo ca mới.')
        hashes=self._volume_hashes if version==LEGACY_VOLUME_VERSION else self._world_hashes
        for rel,expected in hashes.items():
            if version==LEGACY_VOLUME_VERSION and rel in ('services/volume_market_worker.py','services/volume_scenario.py'):
                continue  # Compatibility adapter preserves the V1 seed algorithm.
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=expected:raise ValueError('Checksum nguồn thị trường V4 không khớp.')
        return hashlib.sha256((version+json.dumps(hashes,sort_keys=True)).encode()).hexdigest()
    def _custodian(self,request,version=None):
        version=version or self.version
        self.hash_for(version)
        if version==self.version and request.get('market_context') is None:
            request=dict(request,market_context=self.market_context(request['day'],request.get('seed',42),[]))
        request=dict(request,holiday=bool(request.get('holiday',self.calendar.get(request['day'],{}).get('is_public_holiday'))))
        worker=('generated_market_worker.py' if version==self.version else
                'generated_market_worker_v2.py' if version==LEGACY_GENERATED_VERSION else
                'volume_market_worker.py' if version==LEGACY_VOLUME_VERSION else 'v4_market_worker.py')
        result=subprocess.run([sys.executable,str(ROOT/'services'/worker),str(ROOT/'simulation_only/v4/validation_world.jsonl')],input=json.dumps(request),text=True,encoding='utf-8',capture_output=True,timeout=30)
        if result.returncode:raise ValueError('Custodian mô phỏng V4 không trả dữ liệu hợp lệ.')
        value=json.loads(result.stdout)
        if 'error' in value:raise ValueError(value['error'])
        return value
    def observed_requests(self,s,destination):
        if s['simulator_version']==self.replay_version:
            return [e for e in self.events(s['day'],s['seed'],s['weather'],self.replay_version) if s['minute']<=e['minute']<destination]
        if s['simulator_version'] not in (self.version,LEGACY_GENERATED_VERSION) and s['day'] not in self.calendar:raise ValueError('Ngày chưa có nguồn mô phỏng V4.')
        return self._custodian(dict(operation='consume',day=s['day'],seed=s['seed'],start=s['minute'],end=destination,
            holiday=s['weather'].get('is_public_holiday',0),market_context=s.get('market_context'),
            discounts={sku:p['discount'] for sku,p in s['products'].items()}),s['simulator_version'])['requests']
    def evaluation_counts(self,day,version,market_context=None,seed=42):
        if version==self.replay_version:
            from collections import Counter
            c=Counter()
            for e in self.events(day,version=version):c[e['sku']]+=e.get('quantity',1)
            return c
        return self._custodian(dict(operation='closed_evaluation',day=day,market_context=market_context,seed=seed),version)['counts']
    def history_before(self,day,**kwargs):
        factor=SCALE if kwargs.get('version') in (self.version,LEGACY_GENERATED_VERSION,LEGACY_VOLUME_VERSION) else 1
        return {(r['date'],r['sku_code']):r['sold_qty']*factor for r in self.engine.observed if r['date']<day}
    def outcomes_before(self,day,version=None):
        return {(r['date'],r['sku_code']):dict(scaled(r) if version in (self.version,LEGACY_GENERATED_VERSION,LEGACY_VOLUME_VERSION) else r,stockout=int(r.get('censored_demand_flag',0))) for r in self.engine.observed if r['date']<day}

    def generated_weather(self,day):
        d=date.fromisoformat(day)
        if d.year!=2022:raise ValueError('POS tổng hợp V2 hiện chỉ có lịch feature 2022; cần lịch đã kiểm định cho năm khác.')
        previous=[key for key in self.calendar if key<=day]
        if not previous:raise ValueError('Chưa có thời tiết mẫu trước ngày mô phỏng.')
        if day in self.calendar:
            source_day=day
        else:
            recent=sorted(previous)[-14:]
            source_day=recent[int(hashlib.sha256(day.encode()).hexdigest()[:8],16)%len(recent)]
        original=self.calendar[source_day]
        from .v4_features.context_tools import event_context
        holiday=day in {'2022-05-02','2022-05-03'} or event_context(day)['event_stratum'] in ('public_holiday','tet_official')
        return dict(original,date=day,weekday_iso=d.isoweekday(),is_weekend=int(d.weekday()>=5),
            month=d.month,day_of_year=d.timetuple().tm_yday,is_public_holiday=int(holiday),
            weather_reference_date=(d-timedelta(days=1)).isoformat(),forecast_source='GENERATED_PRIOR_DAY_PROXY',
            weather_provenance={'status':'SIMULATION_ONLY_PRIOR_DAY_PROXY','vintage_verified':False,
                                'source_weather_day':source_day})

    def market_context(self,day,seed,closed):
        d=date.fromisoformat(day);weekday=d.weekday();holiday=bool(self.generated_weather(day)['is_public_holiday'])
        baseline_cutoff='2022-07-01' if day>='2022-07-01' else '2022-05-01'
        source_rows=self.engine.observed if day>='2022-07-01' else self.engine.seed_rows
        means={}
        for sku in self.engine.master:
            means[sku]=seasonal_anchor(day,[r for r in source_rows if r['sku_code']==sku],baseline_cutoff,holiday)*SCALE
        previous=next((s.get('market_context') for s in sorted(closed,key=lambda s:s['day'],reverse=True)
                       if s['day']<day and s.get('market_context')),None)
        prior_factor=float(previous.get('latent_factor',1.)) if previous else 1.
        draw=int(hashlib.sha256(f'{self.version}|{day}|{seed}|daily-market'.encode()).hexdigest()[:12],16)/16**12
        factor=max(.88,min(1.12,.8*prior_factor+.2+.06*(draw-.5)))
        return dict(version=self.version,day=day,seed=seed,baseline_through='2022-06-30' if day>='2022-07-01' else '2022-04-30',
                    mean_by_sku={sku:round(value*factor,3) for sku,value in means.items()},
                    trend_factor=round(factor,4),latent_factor=round(factor,4),prior_generated_days=len(closed),
                    source='PAST_X10_WEEKDAY_BASELINE_WITH_CAPPED_WEEKEND_AND_LATENT_VARIATION')
    def events(self,day,seed=42,weather=None,version=None):
        version=version or self.version
        self.hash_for(version)
        if version!=self.replay_version:raise ValueError('Không công bố tương lai của thị trường. Dùng worker cho cửa sổ đã trôi qua.')
        if day not in self.calendar:raise ValueError('Mô phỏng chỉ dùng ngày có POS V4 01/05–30/06/2022; ngày khác cần dữ liệu nhập.')
        return sorted(self._events[day],key=lambda e:(e['minute'],e['id']))
    def report(self):
        start=date(2022,5,1);dates=[(start+timedelta(days=i)).isoformat() for i in range(153)]
        return dict(type='Generated POS V3 from past baseline; V2 and V4 replay retained for old sessions',version=self.version,sha256=self.arrivals.hash,
            training_rows=0,train_until=None,calibrated_until=None,test_rows=0,test_from=None,evaluated_until=None,test_mae=None,sku_mean_baseline_mae=None,
            volume_scale=SCALE,hourly_profiles=PROFILES,dates=dates,scenarios=[{'version':self.version,'label':'POS sinh theo lịch sử baseline ×10 · biên độ cuối tuần giới hạn'}],note='POS V3 sinh lượt mua liên tục cho các ngày 2022. Mức cuối tuần được giới hạn theo giả định kịch bản AEON và có biến động theo ngày; chưa hiệu chỉnh bằng POS AEON thật. Nhu cầu nền độc lập với lượng JOINT chuẩn bị. Trọng số JOINT không tự train lại sau ca.')
    def comparison(self,day='2022-05-02',seed=42):
        raise ValueError('Không chạy F04 baseline vs AI trong prototype. Kết quả V4 đã khóa được xem riêng qua /api/reference.')

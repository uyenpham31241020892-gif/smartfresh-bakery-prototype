"""V4 Validation POS replay, isolated from inference and the 62-day scorer."""
from collections import defaultdict
from types import SimpleNamespace
import hashlib,json,subprocess,sys
from datetime import date,timedelta
from .engine import DATA,ROOT,read_csv
class Simulator:
    def __init__(self,engine):
        self.engine=engine;self.version='V4_MARKET_WORLD_V1';self.replay_version='V4_VALIDATION_POS_REPLAY_V1'
        self._world_hashes=json.loads((ROOT/'docs/SIMULATOR_INPUT_HASHES.json').read_text())
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
        if version!=self.version:raise ValueError('Luồng mô phỏng không phải V4; tạo ca V4 mới.')
        for rel,expected in self._world_hashes.items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=expected:raise ValueError('Checksum nguồn thị trường V4 không khớp.')
        return hashlib.sha256((version+json.dumps(self._world_hashes,sort_keys=True)).encode()).hexdigest()
    def _custodian(self,request):
        self.hash_for(self.version)
        result=subprocess.run([sys.executable,str(ROOT/'services/v4_market_worker.py'),str(ROOT/'simulation_only/v4/validation_world.jsonl')],input=json.dumps(request),text=True,encoding='utf-8',capture_output=True,timeout=20)
        if result.returncode:raise ValueError('Custodian mô phỏng V4 không trả dữ liệu hợp lệ.')
        value=json.loads(result.stdout)
        if 'error' in value:raise ValueError(value['error'])
        return value
    def observed_requests(self,s,destination):
        if s['simulator_version']==self.replay_version:
            return [e for e in self.events(s['day'],s['seed'],s['weather'],self.replay_version) if s['minute']<=e['minute']<destination]
        if s['day'] not in self.calendar:raise ValueError('Ngày chưa có nguồn mô phỏng V4.')
        return self._custodian(dict(operation='consume',day=s['day'],start=s['minute'],end=destination,discounts={sku:p['discount'] for sku,p in s['products'].items()}))['requests']
    def evaluation_counts(self,day,version):
        if version==self.replay_version:
            from collections import Counter
            c=Counter()
            for e in self.events(day,version=version):c[e['sku']]+=e.get('quantity',1)
            return c
        return self._custodian(dict(operation='closed_evaluation',day=day))['counts']
    def history_before(self,day,**kwargs):
        return {(r['date'],r['sku_code']):r['sold_qty'] for r in self.engine.observed if r['date']<day}
    def outcomes_before(self,day):
        return {(r['date'],r['sku_code']):dict(r,stockout=int(r.get('censored_demand_flag',0))) for r in self.engine.observed if r['date']<day}
    def events(self,day,seed=42,weather=None,version=None):
        version=version or self.version
        self.hash_for(version)
        if version!=self.replay_version:raise ValueError('Không công bố tương lai của thị trường. Dùng worker cho cửa sổ đã trôi qua.')
        if day not in self.calendar:raise ValueError('Mô phỏng chỉ dùng ngày có POS V4 01/05–30/06/2022; ngày khác cần dữ liệu nhập.')
        return sorted(self._events[day],key=lambda e:(e['minute'],e['id']))
    def report(self):
        return dict(type='V4 market simulation with custodian process; optional observed-POS replay',version=self.version,sha256=self.arrivals.hash,
            training_rows=0,train_until=None,calibrated_until=None,test_rows=0,test_from=None,evaluated_until=None,test_mae=None,sku_mean_baseline_mae=None,
            dates=sorted(self.calendar),scenarios=[{'version':self.version,'label':'Thị trường V4 có phản ứng giá giả định gốc'},{'version':self.replay_version,'label':'Replay POS V4 quan sát, không sinh khách mới'}],note='Thị trường dùng sự kiện Validation V4 và quy tắc phản ứng giá gốc strength 0.6; worker chỉ trả lượt mua trong cửa sổ đã trôi qua. Replay giữ giao dịch quan sát riêng. Cả hai là mô phỏng, không phải đo tại AEON hay chạy lại test 62 ngày.')
    def comparison(self,day='2022-05-02',seed=42):
        raise ValueError('Không chạy F04 baseline vs AI trong prototype. Kết quả V4 đã khóa được xem riêng qua /api/reference.')

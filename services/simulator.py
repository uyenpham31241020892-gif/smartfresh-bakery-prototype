"""Synthetic events stay on the simulator side of the inference boundary."""
from functools import lru_cache
import hashlib
import json
import numpy as np
import pandas as pd
from .engine import DATA, ROOT, SLOTS, END
from .arrivals import Arrivals

class Simulator:
    def __init__(self, engine):
        self.engine = engine
        self.arrivals = Arrivals()
        self.version = self.arrivals.version
        self.calendar = pd.read_csv(DATA / 'weather_forecast_feed_2022.csv').fillna({'public_holiday_name': ''}).set_index('date').to_dict('index')
        h = pd.read_csv(DATA / 'history_through_aug15_synthetic.csv')
        self.seed = {(r.date, r.sku_code): int(r.sold_qty) for r in h.itertuples()}
    @lru_cache(maxsize=200)
    def legacy_events(self, day, seed=42):
        """New seeded demo arrivals; original V9 observations are absent from ZIP.

        This is an explicit simulator extension, never presented as reproduction
        of the archived September experiment or an independent model evaluation.
        """
        entropy = int.from_bytes(hashlib.sha256(f'{day}:{seed}'.encode()).digest()[:8], 'little')
        rng = np.random.default_rng(entropy)
        events = []
        for sku in self.engine.master:
            n = int(rng.poisson(self.engine.means[sku]))
            fractions = [self.engine.organic[(sku, j)] for j in range(5)]
            bins = rng.multinomial(n, [1 - sum(fractions)] + fractions)
            for j, count in enumerate(bins):
                times = (480 + rng.beta(2.4, 1.8, count) * 690).astype(int) if j == 0 else rng.integers(SLOTS[j - 1], SLOTS[j - 1] + 30, count)
                for t in times:
                    events.append({'id': len(events), 'sku': sku, 'minute': int(t), 'promo': 0, 'required': 0, 'draw': 0})
            for j, t in enumerate(SLOTS):
                from .engine import LADDER
                response = np.maximum.accumulate([self.engine.emp.get((sku, j, tier), 0) for tier in LADDER])
                for k in range(1, len(LADDER)):
                    count = int(rng.poisson(max(0, response[k] - response[k - 1]) / .6))
                    for _ in range(count):
                        events.append({'id': len(events), 'sku': sku, 'minute': int(rng.integers(t, t + 30)),
                                       'promo': 1, 'required': LADDER[k], 'draw': float(rng.random())})
        return sorted(events, key=lambda x: (x['minute'], x['id']))

    def events(self, day, seed=42, weather=None, version=None):
        if version == 'new_seeded_demo_v1':
            return self.legacy_events(day,seed)
        if version not in [None,self.version]:
            raise ValueError('Không có phiên bản bộ mô phỏng đã ghim cho ca này.')
        weather=weather or self.calendar.get(day)
        if weather is None:
            raise ValueError('Bộ mô phỏng cần forecast đúng ngày, không tự tạo thời tiết.')
        return self._trained_events(day,seed,json.dumps(weather,sort_keys=True,default=str))

    @lru_cache(maxsize=200)
    def _trained_events(self,day,seed,weather_json):
        from .engine import LADDER
        weather=json.loads(weather_json)
        entropy=int.from_bytes(hashlib.sha256(f'{self.version}:{day}:{seed}:{weather_json}'.encode()).digest()[:8],'little')
        rng=np.random.default_rng(entropy)
        events=[]
        for sku in self.engine.master:
            mean=self.arrivals.mean(day,sku,weather)
            residual=float(rng.choice(self.arrivals.model['noise'][sku]))
            count=max(0,min(int(round(mean+residual)),int(self.arrivals.model['daily_caps'][sku])))
            bins=rng.multinomial(count,self.arrivals.model['profiles'][sku])
            for j,n in enumerate(bins):
                if j==0:
                    times=(480+rng.beta(2.4,1.8,n)*630).astype(int)
                else:
                    start=1110 if j==1 else 1140 if j==2 else SLOTS[j-3]
                    times=rng.integers(start,start+30,n)
                for t in times:
                    events.append({'id':len(events),'sku':sku,'minute':int(t),'promo':0,'required':0,'draw':0})
            for j,t in enumerate(SLOTS):
                response=np.maximum.accumulate([self.arrivals.promo.get((sku,j,tier),0) for tier in LADDER])
                for k in range(1,len(LADDER)):
                    for _ in range(int(rng.poisson(max(0,response[k]-response[k-1])/.6))):
                        events.append({'id':len(events),'sku':sku,'minute':int(rng.integers(t,t+30)),
                                       'promo':1,'required':LADDER[k],'draw':float(rng.random())})
        return sorted(events,key=lambda x:(x['minute'],x['id']))

    def simulate(self, day, visible, system='M1_M2_SELECTED', seed=42):
        weather = self.calendar[day]
        plans = self.engine.plan(day, visible, weather)
        if system == 'BASELINE':
            for p in plans:
                p['prepared'] = p['baseline']
        products = {p['sku']: {'prepared': p['prepared'], 'stock': p['prepared'], 'discount': 0,
                              'forecast': p['forecast'], 'sold': 0, 'revenue': 0, 'lost': 0, 'sales': []} for p in plans}
        cursor = 360
        decisions, ledger = [], []
        for minute in SLOTS + [END]:
            for ev in self.events(day, seed, weather):
                if not cursor <= ev['minute'] < minute:
                    continue
                p = products[ev['sku']]
                if ev['promo'] and (ev['required'] > p['discount'] or ev['draw'] > .6):
                    continue
                if p['stock']:
                    p['stock'] -= 1
                    p['sold'] += 1
                    paid = int(round(self.engine.master[ev['sku']]['unit_price_vnd_reference'] * (1 - p['discount'] / 100)))
                    p['revenue'] += paid
                    p['sales'].append(ev['minute'])
                    ledger.append({'sku': ev['sku'], 'minute': ev['minute'], 'paid': paid, 'discount': p['discount']})
                else:
                    p['lost'] += 1
            cursor = minute
            if minute == END:
                break
            j = SLOTS.index(minute)
            for sku, p in products.items():
                s30 = sum(x >= minute - 30 for x in p['sales'])
                s60 = sum(x >= minute - 60 for x in p['sales'])
                if system == 'BASELINE':
                    discount = 30 if minute >= 1260 else 0
                else:
                    proposal = self.engine.price(sku, j, p['stock'], p['prepared'], p['discount'], s30, s60, p['forecast'], weather)
                    discount = proposal['discount']
                decisions.append({'sku': sku, 'minute': minute, 'stock': p['stock'], 'discount': discount})
                p['discount'] = discount
        return products, decisions, ledger, plans

    @lru_cache(maxsize=80)
    def history_before(self, day, system='M1_M2_SELECTED', seed=42):
        if day < '2022-08-16' or day not in self.calendar:
            raise ValueError('Kịch bản V9 hỗ trợ 16/08–30/09/2022. Ngày mới cần file lịch sử và dự báo thời tiết.')
        visible = dict(self.seed)
        for d in sorted(self.calendar):
            if '2022-08-16' <= d < day:
                products, _, _, _ = self.simulate(d, visible, system, seed)
                for sku, p in products.items():
                    visible[(d, sku)] = p['sold']
        return visible

"""Frozen V9 inference. No simulator data or holdout outcomes are read here."""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/current_v9'
SLOTS = [1170, 1200, 1230, 1260, 1290]
LADDER = [0, 20, 25, 30, 35, 40, 45, 50]
CAPS = [20, 25, 35, 45, 50]
FLOORS = [0, 0, 0, 30, 30]
END = 1320
OUTCOME_FEATURES = ['lag1_prepared_qty','lag1_waste_qty','lag1_stockout','lag1_discounted_qty','lag7_waste_qty','rolling7_waste_rate','same_weekday_waste_mean']


def outcome_features(day,sku,outcomes=None):
    outcomes=outcomes or {}
    def past(k):
        d=(pd.Timestamp(day)-pd.Timedelta(days=k)).strftime('%Y-%m-%d')
        return outcomes.get((d,sku),{})
    last,week=past(1),past(7)
    recent=[past(k) for k in range(1,8)]
    same=[past(k).get('waste_qty',0) for k in [7,14,21,28] if past(k)]
    prepared=sum(r.get('prepared_qty',0) for r in recent)
    return {'lag1_prepared_qty':last.get('prepared_qty',0),'lag1_waste_qty':last.get('waste_qty',0),
            'lag1_stockout':last.get('stockout',0),'lag1_discounted_qty':last.get('discounted_qty',0),
            'lag7_waste_qty':week.get('waste_qty',0),'rolling7_waste_rate':sum(r.get('waste_qty',0) for r in recent)/prepared if prepared else 0,
            'same_weekday_waste_mean':float(np.mean(same)) if same else 0.}


def encode(rows, columns):
    return pd.get_dummies(pd.DataFrame(rows), columns=['sku_code'], dtype=float).astype(float).reindex(columns=columns, fill_value=0.)


@lru_cache(None)
def schedules(start, previous):
    found = []
    def walk(j, prev, path):
        if j == 5:
            found.append(path)
            return
        for v in LADDER:
            if max(prev, FLOORS[j]) <= v <= CAPS[j]:
                walk(j + 1, v, path + [v])
    walk(start, previous, [])
    return np.asarray(found, dtype=np.int16)


class Engine:
    def __init__(self, model_dir=None):
        model_dir = Path(model_dir or ROOT / 'models')
        self.manifest = json.loads((model_dir / 'manifest.json').read_text(encoding='utf-8'))
        for name, checksum in self.manifest['native_model_hashes'].items():
            if hashlib.sha256((model_dir / name).read_bytes()).hexdigest() != checksum:
                raise ValueError('Model checksum mismatch: ' + name)
        self.m1 = lgb.Booster(model_file=str(model_dir / 'm1.txt'))
        self.m2 = lgb.Booster(model_file=str(model_dir / 'm2.txt'))
        if self.m1.feature_name() != self.manifest['MCOLS'] or self.m2.feature_name() != self.manifest['COLS']:
            raise ValueError('Feature order does not match the frozen model bundle')
        self.skus = pd.read_csv(DATA / 'SKU_Master.csv').to_dict('records')
        self.master = {s['sku_code']: s for s in self.skus}
        self.means = self.manifest['means']
        self.offsets = {tuple(r['key']): r['value'] for r in self.manifest['residual_offsets']}
        self.emp = {tuple(r['key']): r['value'] for r in self.manifest['emp']}
        self.organic = {tuple(r['key']): r['value'] for r in self.manifest['organic_fracs']}
        self.selection = self.manifest['selection']
        self.version = self.manifest['version']

    def features(self, day, sku, visible, weather, outcomes=None):
        d = pd.Timestamp(day)
        values = []
        for k in range(1, 36):
            key = ((d - pd.Timedelta(days=k)).strftime('%Y-%m-%d'), sku)
            if key not in visible:
                break
            values.append(float(visible[key]))
        arr = np.asarray(values)
        mean = self.means[sku]
        weekday = int(weather['weekday_iso'])
        f = {'sku_code': sku, 'weekday': weekday, 'is_weekend': weather['is_weekend'],
             'is_holiday': weather['is_public_holiday'], 'festival_nonpublic': weather['is_festival_non_public'],
             'month': weather['month'], 'dayofyear': weather['day_of_year'],
             'weekday_sin': math.sin(2 * math.pi * weekday / 7), 'weekday_cos': math.cos(2 * math.pi * weekday / 7),
             'rain_forecast_proxy': weather['forecast_rain_mm_previous_day1'],
             'temp_forecast_jma': weather['forecast_temperature_max_c_previous_day1'],
             'calendar_month_trend': weather['month'] - 6, 'lag1_sales': float(arr[0]) if len(arr) else mean,
             'lag7_sales': float(arr[6]) if len(arr) >= 7 else mean,
             'rolling7_sales': float(arr[:7].mean()) if len(arr) else mean,
             'rolling14_sales': float(arr[:14].mean()) if len(arr) else mean,
             'rolling7_std': float(arr[:7].std()) if len(arr) > 1 else .11 * mean,
             'history_days': len(arr), 'ref_mean_train_only': mean}
        if any(n in self.manifest['COLS'] for n in OUTCOME_FEATURES):
            f.update(outcome_features(day,sku,outcomes))
        return f

    def baseline(self, day, sku, visible):
        d = pd.Timestamp(day)
        vals = [visible[((d - pd.Timedelta(days=k)).strftime('%Y-%m-%d'), sku)] for k in range(1, 8)
                if ((d - pd.Timedelta(days=k)).strftime('%Y-%m-%d'), sku) in visible]
        mean = float(np.mean(vals)) if vals else self.means[sku]
        return max(4, int(4 * math.ceil(mean * 1.29 * (1.07 if d.weekday() >= 5 else 1) / 4)))

    def plan(self, day, visible, weather, outcomes=None):
        rows = [self.features(day, s, visible, weather,outcomes) for s in self.master]
        X = encode(rows, self.manifest['COLS'])
        predictions = np.maximum(0, self.m2.predict(X, num_threads=2))
        contributions = self.m2.predict(X, pred_contrib=True, num_threads=2)
        plans = []
        for i, (sku, f, pred) in enumerate(zip(self.master, rows, predictions)):
            base = self.baseline(day, sku, visible)
            offset = self.offsets[(self.selection['selected_q'], sku)]
            floor = 4 * math.ceil(self.selection['selected_prep_floor'] * base / 4)
            prepared = max(4, 4 * math.ceil((float(pred) + offset) / 4), floor)
            impacts = sorted(zip(self.manifest['COLS'], contributions[i, :-1]), key=lambda x: abs(x[1]), reverse=True)[:6]
            plans.append({'sku': sku, 'name': self.master[sku]['product_name_reference'].removeprefix('AEON BREAD '),
                          'price': int(self.master[sku]['unit_price_vnd_reference']), 'baseline': base,
                          'forecast': float(pred), 'buffer': float(offset), 'floor': floor, 'prepared': prepared,
                          'batches': prepared // 4, 'quantile': self.selection['selected_q'],
                          'features': f, 'model_bias': float(contributions[i, -1]),
                          'contributions': [{'feature': n, 'units': float(v)} for n, v in impacts],
                          'history_warning': f['history_days'] < 7})
        return plans

    def promo(self, sku, weather):
        entries = [{'slot': j, 'discount_pct': tier, 'weekday': weather['weekday_iso'],
                    'is_weekend': weather['is_weekend'], 'is_holiday': weather['is_public_holiday'],
                    'rain_jma': weather['forecast_rain_mm_previous_day1'],
                    'temp_jma': weather['forecast_temperature_max_c_previous_day1'], 'sku_code': sku}
                   for j in range(5) for tier in LADDER]
        fit = self.m1.predict(encode(entries, self.manifest['MCOLS']), num_threads=2).reshape(5, len(LADDER))
        empirical = np.array([[self.emp.get((sku, j, t), 0) for t in LADDER] for j in range(5)])
        estimates = np.maximum.accumulate(np.maximum(0, .35 * fit + .65 * empirical), axis=1)
        estimates[:, 0] = 0
        return estimates

    def price(self, sku, j, stock, prepared, previous, sales30, sales60, forecast, weather, as_of=None):
        if previous not in LADDER or not 0 <= j < 5 or not 0 <= stock <= prepared:
            raise ValueError('Invalid pricing inputs')
        price = int(self.master[sku]['unit_price_vnd_reference'])
        sched = schedules(j, previous)
        if not len(sched):
            raise ValueError('No schedule satisfies the frozen policy')
        promo = self.promo(sku, weather)
        total = max(float(forecast or self.means[sku]), float(prepared - stock))
        base = np.array([total * self.organic[(sku, k)] for k in range(j, 5)])
        expected = max(float(base.sum()), min(10., .12 * sales60 * len(base)))
        if base.sum() > 0:
            base *= expected / base.sum()
        remaining = np.full(len(sched), float(stock))
        revenue = np.zeros(len(sched))
        for k in range(j, 5):
            tiers = sched[:, k - j]
            demand = np.maximum(0, base[k - j] + promo[k, np.searchsorted(LADDER, tiers)])
            if k==j and as_of is not None:
                demand*=max(0.,min(1.,(SLOTS[j]+30-as_of)/30))
            sold = np.minimum(remaining, demand)
            revenue += sold * price * (1 - tiers / 100)
            remaining -= sold
        score = revenue - remaining * .025 * price - sched.sum(axis=1) * .00001
        pick = int(np.argmax(score))
        choice = int(sched[pick, 0]) if stock else max(previous, FLOORS[j])
        candidates = []
        for tier in sorted(set(int(t) for t in sched[:, 0])):
            indices = np.where(sched[:, 0] == tier)[0]
            idx = int(indices[np.argmax(score[indices])])
            candidates.append({'discount': tier, 'expected_revenue': float(revenue[idx]),
                               'expected_leftover': float(remaining[idx]), 'objective': float(score[idx]),
                               'schedule': sched[idx].tolist()})
        return {'sku': sku, 'minute': SLOTS[j], 'stock': stock, 'sales30': sales30, 'sales60': sales60,
                'previous': previous, 'discount': choice, 'price': price,
                'new_price': int(round(price * (1 - choice / 100))), 'cap': CAPS[j], 'floor': FLOORS[j],
                'schedule': sched[pick].tolist(), 'candidates': candidates,
                'low_stock': stock <= max(3, round(sales60 / 2)),
                'reason': 'OUT_OF_STOCK_MAINTAIN_PUBLIC_FLOOR' if stock == 0 else 'JOINT_FORECAST_REVENUE_PLANNING'}

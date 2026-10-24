"""Frozen V606 inference: public as-of context only; never loads training/private CSVs."""
import csv
import json
import math
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / 'SmartFresh_V606_Trained_Models'
PUBLIC = ROOT / '03_TEST_POS_RUNTIME'
CONTRACT = json.loads((MODELS / 'feature_contract.json').read_text(encoding='utf-8'))
with (PUBLIC / 'sku_master.csv').open(encoding='utf-8-sig', newline='') as f:
    MASTER = {r['sku_code']: r for r in csv.DictReader(f)}


@lru_cache(None)
def models():
    # Supplied, trusted training artifacts. No fitting or updating in this module.
    m2 = xgb.Booster()
    m2.load_model(MODELS / 'M2_censored_xgboost.json')
    return (joblib.load(MODELS / 'M2_preprocessor.joblib'), m2,
            joblib.load(MODELS / 'M1_logged_action_imitation.joblib'))


def frame(features, columns):
    if features.get('sku_code') not in MASTER:
        raise ValueError('Unsupported V606 SKU')
    missing = set(columns) - features.keys()
    if missing:
        raise ValueError('Missing contracted features: ' + ', '.join(sorted(missing)))
    # Extra context, outcomes, logged actions, hidden fields NEVER enter X.
    return pd.DataFrame([{k: np.nan if features[k] is None else features[k]
                          for k in columns}], columns=columns)


def prepare(morning_features, completed_own_branch_history):
    f = morning_features
    day = f['date']
    if f['history_through'] >= day or f['weather_reference_date'] >= day:
        raise ValueError('Future/same-day history or weather rejected')
    if not completed_own_branch_history or any(
        r['date'] >= day or r['sku_code'] != f['sku_code']
        for r in completed_own_branch_history
    ):
        raise ValueError('History must be completed, past and own SKU')
    spec = MASTER[f['sku_code']]
    batch, cap = int(spec['batch_size_units_assumed']), int(spec['daily_capacity_units_assumed'])
    x = frame(f, CONTRACT['m2_predictive_columns'])
    pre, m2, _ = models()
    prediction = float(m2.predict(xgb.DMatrix(pre.transform(x).astype(float)))[0])
    if not math.isfinite(prediction):
        raise ValueError('Non-finite M2 prediction')
    status = 'FROZEN_M2_DAY_LOWER_BOUND_MODEL_NOT_SERVICE_GUARANTEE'
    if f['ood_flag']:
        # Declared baseline fallback, based on this branch's completed history only.
        recent = sorted(completed_own_branch_history, key=lambda r: r['date'])[-7:]
        prediction = sum(r['sold_qty'] for r in recent) / len(recent) * 1.12
        if sum(r['censored_demand_flag'] for r in recent) / len(recent) >= .5:
            prediction = max(prediction, recent[-1]['prepared_qty'] * 1.05)
        status = 'OOD_DECLARED_BASELINE_FALLBACK_MANAGER_REVIEW'
    qty = min(cap // batch * batch, max(batch, math.ceil(max(0, prediction) / batch) * batch))
    return dict(initial_qty=qty, production_batches=[], policy_status=status)


def markdown(observed_state, as_of):
    f = observed_state['model_features']
    if f['time'] != as_of[11:16]:
        raise ValueError('M1 checkpoint does not match as-of time')
    x = frame(f, CONTRACT['m1_pre_action_columns'])
    _, _, m1 = models()
    if m1['columns'] != CONTRACT['m1_pre_action_columns']:
        raise ValueError('M1 feature contract mismatch')
    action = str(m1['classifier'].predict(m1['preprocessor'].transform(x))[0])
    price = observed_state['price_context']
    # No early-discount causal evidence: declared policy retains current price before 21h.
    cash = int(price['current_unit_price_vnd'])
    reference = MASTER[f['sku_code']]['markdown_price_vnd_reference']
    if action == 'MARKDOWN_LOGGED' and f['time'] >= '21:00' and reference:
        cash = min(cash, int(reference))
    return {'approved_cash_price_vnd': cash}

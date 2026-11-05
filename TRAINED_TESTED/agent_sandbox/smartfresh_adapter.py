"""
SmartFresh Frozen Model Adapter — V4 Profit-Maximizing Iteration (smartfresh_adapter.py)
========================================================================================
Chiến lược V4: Tối đa hóa Doanh thu & Dùng M1 làm lưới an toàn.
1. M2: Đẩy mục tiêu cung ứng lên Q75-Q90 để triệt tiêu Lost Sales.
2. M1: Nới lỏng ngưỡng phạt rủi ro và ngưỡng chặn, sẵn sàng xả hàng khi P_sellout < 88%.
"""

import os
import sys
import json
import math
import joblib
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = BASE_DIR.parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
MODELS_DIR = REPOSITORY_ROOT / "models" / "joint"
M2_BUNDLE_PATH = MODELS_DIR / "m2_forecast_bundle.joblib"
M1_BUNDLE_PATH = MODELS_DIR / "m1_pricing_q_bundle.joblib"
LOOKUP_PATH = MODELS_DIR / "operational_lookup.json"
POLICY_PATH = MODELS_DIR / "policy_config.json"

_M2_BUNDLE = None
_M1_BUNDLE = None
_OPERATIONAL_LOOKUP = None
_POLICY_CONFIG = None
_DAILY_CHANGE_TRACKER = {}

class M2Preprocessor:
    def __init__(self, sku_list, event_list, numeric_cols):
        self.sku_list = list(sku_list)
        self.event_list = list(event_list)
        self.numeric_cols = list(numeric_cols)

    def transform_row(self, r, sku, spec):
        vec = [1.0 if sku == s else 0.0 for s in self.sku_list]
        ev = r.get("event_stratum", "ordinary")
        vec.extend([1.0 if ev == e else 0.0 for e in self.event_list])
        for c in self.numeric_cols:
            val = r.get(c, 0.0)
            if val in ("", None, "None") or (isinstance(val, float) and math.isnan(val)):
                vec.append(0.0)
            else:
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    vec.append(0.0)
        cap = float(r.get("operational_daily_capacity_units") or spec.get("daily_capacity_units_assumed", 100))
        lead = float(r.get("operational_lead_minutes") or spec.get("production_lead_time_minutes_assumed", 120))
        cost = float(r.get("known_unit_production_cost_vnd") or spec.get("unit_production_cost_vnd_assumed", 12000))
        vec.extend([cap, lead, cost])
        return vec

class M1Preprocessor:
    def __init__(self, sku_list, event_list, numeric_cols):
        self.sku_list = list(sku_list)
        self.event_list = list(event_list)
        self.numeric_cols = list(numeric_cols)

    def transform_row(self, r, candidate_discount_pct, sku, spec):
        vec = [1.0 if sku == s else 0.0 for s in self.sku_list]
        ev = r.get("event_stratum", "ordinary")
        vec.extend([1.0 if ev == e else 0.0 for e in self.event_list])
        t_str = str(r.get("time", "19:30"))
        try:
            h, m = map(int, t_str.split(":"))
            vec.append(float(h * 60 + m))
        except Exception:
            vec.append(1170.0)
        vec.append(float(candidate_discount_pct))
        for c in self.numeric_cols:
            val = r.get(c, 0.0)
            if val in ("", None, "None") or (isinstance(val, float) and math.isnan(val)):
                vec.append(0.0)
            else:
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    vec.append(0.0)
        cap = float(r.get("operational_daily_capacity_units") or spec.get("daily_capacity_units_assumed", 100))
        lead = float(r.get("operational_lead_minutes") or spec.get("production_lead_time_minutes_assumed", 120))
        cost = float(r.get("known_unit_production_cost_vnd") or spec.get("unit_production_cost_vnd_assumed", 12000))
        vec.extend([cap, lead, cost])
        return vec

def _load_artifacts():
    global _M2_BUNDLE, _M1_BUNDLE, _OPERATIONAL_LOOKUP, _POLICY_CONFIG
    if _M2_BUNDLE is None and M2_BUNDLE_PATH.exists():
        _M2_BUNDLE = joblib.load(M2_BUNDLE_PATH)
    if _M1_BUNDLE is None and M1_BUNDLE_PATH.exists():
        _M1_BUNDLE = joblib.load(M1_BUNDLE_PATH)
    if _OPERATIONAL_LOOKUP is None and LOOKUP_PATH.exists():
        _OPERATIONAL_LOOKUP = json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))
    if _POLICY_CONFIG is None and POLICY_PATH.exists():
        _POLICY_CONFIG = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

def _clean_num(val, default=0.0):
    if val is None or val == "" or val == "None":
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default

# --- Gate ---
def gate(event, as_of, known_skus, seen_ids, expected_price_version, max_age_minutes=30):
    try:
        now = datetime.fromisoformat(as_of)
        at = datetime.fromisoformat(event["event_at"])
        if now.tzinfo is None or at.tzinfo is None:
            return "QUARANTINE_TIMEZONE"
        if event["sku_code"] not in known_skus:
            return "QUARANTINE_UNKNOWN_SKU"
        if event["event_id"] in seen_ids:
            return "DROP_DUPLICATE"
        if at > now:
            return "QUARANTINE_FUTURE_EVENT"
        q = event["quantity"]
        p = event["unit_price_vnd"]
        if isinstance(q, bool) or not isinstance(q, int) or q <= 0:
            return "QUARANTINE_QUANTITY"
        if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
            return "QUARANTINE_PRICE"
        if event["price_version"] != expected_price_version:
            return "RECONCILE_PRICE_VERSION"
        if (now - at).total_seconds() > max_age_minutes * 60:
            return "HOLD_FOR_STALE_FEED"
        return "ACCEPT"
    except (ValueError, TypeError, KeyError):
        return "QUARANTINE_SCHEMA"

# --- Joint operating policy: preserve the selected preprocessors and artifact IO. ---
from services.joint_policy import depromo_features, prepare as joint_prepare, pricing as joint_pricing

_LAST_PRICE_EVIDENCE = {}
JOINT_POLICY = True

def prepare_features(morning_features, completed_own_branch_history):
    return depromo_features(morning_features, completed_own_branch_history)

def prepare(morning_features, completed_own_branch_history):
    _load_artifacts()
    if _M2_BUNDLE is None:raise ValueError('Missing M2 bundle')
    sku=morning_features['sku_code']
    return joint_prepare(morning_features,completed_own_branch_history,_M2_BUNDLE,_OPERATIONAL_LOOKUP[sku])

def markdown(observed_state, as_of):
    _load_artifacts()
    if _M1_BUNDLE is None:raise ValueError('Missing M1 bundle')
    features=observed_state['model_features'];sku=features['sku_code']
    context=dict(observed_state.get('price_context',{}))
    context.setdefault('daily_count',_DAILY_CHANGE_TRACKER.get((as_of[:10],sku),0))
    result=joint_pricing(features,context,_M1_BUNDLE,_OPERATIONAL_LOOKUP[sku],_POLICY_CONFIG)
    _LAST_PRICE_EVIDENCE[(as_of,sku)]=result
    # Proposing or rejecting a price does not consume an applied-change allowance.
    return result['action']

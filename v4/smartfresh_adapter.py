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
MODELS_DIR = BASE_DIR / "artifacts_build" / "models"
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
    import __main__
    if not hasattr(__main__, "M2Preprocessor"):
        __main__.M2Preprocessor = M2Preprocessor
    if not hasattr(__main__, "M1Preprocessor"):
        __main__.M1Preprocessor = M1Preprocessor
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

# --- Prepare (M2) ---
def prepare(morning_features, completed_own_branch_history):
    _load_artifacts()
    sku = morning_features["sku_code"]
    spec = _OPERATIONAL_LOOKUP.get(sku, {}) if _OPERATIONAL_LOOKUP else {}

    batch_size = int(spec.get("batch_size_units_assumed", 4))
    max_batch = int(spec.get("max_batch_units_assumed", 100))
    daily_cap = int(_clean_num(morning_features.get("operational_daily_capacity_units"), spec.get("daily_capacity_units_assumed", 100)))
    lead_min = int(_clean_num(morning_features.get("operational_lead_minutes"), spec.get("production_lead_time_minutes_assumed", 120)))
    last_ready = spec.get("last_production_ready_time_assumed", "19:30")

    weekday_iso = int(_clean_num(morning_features.get("weekday_iso"), 1))
    
    # Không khử nhiễu lượng bán ngày hôm trước nữa, lấy số thô để M2 "tham lam" hơn
    if _M2_BUNDLE is not None:
        preprocessor = _M2_BUNDLE["preprocessor"]
        vec = preprocessor.transform_row(morning_features, sku, spec)
        try:
            q50 = float(_M2_BUNDLE["model"].predict([vec])[0])
        except:
            q50 = 20.0
        try:
            q75 = float(_M2_BUNDLE.get("model_q75", _M2_BUNDLE["model"]).predict([vec])[0])
            if q75 <= q50: q75 = q50 * 1.15
        except:
            q75 = q50 * 1.15
        try:
            q90 = float(_M2_BUNDLE.get("model_q90", _M2_BUNDLE["model"]).predict([vec])[0])
            if q90 <= q75: q90 = q75 * 1.15
        except:
            q90 = q75 * 1.15
    else:
        recent = [r["sold_qty"] for r in completed_own_branch_history[-7:]] if completed_own_branch_history else [16]
        q50 = sum(recent) / len(recent)
        q75, q90 = q50 * 1.15, q50 * 1.30

    is_slow_sku = sku in ("TP-CP-001", "TP-RV-001")
    is_hot_sku = sku in ("TP-DN-001", "TP-CR-001")

    # BƠM MẠNH SẢN LƯỢNG M2 Ở V4
    if is_slow_sku:
        if weekday_iso in (2, 3):
            planned_raw = q50  # V4: q50 cho SKU bán chậm ngày giữa tuần
        else:
            planned_raw = 0.5 * q50 + 0.5 * q75 + 1.0  # Nâng buffer
        total_qty = int(math.ceil(planned_raw / batch_size) * batch_size) # Quay lại math.ceil
    else:
        if weekday_iso in (2, 3):
            planned_raw = 0.70 * q50 + 0.30 * q75 + 1.0
        elif weekday_iso in (1, 4, 5):
            planned_raw = q75 + (2.0 if is_hot_sku else 1.0)
        else: # Cuối tuần - Bung nóc!
            planned_raw = q90 + (3.5 if is_hot_sku else 2.0)
        total_qty = int(math.ceil(planned_raw / batch_size) * batch_size)

    total_qty = min(daily_cap, max(batch_size, total_qty))

    initial = max(batch_size, math.ceil(total_qty * 0.4 / batch_size) * batch_size)
    initial = min(total_qty, initial)
    remaining = total_qty - initial

    first_rem = (remaining // (2 * batch_size)) * batch_size
    batch_qtys = [first_rem, remaining - first_rem]
    production_batches = []

    for ready, b_qty in zip(("14:00", "17:00"), batch_qtys):
        if ready > last_ready:
            continue
        while b_qty > 0:
            n = min(b_qty, max_batch)
            b_qty -= n
            ready_h, ready_m = map(int, ready.split(":"))
            ready_minutes = ready_h * 60 + ready_m
            order_minutes = ready_minutes - lead_min
            order_time = "06:00" if order_minutes < 0 else f"{order_minutes // 60:02d}:{order_minutes % 60:02d}"
            production_batches.append({
                "qty": n,
                "order_time": order_time,
                "ready_time": ready
            })

    return {
        "initial_qty": initial,
        "production_batches": production_batches,
        "policy_status": "SMARTFRESH_V4_PROFIT_MAXIMIZING"
    }

# --- Markdown (M1) ---
def markdown(observed_state, as_of):
    _load_artifacts()
    features = observed_state.get("model_features", {})
    price_ctx = observed_state.get("price_context", {})

    sku = features.get("sku_code", "")
    inv = float(_clean_num(features.get("inventory_at_decision"), 0.0))
    if inv <= 0: return 0

    cur_discount = float(_clean_num(price_ctx.get("current_discount_pct"), 0.0))
    list_price = float(_clean_num(price_ctx.get("list_price_vnd"), 25000.0))
    cur_date = as_of[:10]
    cur_time = as_of[11:16] if len(as_of) >= 16 else str(features.get("time", "19:30"))

    tracker_key = (cur_date, sku)
    daily_count = _DAILY_CHANGE_TRACKER.get(tracker_key, 0)
    if daily_count >= 2: return 0

    baseline_floor = features.get("baseline_announced_2100_pct")
    floor_pct = float(baseline_floor) if baseline_floor not in (None, "") else 0.0

    # Rule C Cooldown Guard:
    if cur_time == "21:00" and floor_pct > 0:
        return 0

    max_allowed_d = 40 if cur_time < "20:30" else 50
    menu = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    candidates = [d for d in menu if d >= cur_discount and d >= floor_pct and d <= max_allowed_d]
    if len(candidates) <= 1: return 0

    spec = _OPERATIONAL_LOOKUP.get(sku, {}) if _OPERATIONAL_LOOKUP else {}
    sticker_cost = float(spec.get("markdown_action_cost_vnd_assumed", 350))
    disp_cost = float(spec.get("unit_disposal_cost_vnd_assumed", 150))

    if _M1_BUNDLE is None: return 0
    model = _M1_BUNDLE["model"]
    preprocessor = _M1_BUNDLE["preprocessor"]
    
    vec_hold = preprocessor.transform_row(features, cur_discount, sku, spec)
    sales_hold_30m = min(inv, max(0.0, float(model.predict([vec_hold])[0])))

    mins_left = float(_clean_num(features.get("minutes_to_close"), 60.0))
    pace = float(_clean_num(features.get("sales_pace_units_per_minute"), 0.0))
    rem_mins_after_30 = max(0.0, mins_left - 30.0)
    
    # Nới lỏng suy giảm tốc độ mua (để P_sellout thấp hơn một chút, dễ kích hoạt M1)
    decay_factor = 0.90 if cur_time < "20:30" else 0.70
    
    continuation_sales = max(sales_hold_30m * (rem_mins_after_30 / 30.0) * decay_factor, pace * rem_mins_after_30 * decay_factor)
    expected_eod_sales_hold = min(inv, sales_hold_30m + continuation_sales)
    expected_eod_waste_hold = max(0.0, inv - expected_eod_sales_hold)
    sellout_prob_hold = expected_eod_sales_hold / max(1.0, inv)

    # NỚI LỎNG CỔNG CHẶN TRONG V4: Xác suất tự bán hết >= 88% mới chặn!
    if cur_time < "21:00":
        if sellout_prob_hold >= 0.88 or expected_eod_waste_hold < 1.0:
            return 0

    best_action = 0
    best_net_gain = 0.0
    cur_price = list_price * (1.0 - cur_discount / 100.0)
    
    # Hạ cực thấp tiền phạt rủi ro M1
    q25_penalty = 0.05 
    min_net_gain = 500.0 

    for cand_d in candidates:
        if cand_d == cur_discount: continue

        vec_cand = preprocessor.transform_row(features, cand_d, sku, spec)
        pred_sales_30m = max(0.0, float(model.predict([vec_cand])[0]))
        conservative_sales_30m = min(inv, max(0.0, pred_sales_30m - q25_penalty))

        delta_sales_30m = max(0.0, conservative_sales_30m - sales_hold_30m)
        if delta_sales_30m <= 0.1: continue

        saved_waste_units = min(delta_sales_30m, expected_eod_waste_hold)
        cannibalized_units = max(0.0, delta_sales_30m - saved_waste_units)

        cand_price = list_price * (1.0 - cand_d / 100.0)
        price_drop = cur_price - cand_price

        net_gain = (saved_waste_units * (cand_price + disp_cost) 
                    - (sales_hold_30m + cannibalized_units) * price_drop 
                    - sticker_cost)

        if net_gain > max(min_net_gain, best_net_gain):
            best_net_gain = net_gain
            best_action = cand_d

    if best_action > cur_discount:
        _DAILY_CHANGE_TRACKER[tracker_key] = daily_count + 1
        return best_action

    return 0
"""Explicit synthetic volume contract; prices, percentages and time never scale."""
from datetime import date
import hashlib

SCALE = 10
VERSION = 'AEON_GENERATED_POS_V3'
LEGACY_GENERATED_VERSION = 'AEON_GENERATED_POS_V2'
LEGACY_VOLUME_VERSION = 'AEON_VOLUME_X10_V1'
LEGACY_MODEL_VERSION = 'SMARTFRESH_V4_RETRAIN_X10_V1'
MODEL_VERSION = 'SMARTFRESH_V4_JOINT_V2'
# Relative hourly arrival intensities, 08:00 through 21:59 (user assumptions).
PROFILES = {
    'weekday': [2, 2, 3, 4, 5, 4, 4, 4, 5, 13, 15, 15, 14, 10],
    'day_off': [5, 5, 6, 6, 6, 6, 6, 6, 6, 9, 10, 11, 10, 8],
}
QUANTITY_FIELDS = {
    'prepared_qty', 'sold_qty', 'waste_qty', 'sold_to_2130', 'discounted_qty',
    'sold_calendar_lag1', 'sold_calendar_lag7', 'sold_last7_observed_mean',
    'prepared_last_observed', 'sold_calendar_lag1_fallback_observed_sales',
    'sold_calendar_lag7_fallback_observed_sales', 'operational_daily_capacity_units',
    'daily_capacity_units_assumed', 'max_batch_units_assumed',
    'shelf_capacity_units_assumed', 'shelf_refill_threshold_units_assumed',
    'baseline_buffer_units_assumed', 'inventory_at_decision', 'sold_last_30min',
    'sold_last_60min', 'shelf_inventory', 'backroom_inventory',
    'sales_pace_units_per_minute', 'pace_acceleration',
    'projected_surplus_at_current_pace', 'observed_buyers_last30',
}
TOTAL_MONEY_FIELDS = {
    'revenue_vnd', 'production_cost_vnd_assumed', 'disposal_cost_vnd_assumed',
    'markdown_operations_cost_vnd_assumed', 'contribution_before_overhead_vnd',
}


def scaled(row):
    return {k: v * SCALE if k in QUANTITY_FIELDS | TOTAL_MONEY_FIELDS and isinstance(v, (int, float)) else v
            for k, v in row.items()}


def profile_name(day, holiday=False):
    return 'day_off' if holiday or date.fromisoformat(day).weekday() >= 5 else 'weekday'


def uniform(key):
    return int(hashlib.sha256(key.encode()).hexdigest()[:13], 16) / 16**13


def arrival_second(day, customer_id, replica, seed, holiday=False, promo=False,version=VERSION):
    # Shared basket ID => same visit time for its products. Each replica is a
    # distinct synthetic customer, not a single purchase with quantity=10.
    weights = PROFILES[profile_name(day, holiday)]
    # Promotional opportunities remain in the pricing window, 19:30–22:00.
    bins = [(h * 3600, 3600, w) for h, w in zip(range(8, 22), weights)]
    if promo:
        bins = [(70200, 1800, weights[11] / 2), (72000, 3600, weights[12]), (75600, 3600, weights[13])]
    key = f'{version}|{day}|{customer_id}|{replica}|{seed}|{promo}'
    point = uniform(key + '|hour') * sum(b[2] for b in bins)
    for start, duration, weight in bins:
        if point < weight:
            return start + min(duration - 1, int(uniform(key + '|second') * duration))
        point -= weight
    return 79199

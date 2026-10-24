"""Economic release guard. Logged-action forecasts are not causal uplift evidence."""
import math

POLICY='BENEFIT_REQUIRED_HOLD_WITHOUT_UPLIFT_V1'


def guard(row):
    """No validated price-response source exists in V606: do not invent one."""
    current=round(row['price']*(1-row['previous']/100))
    candidate=row['new_price']
    p=row.get('pricing_policy',{})
    remaining=p.get('projected_remaining_sales_at_current_pace',
        max(row['sales30']/30,row['sales60']/60)*max(0,1320-row['minute']))
    units=min(row['stock'],max(0,remaining))
    saving=units*max(0,current-candidate)
    required=math.ceil(saving/candidate) if candidate>0 and candidate<current else None
    gate=dict(id=POLICY,status='HOLD_NO_VERIFIED_INCREMENTAL_BENEFIT' if candidate<current else 'HOLD_NO_PRICE_CHANGE_NEEDED',
        current_cash_price=current,candidate_cash_price=candidate if candidate<current else None,
        expected_units_at_current_price=units,discount_cost_on_same_units=saving,
        minimum_extra_units_to_break_even=required,verified_extra_units=None,verified_net_benefit=None,
        cost_basis='ALL_PREPARED_COST_ALREADY_INCURRED; NOT_DEDUCTED_AGAIN',
        price_response_status='NO_CAUSAL_PRICE_RESPONSE_EVIDENCE; SIMULATOR_HAS_NO_PRICE_UPLIFT',
        source='GLOBAL_OPERATIONAL_GUARD; LOGGED_ACTION_FORECAST_DOES_NOT_VERIFY_BENEFIT')
    return {**row,'new_price':current,'discount':row['previous'],
        'reason':'HOLD_NO_VERIFIED_INCREMENTAL_BENEFIT' if candidate<current else row['reason'],
        'economic_gate':gate}

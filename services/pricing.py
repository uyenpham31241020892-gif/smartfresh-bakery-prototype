"""Observed-state markdown from 19:30; no assumed causal price response."""
import math

PRICING_POLICY='OBSERVED_SURPLUS_FROM_1930_V1'


def markdown(spec,minute,stock,prepared,previous,sales30,sales60,model_next30,model_action):
    if not all(math.isfinite(v) and v>=0 for v in (stock,prepared,previous,sales30,sales60,model_next30)):
        raise ValueError('Invalid observed pricing state')
    price=int(spec['unit_price_vnd_reference']);current=round(price*(1-previous/100))
    observed_pace=max(sales30/30,sales60/60)
    pace=max(observed_pace,max(0,float(model_next30))/30)
    left=max(0,1320-minute);until2130=max(0,1290-minute)
    remaining=pace*left;before2130=pace*until2130
    reserve=4;protection=before2130+1.64*math.sqrt(before2130)+reserve
    excess=stock-remaining-reserve;threshold=max(4,prepared*.08)
    cash=current;reason='HOLD_NO_MATERIAL_SURPLUS'
    if minute<1170:reason='HOLD_BEFORE_1930'
    elif not stock:reason='HOLD_SOLD_OUT'
    elif minute<1290 and stock<=protection:reason='HOLD_PROTECT_STOCK_TO_2130'
    elif excess>threshold:
        # Severity changes with current surplus and remaining time, not a fixed 21h switch.
        severity=.7*max(0,excess)/max(stock,1)+.3*min(1,max(0,(minute-1170)/150))
        tier=min(20,max(5,5*math.ceil(4*severity)))
        reference=spec.get('markdown_price_vnd_reference')
        minimum=int(reference) if reference else round(price*.8)
        cash=min(current,max(minimum,round(price*(1-tier/100))))
        reason='MARKDOWN_OBSERVED_SURPLUS' if cash<current else 'HOLD_CURRENT_PRICE_ALREADY_SUFFICIENT'
    discount=round(100*(price-cash)/price,10)
    return dict(new_price=cash,discount=discount,reason=reason,pricing_policy=dict(
        id=PRICING_POLICY,earliest_minute=1170,observed_units_per_hour=observed_pace*60,
        model_next30_under_logged_action=max(0,float(model_next30)),model_logged_action=model_action,
        projected_remaining_sales_at_current_pace=remaining,projected_closing_stock_at_current_pace=max(0,stock-remaining),
        surplus_after_reserve=excess,material_surplus_threshold=threshold,
        stock_protection_to_2130=protection,service_reserve=reserve,
        price_effect='NOT_ESTIMATED; NO_CUSTOMER_UPLIFT_ASSUMED',
        origin='FROZEN_M1_FORECAST_PLUS_DECLARED_OBSERVED_SURPLUS_RULE',
        projection='PACE_EXTRAPOLATION_NOT_SERVICE_GUARANTEE'))

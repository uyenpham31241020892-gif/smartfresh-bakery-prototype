"""Late-first clearance with a whole-day concession budget, not mandatory markdown."""
import math
from .clearance import SCENARIO,ELASTICITY

POLICY='LATE_FIRST_REVENUE_BUDGET_CLEARANCE_V8'


def recommend(row,prepared,remaining,to2130,*,scenario=None,history=None):
 h=history or {};minute=row['minute'];stock=row['stock'];price=row['price'];previous=row['previous']
 if not all(math.isfinite(v) and v>=0 for v in [minute,stock,price,previous,prepared,remaining,to2130,row['sales30'],row['sales60']]) or price<=0 or stock>prepared or previous>50:raise ValueError('Invalid pricing state')
 current=round(price*(1-previous/100));pace=max(row['sales30']/30,row['sales60']/60)
 historical=h.get('own_remaining_projection');base=max(remaining,pace*max(0,1320-minute),historical or 0)
 service=0 if minute>=1290 else max(to2130,pace*(1290-minute),base*(1290-minute)/max(1,1320-minute))
 projected=max(0,stock-base);sold=h.get('sold_today',max(0,prepared-stock))
 past=h.get('past_discount_value',0);reference=(sold+min(stock,base))*price
 # Budget covers realized price concessions PLUS future absolute concessions.
 budget_rate=.01 if minute<1260 else .02 if minute<1290 else .025
 budget=reference*budget_rate
 slow_reference=h.get('own_sales60_reference')
 slowing=(slow_reference is not None and row['sales60']<.75*slow_reference) or row['sales30']*2<.7*row['sales60'] or row['sales60']==0
 exceptional=projected>=max(12,.25*prepared) and projected/max(stock,1)>=.6 and slowing
 severe=projected>=max(6,.08*prepared)
 cap=10 if minute<1290 or not severe else 20
 policy=dict(id=POLICY,earliest_minute=1170,preferred_minute=1260,trained_remaining_logged_sales=remaining,
  trained_sales_to_2130=to2130,projected_remaining_sales_at_current_pace=base,projected_closing_stock_at_current_pace=projected,
  material_surplus_threshold=max(4,.05*prepared),early_exception=exceptional,slowing_observed=slowing,
  stock_protection_to_2130=service+1.64*math.sqrt(service)+4,history=h,
  price_effect='ASSUMED_LINEAR_RESPONSE_NOT_LEARNED',assumed_response_coefficient=ELASTICITY,
  daily_concession_budget=budget,daily_budget_rate=budget_rate,past_discount_value=past,
  discount_semantics='TOTAL_PERCENT_OF_LIST_PRICE_NOT_COMPOUNDED',model_fit_until='2022-04-30',validation_through='2022-06-30')
 gate=dict(id=POLICY,scenario=scenario,current_cash_price=current,verified_extra_units=None,verified_net_benefit=None,
  price_response_status='ASSUMED_NOT_CAUSALLY_VERIFIED',cost_basis='PREPARATION_ALREADY_INCURRED_NOT_DEDUCTED_TWICE')
 reason='HOLD_NO_MATERIAL_SURPLUS';candidates=[];chosen=None
 if minute<1170:reason='HOLD_BEFORE_1930'
 elif not stock:reason='HOLD_SOLD_OUT'
 elif scenario!=SCENARIO:reason='HOLD_NO_DECLARED_PRICE_RESPONSE_SCENARIO'
 elif minute<1260 and not exceptional:reason='HOLD_PREFER_AFTER_2100'
 elif projected<=max(4,.05*prepared):pass
 elif base<=0:reason='HOLD_NO_OBSERVED_DEMAND_FOR_RESPONSE'
 else:
  for tier in [10,20]:
   if not previous<tier<=cap:continue
   cash=round(price*(1-tier/100));units=min(stock,base)
   ratio=(1+ELASTICITY*tier/100)/(1+ELASTICITY*previous/100)
   expected=min(stock,base*ratio);extra=max(0,expected-units)
   benefit=round(expected*cash-units*current,6);loss=units*(current-cash)
   service_required=service*ratio+1.64*math.sqrt(service*ratio)+4
   protected=minute>=1290 or stock>=service_required
   exposure=past+units*(price-cash)
   eligible=protected and exposure<=budget and extra>=1 and benefit>=0 and cash>=price*.45
   candidates.append(dict(discount=tier,cash=cash,assumed_extra_units=extra,assumed_net_revenue_change=benefit,
    zero_response_revenue_change=-loss,minimum_extra_units_to_break_even=math.ceil(loss/cash),
    service_protected=protected,stock_required_to_2130=service_required,total_concession_exposure=exposure,
    daily_concession_budget=budget,eligible=eligible))
  valid=[c for c in candidates if c['eligible']]
  if valid:
   # Default to the smaller cut when its modeled benefit is within 5% of the best.
   best=max(c['assumed_net_revenue_change'] for c in valid)
   chosen=min([c for c in valid if c['assumed_net_revenue_change']>=.95*best],key=lambda c:c['discount'])
   reason='MARKDOWN_EXCEPTIONAL_EARLY_SURPLUS' if minute<1260 else 'MARKDOWN_LATE_BUDGETED_SURPLUS'
   gate.update(chosen);gate.update(status='SIMULATION_ASSUMED_CLEARANCE_BENEFIT',evidence_id=POLICY,manager_review_required=True,candidate_cash_price=chosen['cash'])
  else:reason='HOLD_CONCESSION_BUDGET_OR_SERVICE_RISK'
 if not chosen:gate['status']=reason
 return {**row,'new_price':chosen['cash'] if chosen else current,'discount':chosen['discount'] if chosen else previous,
  'reason':reason,'pricing_policy':policy,'economic_gate':gate,'candidates':candidates}

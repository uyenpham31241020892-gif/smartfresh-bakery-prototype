"""Learned sales-risk forecast plus explicitly assumed price sensitivity.

The discount optimizer is a declared scenario policy, not causal learning.
Existing days retain their frozen market; only new v7 simulation days use it.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import joblib
import numpy as np
import xgboost as xgb

DIRECTORY=Path(__file__).resolve().parents[1]/'v606/V606_M1_remaining_v7'
POLICY='TRAINED_REMAINING_SALES_SCENARIO_CLEARANCE_V7'
SCENARIO='V606_busy4-price-sensitivity-assumed-v7'
ELASTICITY=2.0  # Linear incremental purchases = organic purchases * E * discount fraction.


@lru_cache(maxsize=1)
def artifacts():
    report=json.loads((DIRECTORY/'training_report.json').read_text())
    for name,digest in report['artifact_hashes'].items():
        if hashlib.sha256((DIRECTORY/name).read_bytes()).hexdigest()!=digest:raise ValueError('M1 v7 artifact changed')
    models={}
    for horizon in ['close','to2130']:
        m=xgb.Booster();m.load_model(DIRECTORY/(horizon+'.json'));models[horizon]=m
    return joblib.load(DIRECTORY/'preprocessor.joblib'),models,report


def predict(frame,scale):
    pre,models,report=artifacts()
    if list(frame.columns)!=pre['columns']:raise ValueError('M1 remaining-sales feature contract mismatch')
    dm=xgb.DMatrix(pre['preprocessor'].transform(frame))
    return {name:max(0,float(m.predict(dm)[0]))*scale for name,m in models.items()}


def recommend(row,prepared,remaining,to2130,*,scenario=None):
    """Never force clearance when no surplus, no credible sales, or service at risk."""
    price=row['price'];previous=row['previous'];minute=row['minute'];stock=row['stock']
    if not all(math.isfinite(v) and v>=0 for v in [price,previous,minute,stock,prepared,remaining,to2130,row['sales30'],row['sales60']]) or price<=0 or previous>50 or stock>prepared:
        raise ValueError('Invalid clearance decision state')
    current=round(price*(1-previous/100));left=max(0,1320-minute)
    # Both learned logged-action forecasts and current observed pace are conservative inputs.
    pace=max(row['sales30']/30,row['sales60']/60)
    base=max(remaining,pace*left)
    service=0 if minute>=1290 else max(to2130,pace*max(0,1290-minute))
    reserve=4;threshold=max(4,.05*prepared)
    projected=max(0,stock-base)
    service_buffer=1.64*math.sqrt(service)+reserve
    policy=dict(id=POLICY,trained_remaining_logged_sales=remaining,trained_sales_to_2130=to2130,
        projected_remaining_sales_at_current_pace=base,projected_closing_stock_at_current_pace=projected,
        material_surplus_threshold=threshold,stock_protection_to_2130=service+service_buffer,
        service_uncertainty='1.64*sqrt(assumed_sales_to_2130)+4; HEURISTIC_NOT_CALIBRATED_GUARANTEE',
        price_effect='ASSUMED_LINEAR_RESPONSE_NOT_LEARNED',assumed_response_coefficient=ELASTICITY,
        model_fit_until='2022-04-30',validation_through='2022-06-30',earliest_minute=1170)
    gate=dict(id=POLICY,status='HOLD_NO_MATERIAL_SURPLUS',current_cash_price=current,
        verified_extra_units=None,verified_net_benefit=None,price_response_status='ASSUMED_NOT_CAUSALLY_VERIFIED',
        scenario=scenario,cost_basis='ALL_PREPARED_COST_ALREADY_INCURRED; NOT_DEDUCTED_AGAIN')
    candidates=[];chosen=None;reason='HOLD_NO_MATERIAL_SURPLUS'
    if minute<1170:reason='HOLD_BEFORE_1930'
    elif not stock:reason='HOLD_SOLD_OUT'
    elif scenario!=SCENARIO:reason='HOLD_NO_DECLARED_PRICE_RESPONSE_SCENARIO'
    elif projected<=threshold:pass
    elif minute<1290 and stock<=service+service_buffer:reason='HOLD_PROTECT_STOCK_TO_2130'
    elif base<=0:reason='HOLD_NO_OBSERVED_DEMAND_FOR_RESPONSE'
    else:
        # Meaningful bands, chosen afresh; avoid repeated 5% steps. Never raise applied price.
        cap=20 if minute<1230 else 30 if minute<1290 else 40
        units=min(stock,base);hold_revenue=current*units
        for tier in [10,20,30,40]:
            if not previous<tier<=cap:continue
            ratio=(1+ELASTICITY*tier/100)/(1+ELASTICITY*previous/100)
            cash=round(price*(1-tier/100));expected=min(stock,base*ratio)
            extra=max(0,expected-units);loss=units*(current-cash);benefit=round(expected*cash-hold_revenue,6)
            required_service=service*ratio+1.64*math.sqrt(service*ratio)+reserve
            protected=minute>=1290 or stock>=required_service
            allowed=protected and extra>=1 and (benefit>=max(price,hold_revenue*.02) or
                (minute>=1260 and benefit>=0 and extra>=2))
            candidates.append(dict(discount=tier,cash=cash,assumed_extra_units=extra,
                assumed_net_revenue_change=benefit,zero_response_revenue_change=-loss,
                minimum_extra_units_to_break_even=math.ceil(loss/cash),service_protected=protected,
                stock_required_to_2130=required_service,eligible=allowed))
        eligible=[c for c in candidates if c['eligible']]
        if eligible:
            chosen=max(eligible,key=lambda c:(round(c['assumed_net_revenue_change'],2),c['assumed_extra_units'],-c['discount']))
            reason='MARKDOWN_TRAINED_SURPLUS_SCENARIO';gate.update(chosen)
            gate.update(status='SIMULATION_ASSUMED_CLEARANCE_BENEFIT',evidence_id=POLICY,
                candidate_cash_price=chosen['cash'],manager_review_required=True)
        else:reason='HOLD_NO_BENEFICIAL_SERVICE_SAFE_CANDIDATE'
    if not chosen:gate['status']=reason
    return {**row,'new_price':chosen['cash'] if chosen else current,'discount':chosen['discount'] if chosen else previous,
            'reason':reason,'pricing_policy':policy,'economic_gate':gate,'candidates':candidates}

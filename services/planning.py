"""Adaptive as-of supply policy. Customer events and hidden demand are never inputs."""
import math
import numpy as np

POLICY_VERSION='busy4-observed-adaptive-service2130-v4'


def adaptive_supply(sku,raw_forecast,features,history,observations,spec,scale=4):
    day=features['date']
    if any(r['date']>=day or r['sku_code']!=sku for r in history):
        raise ValueError('Planning history must be past and own SKU.')
    local=sorted([r for r in observations if r['sku_code']==sku and r['date']<day],key=lambda r:r['date'])[-7:]
    if any(r['date']>=day for r in observations):raise ValueError('Future planning observation rejected')
    # Seed rows are on the original training scale. Local observations are native POS units.
    local_dates={o['date'] for o in observations if o['sku_code']==sku}
    seed=[r for r in history if r['date'] not in local_dates][-7:]
    seed_mean=float(np.mean([r['sold_qty'] for r in seed])) if seed else float(features['sold_last7_observed_mean'])
    modeled=max(0,float(raw_forecast))*scale
    model_allowed=not bool(features['ood_flag'])
    cold_mean=(modeled+seed_mean*scale)/2 if model_allowed else seed_mean*scale
    # Fixed prior strength, not a clipping band. Recent completed sales can change the plan.
    prior_weight=3.;weights=[1+(i+1)/len(local) for i in range(len(local))]
    local_values=[float(r['sold_qty']) for r in local]
    weight=sum(weights)
    expected=(prior_weight*cold_mean+sum(w*v for w,v in zip(weights,local_values)))/(prior_weight+weight)
    censored=[r for r in local if r['censored_demand_flag']]
    # Stockout sales are lower bounds. Never interpret them as the full latent demand.
    if local and local[-1]['censored_demand_flag']:
        expected=max(expected,float(local[-1]['prepared_qty'])*1.05)
    sigma=max(math.sqrt(max(expected,1)),float(np.std(local_values,ddof=1)) if len(local_values)>1 else 0.)
    buffer=1.64*sigma;reserve=4
    target=expected+buffer+reserve
    batch=int(spec['batch_size_units_assumed']);cap=int(spec['daily_capacity_units_assumed'])*scale
    required=max(batch,batch*math.ceil(target/batch));qty=min(cap//batch*batch,required)
    ratios=[r['sold_to_2130']/r['sold_qty'] for r in local if r['sold_qty'] and not r['censored_demand_flag'] and r.get('sold_to_2130') is not None]
    share=float(np.mean(ratios)) if ratios else .925
    to2130=expected*share
    return dict(quantity=qty,raw_forecast=float(raw_forecast),scenario_forecast=modeled,
        expected_requests_assumed=expected,model_adjustment=expected-seed_mean*scale,
        uncertainty_buffer=buffer,service_reserve=reserve,required=required,capacity=cap,
        capacity_feasible=required<=cap,service_until='21:30',policy=POLICY_VERSION,
        service_status='PLANNING_GOAL_NOT_GUARANTEE',capacity_status='ASSUMED_BUSY_SCENARIO_CAPACITY_NOT_PHYSICAL_SURVEY',
        observation_days=len(local),recent_sold_mean=float(np.mean(local_values)) if local_values else None,
        recent_censored_days=len(censored),model_used=model_allowed,
        model_weight=(prior_weight*.5/(prior_weight+weight)) if model_allowed else 0,
        fallback_reason=features.get('ood_reasons') if not model_allowed else None,
        demand_scale=scale,model_history_normalization='BUSY_POS_DIVIDED_BY_DECLARED_SCALE; SEED_ALREADY_TRAIN_SCALE',
        expected_sold_to_2130=to2130,expected_stock_at_2130=max(0,qty-to2130),
        stock_at_2130_lower_scenario=qty-to2130-1.64*sigma*math.sqrt(share),
        share_sold_by_2130=share,share_source='OWN_COMPLETED_POS' if ratios else 'ASSUMED_75PCT_EVENING_UNIFORM',
        projection_status='ASSUMED_POISSON_PLUS_OBSERVED_VARIABILITY_NOT_VALIDATED_COVERAGE',
        weather_status='PRIOR_DAY_RETROSPECTIVE_ONLY' if features.get('prior_day_rain_mm') is not None and features.get('prior_day_temp_c') is not None else 'MISSING_MODEL_FALLBACK',
        history_through=history[-1]['date'],target_day=day)

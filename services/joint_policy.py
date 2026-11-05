"""Joint operating policy. Decisions use observed state and fitted models only."""
from datetime import date, timedelta
import math
from scipy.stats import poisson
from .seasonal_reference import anchor as seasonal_anchor


POLICY = dict(version='JOINT_V4_V2', sellout_hold_threshold=.88,
    availability_2130_target=.80, min_net_gain_vnd=500., max_changes=3,
    cooldown_minutes=30, step_pct=10, early_caps={'19:30':20,'20:00':25,'20:30':35,'21:00':40,'21:30':50})


def depromo_features(features, history):
    """Remove estimated *incremental* promo units, never all discounted sales."""
    f=dict(features)
    if f.get('depromo_applied'):return f
    sku,day=f['sku_code'],f['date']
    rows=sorted((r for r in history if r.get('sku_code',sku)==sku and r['date']<day),key=lambda r:r['date'])
    if not rows:return f
    # A stockout makes served sales only a lower bound. Subtracting estimated
    # promotion units from that bound would teach the next plan that an
    # inventory-limited day had even less underlying demand.
    corrected={}
    for r in rows:
        sold=float(r['sold_qty'])
        incremental=max(0.,float(r.get('incremental_promo_qty_estimated',0)))
        corrected[r['date']]=sold if r.get('stockout') or r.get('censored_demand_flag') else max(0.,sold-min(sold,incremental))
    recent=rows[-7:]
    removed=sum(float(r['sold_qty'])-corrected[r['date']] for r in recent)
    raw={k:f.get(k) for k in ('sold_calendar_lag1','sold_calendar_lag7','sold_last7_observed_mean')}
    for lag in (1,7):
        key=f'sold_calendar_lag{lag}';past=str(date.fromisoformat(day)-timedelta(days=lag))
        if past in corrected:
            f[key]=corrected[past];f[key+'_fallback_observed_sales']=corrected[past]
        elif f.get(key+'_missing'):
            f[key+'_fallback_observed_sales']=sum(corrected[r['date']] for r in recent)/len(recent)
    f['sold_last7_observed_mean']=sum(corrected[r['date']] for r in recent)/len(recent)
    f.update(depromo_applied=True,depromo_raw_features=raw,depromo_removed_last7=removed,
             depromo_method='M1_COUNTERFACTUAL_ESTIMATE_NOT_ALL_DISCOUNTED_UNITS')
    return f


def quantiles(bundle,features,sku,spec):
    vector=bundle['preprocessor'].transform_row(features,sku,spec)
    values={q:max(0.,float(bundle[key].predict([vector])[0])) for q,key in
            [(45,'model_q45'),(50,'model'),(75,'model_q75'),(90,'model_q90')]}
    if not all(math.isfinite(v) for v in values.values()):raise ValueError('M2 prediction is not finite')
    # Rearrangement repairs quantile crossings without fabricating a percentage uplift.
    return dict(zip(sorted(values),sorted(values.values())))


def baseline_guard(day,sku,history,day_off,forecast):
    """Bound the forecast using weekday-specific history and censored-aware updates."""
    def same_class(row):
        weekday=date.fromisoformat(row['date']).weekday()
        target_weekday=date.fromisoformat(day).weekday()
        # Saturday and Sunday have different POS patterns. Only a weekday
        # public holiday borrows the broader weekend reference group.
        return weekday>=5 if day_off and target_weekday<5 else weekday==target_weekday
    test_start='2022-07-01' if day>='2022-07-01' else '2022-05-01'
    baseline=[r for r in history if r.get('sku_code')==sku and '2022-01-02'<=r['date']<test_start]
    if not baseline:return forecast,dict(status='NO_BASELINE_ANCHOR')
    anchor=seasonal_anchor(day,baseline,test_start,holiday=day_off)
    recent=sorted((r for r in history if r.get('sku_code')==sku and test_start<=r['date']<day and same_class(r)),key=lambda r:r['date'])[-7:]
    eligible=[r for r in recent if not (r.get('stockout') or r.get('censored_demand_flag'))]
    ratios=[max(0.,float(r['sold_qty'])-float(r.get('incremental_promo_qty_estimated',0)))/anchor for r in eligible]
    factor=max(.8,min(1.2,1+.3*(sum(ratios)/len(ratios)-1))) if ratios else 1.
    censored_recent=any(r.get('stockout') or r.get('censored_demand_flag') for r in recent)
    floor_multiplier=.98 if censored_recent else .90
    lower=anchor*factor*floor_multiplier
    upper=anchor*factor*(1.12 if day_off else 1.10)
    # A small online residual model uses only completed, earlier sessions.
    # Stockouts contribute a lower-bound signal, never a negative demand label.
    online=[]
    for row in sorted((r for r in history if r.get('sku_code')==sku and test_start<=r['date']<day
                       and r.get('selected_forecast') and r.get('source_session_id')),key=lambda r:r['date'])[-14:]:
        prior=float(row['selected_forecast'])
        censored=bool(row.get('stockout') or row.get('censored_demand_flag'))
        if censored:
            residual=max(.03,(float(row.get('prepared_qty',0))-prior)/max(prior,1.))
        else:
            organic=max(0.,float(row['sold_qty'])-float(row.get('incremental_promo_qty_estimated',0)))
            residual=(organic-prior)/max(prior,1.)
        age=(date.fromisoformat(day)-date.fromisoformat(row['date'])).days
        weight=.82**(age-1)*(.5 if not same_class(row) else 1.)
        online.append((max(-.25,min(.25,residual)),weight))
    online_residual=sum(r*w for r,w in online)/sum(w for _,w in online) if online else 0.
    online_factor=max(.9,min(1.1,1+.35*online_residual))
    bounded=max(lower,min(upper,forecast*online_factor))
    return bounded,dict(status='CENSOR_AWARE_BASELINE_GUARD',anchor=anchor,uncensored_updates=len(ratios),
                        censored_recent=censored_recent,adjustment=factor,lower=lower,upper=upper,
                        online_updates=len(online),online_residual=online_residual,online_factor=online_factor,
                        original_forecast=forecast,adjusted_forecast=bounded)


def prepare(features,history,bundle,spec):
    f=depromo_features(features,history);sku=f['sku_code'];q=quantiles(bundle,f,sku,spec)
    price=float(spec['unit_price_vnd_reference']);cost=float(f.get('known_unit_production_cost_vnd') or spec['unit_production_cost_vnd_assumed'])
    disposal=float(spec['unit_disposal_cost_vnd_assumed'])
    cu=max(0.,price-cost);co=cost+disposal;critical=cu/max(cu+co,1.)
    busy=int(f['weekday_iso'])>=5 or bool(f.get('is_public_holiday'))
    lower,upper=(.75,.90) if busy else (.45,.50)
    # Day bands are the explicit business policy; margins select within each band.
    chosen=lower+(upper-lower)*critical
    if not busy and sku in ('TP-CP-001','TP-RV-001'):chosen=.45
    if int(f['weekday_iso']) in (2,3) and not busy:chosen=min(chosen,.475)
    lo,hi=(75,90) if busy else (45,50)
    forecast=q[lo]+(q[hi]-q[lo])*(chosen*100-lo)/(hi-lo)
    day_off=int(f['weekday_iso'])>=6 or bool(f.get('is_public_holiday'))
    forecast,calibration=baseline_guard(f['date'],sku,history,day_off,forecast)
    batch=int(spec['batch_size_units_assumed']);cap=int(f.get('operational_daily_capacity_units') or spec['daily_capacity_units_assumed'])
    # The morning approval is a ceiling; later batches are ordered from
    # observed pace. Keep headroom for unexpectedly busy days without baking
    # it all at 06:00.
    ceiling=max(forecast,calibration.get('anchor',forecast)*1.20)
    total=min(cap//batch*batch,max(batch,math.ceil(ceiling/batch)*batch))
    initial=min(total,max(batch,math.ceil(total*.4/batch)*batch));remaining=total-initial
    first=remaining//(2*batch)*batch;refills=[]
    max_batch=int(spec['max_batch_units_assumed'])//batch*batch
    if max_batch<batch:raise ValueError('Invalid production batch capacity')
    lead=int(f.get('operational_lead_minutes') or spec['production_lead_time_minutes_assumed'])
    for ready,quantity in [('14:00',first),('17:00',remaining-first)]:
        if ready>spec['last_production_ready_time_assumed']:raise ValueError('Refill exceeds last ready time')
        minute=int(ready[:2])*60+int(ready[3:]);order=max(360,minute-lead)
        while quantity:
            amount=min(quantity,max_batch);quantity-=amount
            refills.append(dict(qty=amount,ready_time=ready,order_time=f'{order//60:02}:{order%60:02}',conditional=True))
    return dict(initial_qty=initial,production_batches=refills,policy_status='JOINT_NEWSVENDOR',
        selected_quantile=chosen,critical_fractile=critical,underage_cost_vnd=cu,overage_cost_vnd=co,
        quantiles={str(k):v for k,v in q.items()},selected_forecast=forecast,
        depromo_removed_last7=f.get('depromo_removed_last7',0),calibration=calibration,model_features=f)


def predict30(bundle,f,tier,sku,spec):
    value=float(bundle['model'].predict([bundle['preprocessor'].transform_row(f,tier,sku,spec)])[0])
    if not math.isfinite(value):raise ValueError('M1 prediction is not finite')
    return max(0.,value)


def pricing(features,context,bundle,spec,config=None):
    cfg=POLICY|dict(config or {});f=dict(features);sku=f['sku_code']
    minute=1320-int(f['minutes_to_close']);stock=max(0.,float(f['inventory_at_decision']))
    previous=float(context.get('current_discount_pct',f['previous_discount_pct']))
    price=float(spec['unit_price_vnd_reference']);disposal=float(spec['unit_disposal_cost_vnd_assumed'])
    fee=float(context.get('markdown_cost',spec.get('markdown_action_cost_vnd_assumed',350)))
    tm=f'{minute//60:02}:{minute%60:02}'
    # A prior manager override may exceed the AI's gradual cap. HOLD must remain
    # valid, without proposing a price increase or blocking other SKU approvals.
    cap=max(previous,cfg['early_caps'].get(tm,50 if minute>=1290 else 40))
    rate=predict30(bundle,f,previous,sku,spec)
    natural_rate=predict30(bundle,f,0,sku,spec)
    # Forecast horizon uses only current state; each future checkpoint has its own
    # time feature. Recent *observed* history enters as a rate, not future events.
    history=f.get('history_rate_next30');history_n=int(f.get('history_days',0))
    weight=min(.25,history_n*.05) if history is not None else 0.
    def horizon(tier,end):
        total=0.;first=0.
        for at in range(minute,end,30):
            future=dict(f,time=f'{at//60:02}:{at%60:02}',minutes_to_close=1320-at)
            prediction=predict30(bundle,future,tier,sku,spec)
            if at==minute:first=prediction
            # History informs the baseline only; retain learned incremental response.
            if weight:
                baseline=predict30(bundle,future,previous,sku,spec)
                prediction=max(0.,prediction+weight*(float(history)-baseline))
            total+=prediction*min(30,end-at)/30
        return total,first
    hold_mean,_=horizon(previous,1320);before_mean,_=horizon(previous,1290)
    natural_mean,_=horizon(0,1320)
    # Explicit Poisson count assumption: sf(stock-1) = P(demand >= stock).
    # This is not the ratio expected_sales / inventory and is not a real-store calibration.
    sellout=float(poisson.sf(math.ceil(stock)-1,hold_mean)) if stock else 1.
    natural_sellout=float(poisson.sf(math.ceil(stock)-1,natural_mean)) if stock else 1.
    availability=float(poisson.cdf(math.ceil(stock)-1,before_mean)) if stock else 0.
    hold_sales=min(stock,hold_mean);waste=max(0.,stock-hold_sales)
    evidence=dict(action=0,reason='NO_POSITIVE_NET_GAIN',hold_next30=min(stock,rate),
        natural_next30=min(stock,natural_rate),hold_to_close=hold_sales,expected_waste_hold=waste,
        sellout_probability_hold=sellout,sellout_probability_list=natural_sellout,
        availability_probability_2130=availability,probability_method='POISSON_COUNT_ASSUMPTION_NOT_CALIBRATED_AEON',
        history_days=history_n,cap=cap,candidates=[],net_gain=0.,phase='clearance' if minute>=1290 else 'gradual')
    reason=None
    if not stock:reason='NO_STOCK'
    elif sellout>=cfg['sellout_hold_threshold']:reason='SELLOUT_GATE_88'
    elif minute<1290 and availability<cfg['availability_2130_target']:reason='PROTECT_STOCK_UNTIL_2130'
    elif int(context.get('daily_count',0))>=cfg['max_changes']:reason='MAX_APPLIED_CHANGES'
    elif minute<1290 and int(context.get('daily_count',0))>=cfg['max_changes']-1:reason='RESERVE_FINAL_CLEARANCE'
    elif minute-int(context.get('last_price_change_minute',-9999))<cfg['cooldown_minutes']:reason='COOLDOWN'
    step_cap=min(cap,previous+cfg['step_pct']) if minute<1290 else cap
    best=0.;best_action=0
    for tier in [0,10,15,20,25,30,35,40,45,50]:
        if tier<previous or tier>cap:continue
        mean,next30=horizon(tier,1320);early,_=horizon(tier,1290)
        candidate_sales=min(stock,mean);delta=max(0.,candidate_sales-hold_sales)
        saved=min(delta,waste);cannibalized=max(0.,delta-saved)
        candidate_price=price*(1-tier/100);drop=price*(tier-previous)/100
        gain=saved*(candidate_price+disposal)-(hold_sales+cannibalized)*drop-(fee if tier!=previous else 0.)
        service=float(poisson.cdf(math.ceil(stock)-1,early)) if stock else 0.
        eligible=tier>previous and tier<=step_cap and (minute>=1290 or service>=cfg['availability_2130_target'])
        evidence['candidates'].append(dict(discount=tier,expected_sales_next30=min(stock,next30),
            expected_sales_to_close=candidate_sales,expected_revenue=round(min(stock,next30)*candidate_price),
            rescued_units=saved,cannibalized_units=cannibalized,markdown_fee=fee if tier!=previous else 0.,
            cannibalization_cost=(hold_sales+cannibalized)*drop,net_gain=gain,
            availability_probability_2130=service,eligible=eligible))
        if eligible and gain>max(best,cfg['min_net_gain_vnd']):best,best_action=gain,tier
    if reason:evidence['reason']=reason
    elif best_action:evidence.update(action=best_action,reason='POSITIVE_INCREMENTAL_NET_GAIN',net_gain=best)
    return evidence

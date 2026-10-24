from datetime import date,timedelta
import math
CORE_SKUS={'TP-DN-003', 'TP-DN-001', 'TP-DN-002', 'TP-RV-001', 'TP-CP-001', 'TP-DN-004', 'TP-CR-001'}

def event_context(day):
 d=date.fromisoformat(day);offset=(d-date(d.year,2,1 if d.year==2022 else 22)).days
 official=('2022-01-31'<=day<='2022-02-04') or ('2023-01-20'<=day<='2023-01-26')
 run=('2022-01-18'<=day<='2022-01-30') or ('2023-01-07'<=day<='2023-01-19')
 post=('2022-02-05'<=day<='2022-02-14') or ('2023-01-27'<=day<='2023-02-05')
 if d.year not in (2022, 2023):raise ValueError('V6.03event calendar approved only for 2022 and 2023; provide a versioned calendar for another year')
 pub=official or day in {'2022-01-01','2022-04-10','2022-04-30','2022-05-01','2022-09-01','2022-09-02','2023-01-01','2023-01-02'}
 group='tet_official' if official else 'tet_run_up' if run else 'post_tet_assumed_window' if post else 'public_holiday' if pub else 'ordinary'
 return dict(event_stratum=group,is_tet_official_leave=int(official),is_post_tet_window_assumed=int(post),days_to_tet=-offset,is_summer_season_proxy=int(d.month in(6,7,8)),school_break_status='UNVERIFIED_USE_MONTH_PROXY_ONLY',local_event_status='NO_VERIFIED_EVENT_RECORD',local_event_flag_verified=None,calendar_year=d.year)

def enhance_morning(features,history):
 f=dict(features);day=f['date'];ec=event_context(day);f.update(ec);past=sorted([r for r in history if r['date']<day],key=lambda r:r['date']);recent=past[-7:]
 for lag in [1,7]:
  k=f'sold_calendar_lag{lag}';value=f.get(k);missing=value is None or (isinstance(value,float) and math.isnan(value));f[k+'_missing']=int(missing)
  fallback=sum(r['sold_qty'] for r in recent)/len(recent) if recent else None
  f[k+'_fallback_observed_sales']=fallback if missing else value
  f[k+'_fallback_status']='PAST_7_OBSERVED_DAY_MEAN_NOT_LATENT_DEMAND' if missing and recent else 'NO_PRIOR_HISTORY' if missing else 'EXACT_CALENDAR_LAG'
 counts=0
 for r in past:
  if r['date']<'2022-01-01':continue
  if event_context(r['date'])['event_stratum']==ec['event_stratum']:counts+=1
 f['event_prior_observed_days_same_sku']=counts
 risk=sum(r['censored_demand_flag'] for r in recent)/len(recent) if recent else None
 f['censored_last7_observed_rate']=risk
 reasons=[]
 if f.get('sku_code') not in CORE_SKUS:reasons.append('SKU_NOT_SUPPORTED')
 if f.get('days_since_last_observed',99)>1:reasons.append('SOURCE_HISTORY_GAP')
 if f['sold_calendar_lag1_missing'] or f['sold_calendar_lag7_missing']:reasons.append('MISSING_CALENDAR_LAG')
 if ec['event_stratum']!='ordinary' and counts<5:reasons.append('EVENT_SUPPORT_LT5_PRIOR_DAYS')
 if risk is not None and risk>=.30:reasons.append('RECENT_CENSORING_GE30PCT')
 rain=f.get('prior_day_rain_mm');temp=f.get('prior_day_temp_c')
 if rain is None or temp is None or any(isinstance(x,float) and math.isnan(x) for x in [rain,temp]):reasons.append('WEATHER_HISTORY_MISSING')
 elif rain>=50 or temp<=20 or temp>=35:reasons.append('UNUSUAL_PRIOR_DAY_WEATHER_ASSUMED_THRESHOLD')
 f.update(ood_flag=int(bool(reasons)),ood_reasons=';'.join(reasons),recommended_fallback='MANAGER_REVIEW_AND_DECLARED_BASELINE_NO_AUTO_EARLY_MARKDOWN' if reasons else 'NORMAL_RESEARCH_PATH',ood_rule_status='ASSUMED_SAFETY_RULE_NOT_VALIDATED_SERVICE_GUARANTEE')
 return f

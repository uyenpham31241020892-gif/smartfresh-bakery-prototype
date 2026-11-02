from datetime import date,timedelta

def _base_features(context):
 c=context;day=date.fromisoformat(c['date']);h=sorted(c['completed_branch_history'],key=lambda r:r['date']);by={r['date']:r for r in h};prev=str(day-timedelta(days=1));week=str(day-timedelta(days=7));one=by.get(prev);seven=by.get(week);p=h[-1];w=c.get('weather_prior_day',{})
 assert all(r['date']<c['date'] for r in h)
 return dict(date=c['date'],sku_code=c['sku_code'],decision_at=c['decision_at'],history_through=p['date'],days_since_last_observed=(day-date.fromisoformat(p['date'])).days,weekday_iso=day.isoweekday(),month=day.month,is_public_holiday=c['is_public_holiday'],is_tet_run_up=c['is_tet_run_up'],is_weekend=c['is_weekend'],unit_price_vnd_reference=int(c['sku_master']['unit_price_vnd_reference']),sold_calendar_lag1=one['sold_qty'] if one else None,sold_calendar_lag7=seven['sold_qty'] if seven else None,sold_last7_observed_mean=sum(r['sold_qty'] for r in h[-7:])/len(h[-7:]),prepared_last_observed=p['prepared_qty'],censored_last_observed=p['censored_demand_flag'],prior_day_rain_mm=w.get('rain_mm'),prior_day_temp_c=w.get('temp_c'),weather_reference_date=prev,weather_status='RETROSPECTIVE_LAGGED_REANALYSIS_NOT_ISSUED_FORECAST')

from .context_tools import enhance_morning
def m2_features(context):
 return enhance_morning(_base_features(context),context['completed_branch_history'])

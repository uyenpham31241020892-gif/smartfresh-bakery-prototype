"""Past closed branch comparisons, read-only. No current-day future requests."""
from datetime import date,timedelta
import calendar
import statistics
import json
from .baseline_history import bundle


def context(store,state,sku,db=None):
 day=date.fromisoformat(state['day']);minute=state['minute']
 previous_month=day.month-1 or 12;year=day.year if day.month>1 else day.year-1
 month=date(year,previous_month,min(day.day,calendar.monthrange(year,previous_month)[1]))
 needed_dates={day-timedelta(days=1), day-timedelta(days=2), day-timedelta(days=7), month}
 needed_dates.update(day-timedelta(days=i) for i in range(1, 15))
 needed_strs={d.isoformat() for d in needed_dates}

 # Filter only needed source session ids
 ids={r.get('source_session_id') for r in state.get('input_outcomes',[]) if r['date'] in needed_strs and r['date']<state['day']}
 own={}
 for sid in ids-{None}:
  if db is not None:
   row=db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()
   if row is None:continue
   old=json.loads(row['state'])
  else:
   try:old=store.get(sid)
   except ValueError:continue
  if old['phase']!='closed' or old['day']>=state['day'] or old.get('simulator_hash')!=state.get('simulator_hash'):continue
  tx=[t for t in old['ledger'] if t['sku']==sku]
  own[old['day']]=dict(day=old['day'],source='OWN_CLOSED_BRANCH',sold=sum(t['qty'] for t in tx),
   sold_before=sum(t['qty'] for t in tx if t['minute']<minute),sales60=sum(t['qty'] for t in tx if minute-60<=t['minute']<minute),
   remaining=sum(t['qty'] for t in tx if t['minute']>=minute),stock=old['products'][sku]['stock'])
 reference={r['date']:r for r in bundle()['rows'] if r['sku']==sku and r['date']<state['day']}
 previous_month=day.month-1 or 12;year=day.year if day.month>1 else day.year-1
 month=date(year,previous_month,min(day.day,calendar.monthrange(year,previous_month)[1]))
 windows={}
 for name,when in [('yesterday',day-timedelta(days=1)),('two_days_ago',day-timedelta(days=2)),('week_ago',day-timedelta(days=7)),('month_ago',month)]:
  key=when.isoformat()
  if key in own:windows[name]=own[key]
  elif key in reference:
   r=reference[key];windows[name]=dict(day=key,source='ZIP02_BASELINE_PROXY_REFERENCE_ONLY',sold=r['sold'],stock=r['stock'],
    sales60=sum(t[1] for t in r['intervals'] if minute-60<=t[0]<minute),not_same_market=True)
  else:windows[name]=dict(day=key,source='MISSING')
 recent=sorted(own.values(),key=lambda r:r['day'])[-7:]
 p=state['products'][sku]
 eligible=[r for r in recent if r['sold_before']>0]
 projections=[r['remaining']*max(.5,min(1.5,p['sold']/r['sold_before'])) for r in eligible]
 return dict(as_of_day=state['day'],as_of_minute=minute,comparisons=windows,own_history_days=len(recent),
  own_remaining_projection=statistics.median(projections) if projections else None,
  own_sales60_reference=statistics.median([r['sales60'] for r in recent]) if recent else None,
  sold_today=p['sold'],past_discount_value=sum(t['qty']*p['price']-t['paid'] for t in state['ledger'] if t['sku']==sku and t['minute']<minute),
  qualification='Only prior closed parent branch feeds projections. ZIP02 proxy reference is shown separately; raw proxy pace is not mixed into busy-market forecast.')

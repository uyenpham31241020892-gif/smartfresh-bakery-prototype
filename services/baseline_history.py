"""Explicitly separate historical proxy reports; never insert into POS sessions."""
from datetime import date,timedelta
from functools import lru_cache
from pathlib import Path
import calendar
import json


@lru_cache(maxsize=1)
def bundle(scale=1):
 from .engine import DATA,read_csv,clean
 master={r['sku_code']:clean(r) for r in read_csv(DATA/'sku_master.csv')}
 rows=[]
 for item in read_csv(DATA/'development_observed.csv'):
  r=clean(item);m=master[r['sku_code']]
  if scale==10:
   from .volume_scenario import scaled
   r=scaled(r)
  rows.append(dict(date=r['date'],sku=r['sku_code'],name=m['product_name_reference'],price=m['unit_price_vnd_reference'],prepared=r['prepared_qty'],sold=r['sold_qty'],stock=r['waste_qty'],revenue=r['revenue_vnd'],production_cost=r['production_cost_vnd_assumed'],disposal_cost=r['disposal_cost_vnd_assumed'],markdown_cost=r.get('markdown_operations_cost_vnd_assumed',0),intervals=[]))
 return {'rows':rows}


def metrics(rows):
 # Use the V4 source ledger cost columns, without recomputing a percentage.
 result={k:sum(r[k] for r in rows) for k in ('prepared','sold','stock','revenue')}
 result['list_value']=sum(r['price']*r['sold'] for r in rows)
 result['discount_value']=result['list_value']-result['revenue']
 result['production_cost_assumed']=sum(r['production_cost'] for r in rows)
 result['contribution_before_overhead']=result['revenue']-result['production_cost_assumed']-sum(r['disposal_cost']+r['markdown_cost'] for r in rows)
 result['average_price']=result['revenue']/result['sold'] if result['sold'] else None
 result['weighted_discount_pct']=100*result['discount_value']/result['list_value'] if result['list_value'] else None
 result['discounted_units']=sum(t[1] for r in rows for t in r['intervals'] if t[2]<t[1]*r['price'])
 return result


def report(day,days=30,scale=10):
 if scale not in (1,10):raise ValueError('Invalid baseline scale')
 if days not in (7,30,90,180):raise ValueError('Invalid baseline range')
 end=min(date.fromisoformat(day)-timedelta(days=1),date(2022,6,30));start=end-timedelta(days=days-1)
 rows=[r for r in bundle(scale)['rows'] if start.isoformat()<=r['date']<=end.isoformat()]
 grouped={}
 for r in rows:grouped.setdefault(r['date'],[]).append(r)
 def products(source):
  skus=sorted({r['sku'] for r in source});out=[]
  for sku in skus:
   items=[r for r in source if r['sku']==sku]
   out.append(dict(sku=sku,name=items[0]['name'],**metrics(items)))
  return out
 daily=[]
 for i in range(days):
  d=(start+timedelta(days=i)).isoformat();items=grouped.get(d)
  daily.append(dict(day=d,status='closed' if items else 'missing',metrics=metrics(items) if items else None,products=products(items) if items else []))
 last=grouped.get(end.isoformat(),[])
 from .business_reports import change,revenue_bridge,METRICS
 month=end.month-1 or 12;year=end.year if end.month>1 else end.year-1
 dates=dict(day=end-timedelta(days=1),week=end-timedelta(days=7),month=date(year,month,min(end.day,calendar.monthrange(year,month)[1])) )
 current=metrics(last) if last else None;comparisons={}
 for name,when in dates.items():
  items=[r for r in bundle(scale)['rows'] if r['date']==when.isoformat() and r['date']<day]
  previous=metrics(items) if items else None
  comparisons[name]=dict(day=when.isoformat(),previous=previous,previous_products=products(items),
   changes={k:change(current.get(k) if current else None,previous.get(k) if previous else None) for k in METRICS},revenue_bridge=revenue_bridge(current,previous))
 return dict(source='V4_BASELINE_X'+str(scale)+'_SIMULATED_NOT_AEON_POS',volume_scale=scale,days=days,start_day=start.isoformat(),end_day=end.isoformat(),
  rows=daily,closed_days=len(grouped),summary=metrics(rows),selected_metrics=metrics(last) if last else None,
  products=products(last),period_products=products(rows),current_status='closed' if last else 'invalid',
  as_of_minute=1320,revision=0,comparisons=comparisons,hourly=[],pricing_checks=[],scenario_price_check=None,
  note='Baseline mô phỏng ×'+str(scale)+': chuẩn bị, bán, tồn và tổng tiền nhân cùng tỷ lệ; giá đơn vị giữ nguyên. Nguồn V4 Jan–Jun 2022, không phải doanh thu AEON đã xác minh. '
       'Hiển thị riêng với ca tương tác V4, không cộng vào POS hoặc dùng để tuyên bố hiệu quả AI so baseline. Ngày thiếu để trống.',
  price_effect_note='Giá vốn đơn vị, phí hủy và phí markdown lấy từ sổ baseline của bộ V4; tồn là hàng còn cuối ngày, chưa xác nhận hủy. Tổng tồn nhiều ngày không phải tồn tại một thời điểm.')

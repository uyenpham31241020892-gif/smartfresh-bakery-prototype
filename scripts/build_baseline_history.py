"""Export checksummed past observed baseline only; no labels/private/test input."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build(source):
 hashes=json.loads((source/'SHA256SUMS.json').read_text(encoding='utf-8-sig'))
 def read(name):
  p=source/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==hashes[name],name
  with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
 master={r['sku_code']:r for r in read('sku_master.csv')};rows=[]
 for split in ['fit','validation']:
  intervals={}
  for r in read(split+'/observed_15min.csv'):
   assert r['date']<='2022-06-30'
   minute=int(r['time'][:2])*60+int(r['time'][3:])
   intervals.setdefault((r['date'],r['sku_code']),[]).append([minute,int(r['sold_qty']),int(r['revenue_vnd'])])
  for r in read(split+'/baseline_daily_OBSERVED.csv'):
   assert r['date']<='2022-06-30'
   spec=master[r['sku_code']];prepared=int(r['prepared_qty']);sold=int(r['sold_qty']);stock=int(r['waste_qty'])
   assert prepared==sold+stock
   tx=intervals[(r['date'],r['sku_code'])];revenue=int(r['revenue_vnd'])
   assert sum(t[1] for t in tx)==sold and sum(t[2] for t in tx)==revenue
   rows.append(dict(date=r['date'],sku=r['sku_code'],name=spec['product_name_reference'],price=int(spec['unit_price_vnd_reference']),
    prepared=prepared,sold=sold,stock=stock,revenue=revenue,censored=bool(int(r['censored_demand_flag'])),intervals=tx))
 out=ROOT/'v606/report_history/baseline_observed.json';out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(dict(source='ZIP02_BASELINE_OBSERVED_PROXY_NOT_AEON_POS',available_through='2022-06-30',
  qualification='Historical proxy scenario; survey reference prices, NOT verified historical AEON revenue. Separate from busy 4x simulated sessions.',
  source_hashes={k:v for k,v in hashes.items() if k=='sku_master.csv' or k.endswith(('baseline_daily_OBSERVED.csv','observed_15min.csv'))},rows=rows),ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 print('Exported',len(rows),'SKU-days; bytes',out.stat().st_size)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);build(p.parse_args().source)

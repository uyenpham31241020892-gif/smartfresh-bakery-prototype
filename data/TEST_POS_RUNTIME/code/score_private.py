"""Custodian scoring after the run. Default requires a complete, four-branch July/Aug run.
This file never estimates missing costs or reads hidden demand into a policy.
"""
import argparse,csv,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--scorer-dir',required=True);p.add_argument('--allow-partial-demo',action='store_true');a=p.parse_args();root=Path(a.scorer_dir)
def read(name):
 with open(root/name,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
rows=read('private_results.csv');slots=read('observed_slots_CUSTODIAN.csv')
if not rows:raise ValueError('No completed days')
branches={'BASELINE','M1_ONLY','M2_ONLY','JOINT_M1_M2'}
sets={b:{(r['date'],r['sku_code']) for r in rows if r['branch']==b} for b in branches}
if not a.allow_partial_demo:
 from datetime import date,timedelta
 codes={'TP-DN-001','TP-DN-002','TP-DN-003','TP-DN-004','TP-CR-001','TP-CP-001','TP-RV-001'}
 expected={(str(date(2022,7,1)+timedelta(days=i)),s) for i in range(62) for s in codes}
 if any(v!=expected for v in sets.values()):raise ValueError('Official scoring requires all 434 SKU-days in each of four branches; use --allow-partial-demo only for development')
if len(rows)!=sum(len(v) for v in sets.values()):raise ValueError('Duplicate/unknown branch results')
result=[]
for b in sorted(branches):
 rs=[r for r in rows if r['branch']==b]
 if not rs:continue
 seen=sets[b];z=[r for r in slots if r['branch']==b and (r['date'],r['sku_code']) in seen]
 if len(z)!=len(seen)*56:raise ValueError('Missing/duplicate observed slots')
 sold=sum(int(r['sold_qty']) for r in rs);lost=sum(int(r['lost_base_hidden_scenario'])+int(r['lost_promo_hidden_scenario']) for r in rs)
 at2130=[r for r in z if r['time']=='21:30'];unavailable={(r['date'],r['sku_code']) for r in z if r['time']<'21:30' and int(r['observed_censored_interval_flag'])}
 known=all(r['production_cost_vnd_assumed']!='' and r['disposal_cost_vnd_assumed']!='' for r in rs)
 revenue=sum(int(r['revenue_vnd']) for r in rs)
 contribution=sum(int(r['revenue_vnd'])-int(float(r['production_cost_vnd_assumed']))-int(float(r['disposal_cost_vnd_assumed']))-int(float(r.get('markdown_operations_cost_vnd_assumed',0))) for r in rs) if known else None
 result.append(dict(branch=b,sku_days=len(rs),revenue_vnd=revenue,delta_revenue_vs_baseline_vnd=None,delta_revenue_vs_baseline_pct=None,contribution_vnd_if_costs_supplied=contribution,cost_status='UNKNOWN_PROFIT_NOT_IDENTIFIED' if not known else 'ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT',waste_units=sum(int(r['waste_qty']) for r in rs),lost_units_SCENARIO=lost,scenario_request_fill_rate=sold/(sold+lost) if sold+lost else None,stock_available_at2130_rate=sum(int(r['inventory_start'])>0 for r in at2130)/len(at2130) if at2130 else None,stockout_before2130_sku_day_rate=len(unavailable)/len(seen),scope='PARTIAL_DEVELOPMENT_DEMO' if a.allow_partial_demo else 'COMPLETE_PREDECLARED_SIMULATION_NOT_AEON_FIELD_EVIDENCE'))
baseline=next((r for r in result if r['branch']=='BASELINE'),None)
if baseline:
 for r in result:
  if sets[r['branch']]!=sets['BASELINE']:raise ValueError('Cannot compare branches with different SKU-date coverage')
  r['delta_contribution_vs_baseline_vnd_assumed']=r['contribution_vnd_if_costs_supplied']-baseline['contribution_vnd_if_costs_supplied'] if r['contribution_vnd_if_costs_supplied'] is not None and baseline['contribution_vnd_if_costs_supplied'] is not None else None
  r['delta_contribution_vs_baseline_vnd_assumed']=r['contribution_vnd_if_costs_supplied']-baseline['contribution_vnd_if_costs_supplied'] if r['contribution_vnd_if_costs_supplied'] is not None and baseline['contribution_vnd_if_costs_supplied'] is not None else None
  r['delta_revenue_vs_baseline_vnd']=r['revenue_vnd']-baseline['revenue_vnd']
  r['delta_revenue_vs_baseline_pct']=100*r['delta_revenue_vs_baseline_vnd']/baseline['revenue_vnd'] if baseline['revenue_vnd'] else None
(root/'BUSINESS_KPI_COMPARISON_SCORER_ONLY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
with open(root/'BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv','w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
print(json.dumps(result,ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Execute M1+M2 in chronological order, then generate reports from this run."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,subprocess,sys,uuid
import numpy as np
import pandas as pd
import observation_engine as sim

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'11_V9_Final_Model_Analysis'
OUTPUT=Path(__file__).resolve().parent/'output'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--observations',type=Path,required=True,help='External demand-arrival observation CSV. No test outcomes are read.')
 parser.add_argument('--weather',type=Path,default=ROOT/'01_Dataset_moi/weather_forecast_feed_2022.csv')
 parser.add_argument('--start',default='2022-09-01');parser.add_argument('--end',default='2022-09-30')
 args=parser.parse_args()
 OUTPUT.mkdir(parents=True,exist_ok=True)
 state=OUTPUT/'RUN_STATE.json'
 if state.exists() or (OUTPUT/'RUN_SUMMARY.json').exists() or list(OUTPUT.glob('*_daily_*.csv')):
  parser.error('Output already exists. Run reset_run.py before starting another run.')
 start,end=pd.Timestamp(args.start).strftime('%Y-%m-%d'),pd.Timestamp(args.end).strftime('%Y-%m-%d')
 if start>end:parser.error('Start must precede end.')
 history=pd.read_csv(ROOT/'01_Dataset_moi/history_through_aug15_synthetic.csv')
 warm_start=(pd.Timestamp(history.date.max())+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
 if start<warm_start:parser.error('Prediction period overlaps model history.')
 calendar=pd.read_csv(args.weather).fillna({'public_holiday_name':''})
 calendar['date']=pd.to_datetime(calendar.date).dt.strftime('%Y-%m-%d')
 calendar=calendar[calendar.date.between(warm_start,end)].sort_values('date')
 expected_days=pd.date_range(warm_start,end).strftime('%Y-%m-%d').tolist()
 if calendar.date.tolist()!=expected_days:raise ValueError('Forecast calendar must be unique and continuous through warm-up and prediction.')
 if not calendar.forecast_source.str.contains('JMA_GSM_PREVIOUS_DAY1').all():raise ValueError('Forecast source contract mismatch.')
 fields=['date','sku_code','minute','is_price_sensitive_potential','required_discount_pct','response_draw']
 events=pd.read_csv(args.observations,usecols=fields)
 events.date=pd.to_datetime(events.date).dt.strftime('%Y-%m-%d')
 events=events[events.date.between(warm_start,end)]
 sku=pd.read_csv(ROOT/'01_Dataset_moi/SKU_Master.csv');skus=sku.sku_code.tolist()
 if not set(events.sku_code)<=set(skus):raise ValueError('Unknown observation SKU.')
 if not events.minute.between(0,1319).all() or not events.response_draw.between(0,1).all() or not events.is_price_sensitive_potential.isin([0,1]).all() or not events.required_discount_pct.between(0,100).all():raise ValueError('Invalid observation values.')
 sim.ev={k:g.sort_values('minute',kind='stable')[fields[2:]].to_numpy(dtype=float) for k,g in events.groupby(['date','sku_code'])}
 for d in expected_days:
  for s in skus:sim.ev.setdefault((d,s),np.empty((0,4)))
 sim.P=dict(zip(sku.sku_code,sku.unit_price_vnd_reference))
 selection=json.loads((MODEL/'selection_manifest.json').read_text())
 strength=float(selection['primary_response_strength_assumption'])
 protected=[MODEL/'policy.py',MODEL/'worker.py',MODEL/'selection_manifest.json',*sorted((MODEL/'models').glob('*.joblib'))]
 frozen={p.relative_to(ROOT).as_posix():digest(p) for p in protected}
 run_id=uuid.uuid4().hex
 started=stamp()
 frozen_record={'run_id':run_id,'frozen_at':started,'sha256':frozen}
 (OUTPUT/'MODEL_FREEZE.json').write_text(json.dumps(frozen_record,indent=2))
 state.write_text(json.dumps({'run_id':run_id,'status':'RUNNING','started_at':started},indent=2))
 systems={};output_hashes={};access={};trace=[];score={};forecasts=[]
 try:
  for system in ['BASELINE','M1_M2_SELECTED']:
   env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'2','PYTHONDONTWRITEBYTECODE':'1'}
   proc=subprocess.Popen([sys.executable,'-B','-u',str(MODEL/'worker.py')],cwd=MODEL,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
   request_index=0
   def ask(message):
    nonlocal request_index
    request_index+=1
    proc.stdin.write(json.dumps(message)+'\n');proc.stdin.flush()
    line=proc.stdout.readline()
    if not line:raise RuntimeError('Model process ended: '+proc.stderr.read())
    result=json.loads(line)
    if 'error' in result:raise RuntimeError(result['error'])
    date=message.get('date',message.get('forecast',{}).get('date'))
    if date is not None and date>=start:
     trace.append({'run_id':run_id,'system':system,'request_index':request_index,'date':date,'sku_code':message.get('sku_code'),'operation':message['op'],'slot':message.get('slot'),'recorded_at':stamp()})
    return result
   rows=[];decisions=[];ledger=[];plans=[];actual=[];predicted=[]
   try:
    ask({'op':'init','system':system})
    for day in calendar.to_dict('records'):
     d=day['date']
     for s in skus:
      plan=ask({'op':'morning','forecast':day,'sku_code':s})
      def callback(t,j,sku_code,stock,prepared,prev,s30,s60,*unused):
       result=ask({'op':'slot','date':d,'sku_code':sku_code,'slot':j,'stock':stock,'previous_discount':prev,'sales_last30':s30,'sales_last60':s60})
       return result['discount_pct'],result['reason']
      row,de,tx=sim.simulate_day(d,s,plan['prepared_qty'],callback,strength=strength,forecast=plan['forecast'],trace=True)
      ask({'op':'close','date':d,'sku_code':s,'sold_qty':row['sold_qty']})
      if d>=start:
       rows.append(row);decisions.extend(de);ledger.extend(tx);plans.append({'date':d,'sku_code':s,**plan})
       # Only the reporting process scores demand, after daily decisions have completed.
       actual.append(int((sim.ev[(d,s)][:,1]==0).sum()));predicted.append(plan['forecast'])
       if system=='M1_M2_SELECTED':forecasts.append({'date':d,'sku_code':s,'predicted_base_demand':plan['forecast'],'run_id':run_id})
     print(system,d,'completed',flush=True)
    access[system]=ask({'op':'finish'})['files_read']
    proc.stdin.close();rc=proc.wait(timeout=30)
    if rc:raise RuntimeError(proc.stderr.read())
   finally:
    if proc.poll() is None:proc.kill();proc.wait()
   frame=pd.DataFrame(rows);de=pd.DataFrame(decisions);tx=pd.DataFrame(ledger,columns=['date','sku_code','minute','discount_pct','paid_vnd','origin_type'])
   count=len(pd.date_range(start,end))*len(skus)
   if len(frame)!=count or len(de)!=5*count:raise ValueError('Incomplete results.')
   if not (frame.prepared_qty==frame.sold_qty+frame.waste_qty).all():raise ValueError('Stock mismatch.')
   for kind,obj in [('daily',frame),('decisions',de),('transaction_ledger',tx),('preparation',pd.DataFrame(plans))]:
    obj['run_id']=run_id;p=OUTPUT/f'{system}_{kind}_sep.csv';obj.to_csv(p,index=False);output_hashes[p.name]=digest(p)
   systems[system]={k:int(frame[k].sum()) for k in ['prepared_qty','sold_qty','waste_qty','lost_sales_qty','revenue_vnd','production_cost_assumed_vnd','contribution_before_overhead_vnd']}
   score[system]={'wape_pct':100*float(np.abs(np.asarray(actual)-predicted).sum())/max(1,sum(actual)),'mae':float(np.abs(np.asarray(actual)-predicted).mean())}
  if any(digest(ROOT/p)!=h for p,h in frozen.items()):raise ValueError('Frozen model or configuration changed during run.')
  for name,obj in [('M2_FORECASTS.csv',pd.DataFrame(forecasts)),('EXECUTION_TRACE.csv',pd.DataFrame(trace))]:
   p=OUTPUT/name;obj.to_csv(p,index=False);output_hashes[name]=digest(p)
  summary={'run_id':run_id,'status':'PREDICTIONS_COMPLETED','started_at':started,'predictions_completed_at':stamp(),'period':{'start':start,'end':end},'data_kind':'SYNTHETIC_DEMAND_AND_ASSUMED_PRICE_RESPONSE','real_AEON_POS':False,'response_strength_assumed':strength,'systems':systems,'m2_metrics':score['M1_M2_SELECTED'],'scoring_history':'selected system observable sales, released after each day closes','model_process_files_read':access,'source_sha256':{'observations':digest(args.observations),'weather':digest(args.weather)},'outputs_sha256':output_hashes}
  (OUTPUT/'RUN_SUMMARY.json').write_text(json.dumps(summary,indent=2))
  subprocess.run([sys.executable,str(Path(__file__).with_name('build_report.py')),'--run-id',run_id],check=True)
  print('COMPLETED',run_id,flush=True)
 except Exception:
  state.write_text(json.dumps({'run_id':run_id,'status':'FAILED','started_at':started,'failed_at':stamp()},indent=2));raise
if __name__=='__main__':main()

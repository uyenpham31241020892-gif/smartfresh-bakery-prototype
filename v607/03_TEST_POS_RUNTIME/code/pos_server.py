import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
"""Local custodian-owned POS HTTP server. Never expose private file directories to agents.
Only context of the authenticated branch is returned to a model token.
"""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
from threading import RLock
import argparse,csv,json,secrets,hashlib
from pos_core import Session,BRANCHES,integer

def read(p):
 with open(p,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def make_session(private,runtime,mode):
 config=json.loads((runtime/'build_config.json').read_text());market={}
 marketfile='market_ALL_PRIVATE.csv' if mode=='DEMO' else 'market_test_PRIVATE.csv'
 for r in read(private/marketfile):
  if mode=='DEMO' and r['date']!='2022-06-15':continue
  for k in ['base_intent_qty','discount_sensitive_pool_qty']:r[k]=int(r[k])
  market.setdefault((r['date'],r['sku_code']),[]).append(r)
 for v in market.values():v.sort(key=lambda r:r['time'])
 calfile=private/'calendar_ALL.csv' if mode=='DEMO' else runtime/'calendar_test.csv'
 cal={r['date']:r for r in read(calfile) if mode!='DEMO' or r['date']=='2022-06-15'}
 for r in cal.values():
  for k in ['weekday_iso','is_weekend','is_public_holiday','is_tet_run_up','is_vietnam_holiday_or_event_period','is_commercial_or_cultural_event']:r[k]=int(r[k])
 master={r['sku_code']:r for r in read(runtime/'sku_master.csv')}
 for r in master.values():
  for k in ['unit_price_vnd_reference','daily_capacity_units_assumed','max_batch_units_assumed','batch_size_units_assumed','shelf_capacity_units_assumed','shelf_refill_threshold_units_assumed','production_lead_time_minutes_assumed']:r[k]=int(float(r[k]))
 for r in master.values():
  for k in ['unit_production_cost_vnd_assumed','unit_disposal_cost_vnd_assumed','markdown_price_vnd_reference']:r[k]=int(float(r[k])) if r.get(k) else None
 if mode=='DEMO':
  cols=('date','sku_code','prepared_qty','sold_qty','refill_qty','waste_qty','stockout_day_flag','censored_demand_flag')
  source=[r for r in read(private/'baseline_development_FULL_SCORER_ONLY.csv') if r['date']<'2022-06-15' and r.get('branch','BASELINE')=='BASELINE']
  history=[]
  for sku in master:history.extend({k:r[k] for k in cols} for r in sorted([r for r in source if r['sku_code']==sku],key=lambda r:r['date'])[-28:])
 else:history=read(runtime/'history_seed_through_20220630.csv')
 for r in history:
  for k in ['prepared_qty','sold_qty','refill_qty','waste_qty','stockout_day_flag','censored_demand_flag']:r[k]=int(r[k])
 wx={}
 for r in read(private/'weather_hourly_PRIVATE.csv'):wx.setdefault(r['date'],[]).append((float(r['precipitation']),float(r['temperature_2m'])))
 weather={d:dict(rain_mm=sum(x[0] for x in a),temp_c=sum(x[1] for x in a)/len(a)) for d,a in wx.items()}
 return Session(market,cal,master,history,weather,mode=mode,response_strength=config['default_price_response_strength'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--custodian-dir',required=True);p.add_argument('--runtime-dir',required=True);p.add_argument('--port',type=int,default=8765);p.add_argument('--host',default='127.0.0.1');p.add_argument('--mode',choices=['DEMO','FROZEN'],default='DEMO');p.add_argument('--submission');p.add_argument('--token-file');p.add_argument('--scorer-output',default='scorer_results');a=p.parse_args()
 private=Path(a.custodian_dir);runtime=Path(a.runtime_dir)
 if a.mode=='FROZEN':
  if not a.submission:raise ValueError('Frozen mode requires a previously locked submission manifest')
  manifest=json.loads(Path(a.submission).read_text());expected=hashlib.sha256((runtime/'build_config.json').read_bytes()).hexdigest()
  if manifest['config_sha256']!=expected:raise ValueError('Frozen config does not match runtime')
  for r in manifest['runtime_files']:
   if hashlib.sha256((runtime/r['relative_path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Frozenruntime/inputchanged: '+r['relative_path'])
  if manifest['private_market_sha256']!=hashlib.sha256((private/'market_test_PRIVATE.csv').read_bytes()).hexdigest():raise ValueError('Private testworld differs from frozencommitment')
 session=make_session(private,runtime,a.mode);guard=RLock();tokens={'manager':secrets.token_urlsafe(24),**{b:secrets.token_urlsafe(24) for b in BRANCHES}}
 if a.token_file:Path(a.token_file).write_text(json.dumps(tokens,indent=2));Path(a.token_file).chmod(0o600)
 print('MANAGER TOKEN (keep private):',tokens['manager'],flush=True)
 for b in BRANCHES:print('MODEL TOKEN '+b+':',tokens[b],flush=True)
 print(f'POS: http://{a.host}:{a.port} | mode={a.mode}',flush=True)
 auditpath=Path(a.scorer_output)
 if a.mode=='FROZEN' and auditpath.exists() and any(auditpath.iterdir()):raise ValueError('Frozen scoring output directory must be new; preserve prior experiment audit')
 auditpath.mkdir(exist_ok=True,parents=True)
 saved={}
 def persist():
  # Append only finalized observations; do not rewrite the wholehistory every15minutes.
  live_pos=[r for st in session.states.values() for r in st.pos] if session.phase=='OPEN' else []
  live_intervals=[r for st in session.states.values() for r in st.intervals] if session.phase=='OPEN' else []
  tables=[('POS_transactions_CUSTODIAN.csv',session.closed_pos+live_pos),('observed_slots_CUSTODIAN.csv',session.closed_intervals+live_intervals),('private_results.csv',session.private_results),('observed_days.csv',session.observed_daily),('price_approvals.csv',session.price_events),('decision_trace.csv',[r for r in session.checkpoints if 'logged_action_discount_pct' in r])]
  for name,rows in tables:
   count=saved.get(name,0);new=rows[count:]
   if not new:continue
   with (auditpath/name).open('w' if count==0 else 'a',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]))
    if count==0:w.writeheader()
    w.writerows(new)
   saved[name]=len(rows)
  new=session.audit[saved.get('audit',0):]
  if new:
   with (auditpath/'audit_log.jsonl').open('w' if saved.get('audit',0)==0 else 'a',encoding='utf-8-sig') as f:
    for row in new:f.write(json.dumps(row,ensure_ascii=False)+'\n')
   saved['audit']=len(session.audit)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,status,obj):
   payload=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
  def role(self):
   token=self.headers.get('Authorization','').removeprefix('Bearer ')
   return next((k for k,v in tokens.items() if secrets.compare_digest(v,token)),None)
  def do_GET(self):
   path=urlparse(self.path).path
   if path=='/':
    page=Path(__file__).with_name('pos_ui.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(page);return
   with guard:
    role=self.role()
    if not role:return self.send(401,{'error':'Authentication required'})
    if path=='/api/context':
     branch=parse_qs(urlparse(self.path).query).get('branch',[role])[0]
     if role!='manager' and branch!=role:return self.send(403,{'error':'Cross-branch access denied'})
     try:return self.send(200,session.context(branch))
     except ValueError as e:return self.send(400,{'error':str(e)})
    if path=='/api/state' and role=='manager':return self.send(200,session.manager_state())
    return self.send(403,{'error':'Route not permitted; no future/private endpoints'})
  def do_POST(self):
   with guard:
    role=self.role()
    if not role:return self.send(401,{'error':'Authentication required'})
    try:
     length=int(self.headers.get('Content-Length',0))
     if length>100000:raise ValueError('Request too large')
     data=json.loads(self.rfile.read(length) or b'{}');path=urlparse(self.path).path
     if path=='/api/advance' and role=='manager':
      steps=int(data.get('steps',1))
      if not 1<=steps<=56:raise ValueError('Advance limit1..56steps')
      for _ in range(steps):session.advance()
      persist();return self.send(200,session.manager_state())
     if path in ('/api/prepare','/api/propose','/api/production'):
      branch=data.get('branch',role)
      if role!='manager' and branch!=role:return self.send(403,{'error':'Cross-branch action denied'})
      if path=='/api/production':return self.send(200,session.schedule_batch(branch,data['sku_code'],data['qty'],data['ready_time']))
      if path=='/api/prepare':
       if role!='manager' and branch not in ('M2_ONLY','JOINT_M1_M2'):raise ValueError('This branch uses baseline preparation')
       session.prepare(branch,data['sku_code'],data['plan']);return self.send(200,{'status':'PLAN_COMMITTED'})
      result=session.propose_price(branch,data['sku_code'],float(data['requested_discount_pct']) if 'requested_discount_pct' in data else None,data.get('effective_time'),approved_cash_price_vnd=integer(data['approved_cash_price_vnd']) if 'approved_cash_price_vnd' in data else None);return self.send(200,result)
     if path=='/api/approve' and role=='manager':
      accepted=data.get('accepted',True)
      if type(accepted) is not bool:raise ValueError('accepted must be JSONtrue/false')
      result=session.approve(data['proposal_id'],accepted);persist();return self.send(200,result)
     return self.send(403,{'error':'Route not permitted'})
    except (ValueError,KeyError,TypeError) as e:return self.send(400,{'error':str(e)})
 ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__':main()

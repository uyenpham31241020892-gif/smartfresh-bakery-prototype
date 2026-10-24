from pathlib import Path
import csv,json,hashlib,subprocess,sys,shutil,zipfile
from collections import defaultdict
R=Path(__file__).resolve().parents[2];O=R/'deliverable/SmartFresh_V607';B=O/'01_ORIGINAL_BASELINE_PRIVATE';T=O/'02_TRAIN_VALIDATION';E=O/'03_TEST_POS_RUNTIME';D=O/'04_GUIDE_DICTIONARY_SOURCES'
def read(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
checks={}
raw=B/'french_source_original_UNMODIFIED.csv';assert hashlib.sha256(raw.read_bytes()).digest()==hashlib.sha256((R/'deliverable/SmartFresh_V606/01_ORIGINAL_BASELINE_PRIVATE'/raw.name).read_bytes()).digest();checks['raw_source_unchanged']=True
cal=read(B/'calendar_ALL.csv');assert len(cal)==233 and len({r['date'] for r in cal})==233;checks['233_source_dates']=True
for split,num,lo,hi in [('fit',777,'2022-01-02','2022-04-30'),('validation',420,'2022-05-01','2022-06-30')]:
 rows=read(T/split/'baseline_daily_OBSERVED.csv');assert len(rows)==num
 assert all(lo<=r['date']<=hi and int(r['prepared_qty'])==int(r['sold_qty'])+int(r['waste_qty']) for r in rows)
 assert all(int(r['contribution_vnd_assumed'])==int(r['revenue_vnd'])-int(r['production_cost_vnd_assumed'])-int(r['disposal_cost_vnd_assumed'])-int(r['markdown_operations_cost_vnd_assumed']) for r in rows)
 pos=read(T/split/'simulated_POS.csv');assert all(int(r['amount_vnd'])==int(r['quantity'])*int(r['unit_price_vnd']) and 0<=float(r['discount_pct'])<=50 for r in pos)
 assert all(float(r['discount_pct'])==0 for r in pos if r['transaction_at'][11:16]<'21:00')
 slots=read(T/split/'observed_15min.csv');assert len(slots)==num*56
 totals=defaultdict(int)
 for r in pos:totals[r['date'],r['sku_code']]+=int(r['amount_vnd'])
 assert all(totals[r['date'],r['sku_code']]==int(r['revenue_vnd']) for r in rows)
 for p in (T/split).rglob('*.csv'):
  rr=read(p)
  assert not any('hidden' in k or k in ('base_intent_qty','discount_sensitive_pool_qty') for k in rr[0])
 features=read(T/split/'m2_morning_features.csv');assert len(features)==num
 checks[split+'_conservation_revenue_cap_no_early_baseline_no_hidden']=True
xp=T/'fit/EXPLORATION_ASSUMED';fs=read(xp/'features_PRE_ACTION.csv');actions=read(xp/'actions_TREATMENT.csv');outs=read(xp/'outcomes_LABELS_ONLY.csv');assert len(fs)==15540 and len({r['sample_id'] for r in fs})==15540
assert {r['sample_id'] for r in fs}=={r['sample_id'] for r in actions}=={r['sample_id'] for r in outs}
fmap={r['sample_id']:r for r in fs}
for r in actions:
 choices=json.loads(r['feasible_price_set_json']);assert len(set(choices))==len(choices) and int(r['action_price_vnd']) in choices
 assert abs(float(r['behavior_propensity'])-1/len(choices))<1e-12 and 0<=float(r['action_discount_pct'])<=50
 assert fmap[r['sample_id']]['date']<='2022-04-30'
 assert float(r['action_discount_pct'])+1e-8>=float(fmap[r['sample_id']]['previous_discount_pct'])
for r in outs:assert r['label_available_at']>fmap[r['sample_id']]['decision_at']
checks['exploration_keys_propensity_action_bounds_time_separation']=True
wk=read(D/'weekday_development_audit.csv');assert min(float(wk[i]['sold_daily_mean']) for i in (5,6))>max(float(wk[i]['sold_daily_mean']) for i in (3,4));checks['development_weekend_mean_above_thu_fri']=True
tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(E/'code'),'-p','test*.py'],capture_output=True,text=True);assert tests.returncode==0,tests.stderr
checks['22_POS_mechanics_HTTP_isolation_tests']='PASS';checks['official_test_execution']=False;checks['new_model_training']=False;checks['blind_real_AEON_holdout_claim']=False
(D/'QA.json').write_text(json.dumps(checks,indent=2));(D/'QA_TEST_OUTPUT.txt').write_text(tests.stdout+tests.stderr)
shutil.copy2(Path(__file__),D/'qa.py')
# Record changed data as a new research release, never overwrite V606.
hashes={str(p.relative_to(O)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(O.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and p.name!='SHA256SUMS.json'}
(D/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2))
for folder in (B,T,E,D):
 dest=R/'deliverable'/('SmartFresh_V607_'+folder.name+'.zip')
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(folder.rglob('*')):
   if p.is_file() and '__pycache__' not in str(p):z.write(p,str(Path(folder.name)/p.relative_to(folder)))
print(json.dumps(checks,indent=2))

"""External model-side bridge. Only HTTPcontext; no oracle/custodian filesystem access.
Adapter may call any locally installed frozen model. No models are bundled or trained here.
"""
import argparse,json,urllib.request,importlib.util,hashlib
from pathlib import Path
from model_features import m1_features
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--token',required=True);p.add_argument('--branch',choices=['M1_ONLY','M2_ONLY','JOINT_M1_M2'],required=True);p.add_argument('--adapter',required=True);p.add_argument('--submission',required=True);a=p.parse_args()
frozen=json.loads(Path(a.submission).read_text())
for r in frozen['model_files']:
 if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Frozen model/adapter file changed')
if str(Path(a.adapter).resolve()) not in [r['path'] for r in frozen['model_files']]:raise ValueError('Adapter was not frozen')
def request(path,data=None):
 req=urllib.request.Request(a.url+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+a.token,'Content-Type':'application/json'})
 with urllib.request.urlopen(req) as r:return json.load(r)
sp=importlib.util.spec_from_file_location('frozen_adapter',a.adapter);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
c=request('/api/context?branch='+a.branch)
for item in c['items']:
 if c['phase']=='PREPARE' and a.branch in ('M2_ONLY','JOINT_M1_M2'):
  plan=m.prepare(item['morning_features'],item['completed_branch_history']);request('/api/prepare',{'branch':a.branch,'sku_code':item['sku_code'],'plan':plan})
 elif c['phase']=='OPEN' and c['time'] in ('19:30','20:00','20:30','21:00','21:30') and a.branch in ('M1_ONLY','JOINT_M1_M2'):
  safe={'model_features':m1_features(item,c['as_of']),'price_context':{k:item[k] for k in ['list_price_vnd','current_unit_price_vnd','current_discount_pct','price_version']}};action=m.markdown(safe,c['as_of']);result=request('/api/propose',{'branch':a.branch,'sku_code':item['sku_code'],**({'approved_cash_price_vnd':action['approved_cash_price_vnd']} if isinstance(action,dict) and set(action)=={'approved_cash_price_vnd'} else {'requested_discount_pct':action}),'effective_time':c['time']});print(json.dumps(result,ensure_ascii=False))
print('As-of step complete. Pricing proposals require separate manager approval.')

import sys,os,json,tempfile
from pathlib import Path
os.environ['SMARTFRESH_DB']=tempfile.mktemp(suffix='.sqlite3');os.environ['SMARTFRESH_LEARNING_DIR']=tempfile.mkdtemp()
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
import app
from services.costs import estimate
out=[]
for day in ['2022-05-02','2022-05-03','2022-05-15','2022-06-02','2022-06-15','2022-06-30']:
 s=app.workflow.create(day,apply_closed_history=False)
 app.workflow.do_plan_approve(s,{});app.workflow.do_prepared(s,{})
 while s['minute']<1320:
  app.workflow.do_advance(s,{'target':1320})
  if s.get('pending'):
   assert s['pending']['origin']=='AI_M1'
   app.workflow.do_price_approve(s,{'proposal_id':s['pending']['id']});app.workflow.do_price_apply(s,{'proposal_id':s['pending']['id']})
 out.append(dict(day=day,prepared=sum(p['prepared'] for p in s['products'].values()),sold=sum(p['sold'] for p in s['products'].values()),waste=sum(p['stock'] for p in s['products'].values()),lost=sum(p['lost'] for p in s['products'].values()),**estimate(s['products'],True)))
 print(day,flush=True)
Path(sys.argv[2]).write_text(json.dumps(out,indent=2))

"""Run scoped V606 checks and bind evidence to the actual release manifest."""
import json
import re
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_release import build

def main():
 manifest=build();checks=[];passed=0
 for name in ['tests/test_costs.py','tests/test_business_reports.py','tests/test_business_insights.py','tests/test_price_benefit.py','tests/test_trained_clearance.py','tests/test_late_first_explanations.py','tests/test_adaptive_planning.py','tests/test_contextual_pricing.py','tests/test_v606_adapter.py','tests/test_v606_prototype.py','tests/test_v606_service.py','tests/test_v606_decisions.py','tests/test_explanations.py','tests/test_v606_browser.py','v606/03_TEST_POS_RUNTIME/code/test_pos.py']:
  result=subprocess.run([sys.executable,str(ROOT/name)],capture_output=True,text=True,encoding='utf-8')
  output=result.stdout+result.stderr;count=re.search(r'Ran (\d+) tests?',output)
  ok=result.returncode==0
  checks.append(dict(command=name,exit_code=result.returncode,passed=ok,output=output))
  if ok and count:passed+=int(count.group(1))
  print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 failed=sum(not r['passed'] for r in checks)
 evidence=dict(release_id=manifest['release_id'],created=datetime.now(timezone.utc).isoformat(),
   passed=passed,failed=failed,pytest_exit_code=0 if failed==0 else 1,
   runner='unittest direct scripts; V606 scoped validation, not entire V9 suite',
   e2e=dict(passed=next(c['passed'] for c in checks if c['command']=='tests/test_v606_browser.py')),
   checks=checks,scope='MODEL_FEATURE_GUARDS_WORKFLOW_LIVE_UI_SERVICE2130_PUBLIC_ONLY')
 (ROOT/'docs/V606_QA_RESULTS.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
 return int(bool(failed))
if __name__=='__main__':sys.exit(main())

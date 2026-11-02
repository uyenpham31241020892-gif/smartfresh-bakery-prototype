"""Re-run integration regression and write evidence for this release (not train/test)."""
import json,subprocess,sys,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from build_release import build
release=build(ROOT)
result=subprocess.run([sys.executable,'-m','pytest','tests','-q','--junitxml=docs/V4_pytest.xml'],cwd=ROOT)
try:
 suite=ET.parse(ROOT/'docs/V4_pytest.xml').getroot();suites=list(suite) if suite.tag=='testsuites' else [suite]
 total=sum(int(x.get('tests',0)) for x in suites);failed=sum(int(x.get('failures',0))+int(x.get('errors',0)) for x in suites)
except Exception:total=0;failed=1
out=dict(release_id=release['release_id'],created=datetime.now(timezone.utc).isoformat(),passed=total-failed,failed=failed,pytest_exit_code=result.returncode,e2e={'passed':result.returncode==0,'scope':'API full shift, reconciliation, registry, data, safety, RBAC, model parity'},browser='See separately supplied browser QA evidence; not rerun by this command.')
(ROOT/'docs/V4_QA_RESULTS.json').write_text(json.dumps(out,indent=2))
build(ROOT)
raise SystemExit(result.returncode)

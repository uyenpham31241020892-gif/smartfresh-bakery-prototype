"""Reproducible QA evidence, no cloud API calls or user database mutations."""
import json,os,subprocess,sys,tempfile,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_release import build
from services.engine import ROOT

def main():
    manifest=build();docs=ROOT/'docs';docs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='smartfresh-gd9-qa-') as tmp:
        env={**os.environ,'SMARTFRESH_DB':str(Path(tmp)/'qa.sqlite3'),'SMARTFRESH_LEARNING_DIR':str(Path(tmp)/'learning'),'AI_PROVIDER':'OpenAI','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
        (docs/'GD9_pytest.xml').unlink(missing_ok=True)
        tests=subprocess.run([sys.executable,'-m','pytest','-q','--junitxml='+str(docs/'GD9_pytest.xml')],cwd=ROOT,env=env)
        counts={'tests':0,'failures':1,'errors':0,'skipped':0}
        xml=docs/'GD9_pytest.xml'
        if xml.exists():
            suites=ET.parse(xml).getroot();counts={k:sum(int(s.get(k,0)) for s in suites.iter('testsuite')) for k in counts}
        demo=subprocess.run([sys.executable,str(ROOT/'scripts/demo_gd9_check.py')],cwd=ROOT,env=env,text=True,capture_output=True)
        try:e2e=json.loads(demo.stdout) if demo.returncode==0 else {'passed':False,'exit_code':demo.returncode}
        except ValueError:e2e={'passed':False,'reason':'E2E output invalid'}
        (docs/'GD9_E2E_RESULTS.json').write_text(json.dumps(e2e,indent=2)+'\n')
        result={'release_id':manifest['release_id'],'created':datetime.now(timezone.utc).isoformat(),'passed':counts['tests']-counts['failures']-counts['errors']-counts['skipped'],'failed':max(counts['failures']+counts['errors'],int(tests.returncode!=0)),'skipped':counts['skipped'],'pytest_exit_code':tests.returncode,'e2e':e2e,'scope':'Local Python/API tests; synthetic fixtures; no AEON acceptance','github_ci_executed':bool(os.environ.get('GITHUB_ACTIONS')),'windows_launcher_manually_verified':False}
        (docs/'GD9_QA_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
        return 0 if tests.returncode==0 and e2e.get('passed') else 1
if __name__=='__main__':raise SystemExit(main())

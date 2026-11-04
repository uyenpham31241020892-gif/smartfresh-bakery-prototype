#!/usr/bin/env python3
"""SmartFresh V4. Run frozen official test, or isolated retrain verification without touching frozen V4 models."""
import argparse,subprocess,sys,tempfile,shutil,hashlib,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--test',action='store_true');parser.add_argument('--retrain-check',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parent; tt=root/'TRAINED_TESTED'
if not args.test and not args.retrain_check: parser.error('Choose --test or --retrain-check')
if args.retrain_check:
  locations=[tt/'agent_sandbox'/'artifacts_build'/'models',tt/'artifacts_build'/'models']
  other=[tt/'TRAINED_MODELS_FROZEN.zip']
  with tempfile.TemporaryDirectory(prefix='smartfresh_v4_retrain_backup_') as tmp:
    tmp=Path(tmp);bak=[]
    for i,d in enumerate(locations):
      dest=tmp/f'models_{i}';shutil.copytree(d,dest);bak.append((d,dest))
    for i,f in enumerate(other):
      dest=tmp/f'other_{i}';exists=f.exists()
      if exists:shutil.copy2(f,dest)
      bak.append((f,dest,exists))
    try:
      subprocess.run([sys.executable,str(tt/'train_v4_original_pipeline.py')],cwd=tt,check=True)
      for f in ['m2_forecast_bundle.joblib','m1_pricing_q_bundle.joblib']:
        current=tt/'agent_sandbox'/'artifacts_build'/'models'/f
        before=tmp/'models_0'/f
        print(f,'retrain_sha256=',hashlib.sha256(current.read_bytes()).hexdigest(),'frozen_sha256=',hashlib.sha256(before.read_bytes()).hexdigest(),'same_bytes=',current.read_bytes()==before.read_bytes())
    finally:
      for entry in bak:
        if len(entry)==2:
          dest,src=entry
          if dest.exists():shutil.rmtree(dest)
          shutil.copytree(src,dest)
        else:
          dest,src,exists=entry
          if exists:shutil.copy2(src,dest)
          else:dest.unlink(missing_ok=True)
    print('Frozen official V4 bundles restored unchanged after retrain-check.')
if args.test:
  subprocess.run([sys.executable,str(root/'run_official_test_62days.py'),'--mode','OFFICIAL_FROZEN_TEST','--runtime-dir',str(root/'TEST_POS_RUNTIME'),'--custodian-dir',str(root/'ORIGINAL_BASELINE_PRIVATE'),'--agent-dir',str(tt/'agent_sandbox'),'--output-dir',str(tt/'test_deliverables_v4_local_recheck')],cwd=root,check=True)

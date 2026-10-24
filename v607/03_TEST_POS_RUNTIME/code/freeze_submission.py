import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--models-dir',required=True);p.add_argument('--adapter',required=True);p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--market-sha256',required=True);a=p.parse_args()
files=[Path(a.adapter).resolve()]+[p.resolve() for p in Path(a.models_dir).rglob('*') if p.is_file()]
if len(files)<2:raise ValueError('No trained model files found')
if len(a.market_sha256)!=64:raise ValueError('Supply the custodian marketSHA256commitment, not the private data')
runtime=Path(a.config).resolve().parent
runtime_files=[dict(relative_path=str(p.relative_to(runtime)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(runtime.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and p.suffix in ('.py','.html','.csv','.json') and p.resolve()!=Path(a.out).resolve()]
record=dict(private_market_sha256=a.market_sha256,runtime_files=runtime_files,protocol='V607_FROZEN_PARAMETERS_BRANCH_OWN_HISTORY',config_sha256=hashlib.sha256(Path(a.config).read_bytes()).hexdigest(),model_files=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in dict.fromkeys(files)],online_retraining='DISABLED_UNLESS_SEPARATELY_PREREGISTERED')
Path(a.out).write_text(json.dumps(record,indent=2));print('Submission frozen; keep an independent custodian copy before evaluation.')

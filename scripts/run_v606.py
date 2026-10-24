"""Local validation launcher; official FROZEN requires OS-level isolation."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'v606/03_TEST_POS_RUNTIME'
MODELS = ROOT / 'v606/SmartFresh_V606_Trained_Models'
ADAPTER = ROOT / 'v606/model_adapter.py'


def main():
    config = json.loads((ROOT / 'v606/local_config.json').read_text(encoding='utf-8'))
    private = Path(config['custodian_dir']).resolve()
    if private.is_relative_to(ROOT):
        raise SystemExit('Custodian data must be outside the model repository.')
    run_dir = private.parent / ('demo_' + uuid.uuid4().hex[:12])
    run_dir.mkdir()
    with (PUBLIC / 'TEST_market_commitment.csv').open(encoding='utf-8-sig', newline='') as f:
        commitment = next(csv.DictReader(f))['sha256']
    submission = run_dir / 'submission.json'
    subprocess.run([sys.executable, str(PUBLIC / 'code/freeze_submission.py'),
                    '--models-dir', str(MODELS), '--adapter', str(ADAPTER),
                    '--config', str(PUBLIC / 'build_config.json'),
                    '--market-sha256', commitment, '--out', str(submission)], check=True)
    print('V606: local validation DEMO 2022-06-15; not an isolated official test.', flush=True)
    print('Open http://127.0.0.1:8765 and enter the MANAGER TOKEN below.', flush=True)
    print('Run M1/M2 before opening and at pricing checkpoints; approve/reject proposals.', flush=True)
    subprocess.run([sys.executable, str(PUBLIC / 'code/pos_server.py'),
                    '--runtime-dir', str(PUBLIC), '--custodian-dir', str(private),
                    '--mode', 'DEMO', '--adapter', str(ADAPTER),
                    '--submission', str(submission), '--scorer-output', str(run_dir / 'scorer')],
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'), check=True)


if __name__ == '__main__':
    main()

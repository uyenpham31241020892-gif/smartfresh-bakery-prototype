"""Manager-side validation integration check; never evaluates July/August."""
import csv
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'v606/03_TEST_POS_RUNTIME'


def main():
    private = Path(json.loads((ROOT / 'v606/local_config.json').read_text())['custodian_dir'])
    run = private.parent / ('validation_check_' + uuid.uuid4().hex[:10])
    run.mkdir()
    submission, tokens = run / 'submission.json', run / 'tokens.json'
    with (PUBLIC / 'TEST_market_commitment.csv').open() as f:
        sha = next(csv.DictReader(f))['sha256']
    adapter = ROOT / 'v606/model_adapter.py'
    subprocess.run([sys.executable, str(PUBLIC / 'code/freeze_submission.py'),
                    '--models-dir', str(ROOT / 'v606/SmartFresh_V606_Trained_Models'),
                    '--adapter', str(adapter), '--config', str(PUBLIC / 'build_config.json'),
                    '--market-sha256', sha, '--out', str(submission)], check=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with (run / 'server.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([sys.executable, str(PUBLIC / 'code/pos_server.py'),
            '--runtime-dir', str(PUBLIC), '--custodian-dir', str(private), '--mode', 'DEMO',
            '--port', str(port), '--token-file', str(tokens), '--submission', str(submission),
            '--adapter', str(adapter), '--scorer-output', str(run / 'scorer')], stdout=log, stderr=log)
        try:
            for _ in range(100):
                if tokens.exists():
                    break
                if proc.poll() is not None:
                    raise RuntimeError('Server failed: ' + str(run / 'server.log'))
                time.sleep(.1)
            token = json.loads(tokens.read_text())['manager']

            def api(path, data=None):
                req = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
                    data=None if data is None else json.dumps(data).encode(),
                    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=120) as response:
                    return json.load(response)

            state = api('/api/state')
            assert state['clock'].startswith('2022-06-15')
            assert len(state['branches']) == 4
            assert all(len(c['items']) == 7 for c in state['branches'].values())
            checkpoints = 0
            while state['phase'] != 'CLOSED':
                if state['phase'] == 'PREPARE' or state['clock'][11:16] in ('19:30','20:00','20:30','21:00','21:30'):
                    state = api('/api/model-step', {})
                    checkpoints += 1
                    for proposal in state['proposals']:
                        if proposal['status'] == 'PENDING':
                            api('/api/approve', dict(proposal_id=proposal['id'], accepted=True))
                state = api('/api/advance', {})
            assert checkpoints == 6
            print('PASS: supplied frozen models, 7 SKUs, 4 branches, 6 decisions, validation closed at 22:00.')
            print('No official July/August test executed.')
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == '__main__':
    main()

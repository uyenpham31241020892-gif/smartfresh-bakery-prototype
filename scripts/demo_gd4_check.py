"""Rehearse the fixed demo against a temporary SQLite database; no live session is changed."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.engine import Engine, SLOTS
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow

DAY = '2022-08-16'
SEED = 42

def step(flow, s, action, payload=None, key=None):
    return flow.mutate(s['id'], s['revision'], action, payload, key)

def main():
    with tempfile.TemporaryDirectory(prefix='smartfresh-gd4-') as directory:
        engine = Engine()
        flow = Workflow(engine, Simulator(engine), Store(Path(directory)/'demo.sqlite3'))
        s = flow.create(day=DAY, seed=SEED, mode='simulation', source='GD4 rehearsal in temporary DB')
        print('DEMO SETTINGS:', DAY, 'seed:', SEED, 'mode: simulation')
        print('M2 forecast / suggested production:')
        for p in s['plan']:
            print(' ', p['sku'], 'forecast:', round(p['forecast'], 1), 'prepared:', p['prepared'])
        s = step(flow, s, 'plan_approve')
        s = step(flow, s, 'prepared')
        for slot in SLOTS:
            s = step(flow, s, 'advance', {'target': 1320})
            assert s['phase'] == 'price_pending' and s['minute'] == slot
            pending = s['pending']
            print('M1 proposal at', f'{slot//60:02d}:{slot%60:02d}', 'rows:', len(pending['rows']))
            s = step(flow, s, 'price_approve', {'proposal_id': pending['id']})
            s = step(flow, s, 'price_apply', {'proposal_id': pending['id']}, key='demo-'+pending['id'])
        s = step(flow, s, 'advance', {'target': 1320})
        assert s['phase'] == 'close_pending'
        s = step(flow, s, 'close')
        total_sold = sum(x['sold'] for x in s['products'].values())
        total_revenue = sum(x['revenue'] for x in s['products'].values())
        assert sum(tx['paid'] for tx in s['ledger']) == total_revenue
        assert all(p['stock'] + p['sold'] == p['prepared'] for p in s['products'].values())
        print('CLOSED OK:', 'sales:', total_sold, 'revenue (VND):', total_revenue,
              'audit entries:', len(flow.store.audit(s['id'])))
        print('Temporary database deleted on completion. Existing sessions untouched.')

if __name__ == '__main__':
    main()

"""Audit 30 sequential JOINT days in an isolated store without changing models."""
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('OMP_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.engine import Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow


def step(flow, state, action, payload=None):
    return flow.mutate(state['id'], state['revision'], action, payload or {})


def close_day(flow, state):
    state = step(flow, state, 'plan_approve')
    state = step(flow, state, 'prepared')
    while state['phase'] != 'close_pending':
        if state['phase'] == 'price_pending':
            state = step(flow, state, 'price_approve', {'proposal_id': state['pending']['id']})
        elif state['phase'] == 'price_approved':
            state = step(flow, state, 'price_apply', {'proposal_id': state['pending']['id']})
        else:
            state = step(flow, state, 'advance', {'target': 1320})
    return step(flow, state, 'close')


def main():
    engine = Engine()
    simulator = Simulator(engine)
    rows = []
    with tempfile.TemporaryDirectory(prefix='smartfresh-month-') as directory:
        flow = Workflow(engine, simulator, Store(Path(directory) / 'audit.sqlite3'))
        state = flow.create(day='2022-05-01', seed=42, auto_run=False)
        for index in range(30):
            day = state['day']
            independent = flow.create(day=day, seed=42, apply_closed_history=False,
                                      identifier=f'independent-{day}')
            expected = simulator.evaluation_counts(day, simulator.version,state['market_context'],state['seed'])
            planned = {p['sku']: p for p in state['plan']}
            state = close_day(flow, state)
            products = state['products']
            row = dict(day=day, weekday=__import__('datetime').date.fromisoformat(day).strftime('%a'),
                       is_public_holiday=state['weather']['is_public_holiday'], model_version=state['model_version'],
                       seed=state['seed'], prepared=sum(p['prepared'] for p in products.values()),
                       sold=sum(p['sold'] for p in products.values()), waste=sum(p['stock'] for p in products.values()),
                       base_intent=sum(expected.values()),
                       independent_prepared=sum(p['prepared'] for p in independent['plan']),
                       incremental_promo_estimate=sum(p.get('incremental_promo_qty_estimated', 0) for p in products.values()),
                       stockout_skus=sum(bool(p.get('stockout_intervals') or p.get('stockout_since') is not None)
                                         for p in products.values()),
                       skus=[dict(sku=sku, prepared=p['prepared'], sold=p['sold'], waste=p['stock'],
                                  base_intent=expected.get(sku, 0), quantile=planned[sku]['quantile'],
                                  lag1=planned[sku]['features'].get('sold_calendar_lag1'),
                                  lag7=planned[sku]['features'].get('sold_calendar_lag7'))
                             for sku, p in products.items()])
            rows.append(row)
            print(f"{day} {row['weekday']} prepared={row['prepared']} sold={row['sold']} waste={row['waste']} base={row['base_intent']} independent={row['independent_prepared']}", flush=True)
            if index < 29:
                state = flow.next_day(state['id'])
        result = dict(period='2022-05-01..2022-05-30',days=30,
                      note='Generated POS V2 from past baseline; no real AEON POS, no model weight update, no future data fed to model.',
                      rows=rows)
        path = ROOT / 'docs/JOINT_MONTH_AUDIT.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('report:', path, flush=True)


if __name__ == '__main__':
    main()

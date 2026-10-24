from datetime import date, timedelta
import json
import httpx
import pandas as pd
import pytest
from services.learning import Learning, weather
from services.store import Store
from services.engine import CAPS, FLOORS, LADDER
from services.workflow import Workflow


def daily(engine, days=63):
    rows = []
    for i in range(days):
        d = date(2024, 1, 1) + timedelta(days=i)
        for sku in engine.master:
            rows.append({'date': d.isoformat(), 'sku_code': sku, 'prepared_qty': 120, 'sold_qty': 80,
                         'waste_qty': 40, 'stockout': 0, 'discounted_qty': 0, 'forecast_rain_mm_previous_day1': 2,
                         'forecast_temperature_max_c_previous_day1': 28, 'is_public_holiday': 0,
                         'is_festival_non_public': 0, 'issued_at': (d-timedelta(days=1)).isoformat()+'T18:00:00+07:00'})
    return pd.DataFrame(rows)


@pytest.fixture
def learner(engine, tmp_path):
    return Learning(Store(tmp_path/'learning.sqlite3'), engine, tmp_path/'artifacts')


def test_m2_train_evaluate_confirm_persistence_pin_and_rollback(learner, engine, simulator):
    df = daily(engine)
    raw = df.to_csv(index=False).encode()
    assert learner.ingest('outcomes.csv', raw, 'm2')['added'] == 504
    assert learner.ingest('outcomes.csv', raw, 'm2')['added'] == 0
    flow = Workflow(engine, simulator, learner.store)
    flow.active_engine, flow.version_engine = learner.active, learner.resolve
    flow.observed_history = learner.history_before
    flow.observed_outcomes = learner.outcomes_before
    old = flow.create()
    r = learner.train('m2')
    assert r['passed'] and r['status'] == 'awaiting_confirmation', r
    assert r['candidate']['mae'] < r['current']['mae']
    assert r['train_until'] < r['calibration_from'] < r['test_from'] <= r['evaluated_until']
    assert learner.active().version == engine.version
    assert learner.train('m2')['id'] == r['id']  # no repeated fishing on holdout
    with pytest.raises(ValueError, match='thay đổi'):
        learner.promote(r['id'], 'stale-parent', 'Test human confirmation')
    learner.promote(r['id'], engine.version, 'Test human confirmation')
    assert learner.active().version == r['id']
    restarted = Learning(learner.store, engine, learner.root)
    assert restarted.active().version == r['id']
    assert flow.version_engine(old['model_version']).version == engine.version
    with pytest.raises(ValueError, match='Ngày dự báo'):
        flow.create()
    new_day = '2024-03-04'
    w = weather({**df.iloc[-1].to_dict(), 'date': new_day})
    # GD5: externally supplied forecasts require an explicit availability timestamp.
    w['issued_at'] = '2024-03-03T18:00:00+07:00'
    history = {(r.date, r.sku_code): r.sold_qty for r in df.itertuples()}
    new = flow.create(day=new_day, mode='live', weather=w)
    assert new['model_version'] == r['id'] and new['plan'][0]['forecast'] == pytest.approx(80)
    # A ca created before promotion continues pricing with its original model.
    flow.mutate(old['id'], 0, 'plan_approve')
    current = flow.mutate(old['id'], 1, 'prepared')
    current['minute'] = 1170
    assert flow.proposals(current)['rows'][0]['new_price'] >= 0
    learner.rollback(r['id'], 'Test rollback')
    assert learner.active().version == engine.version
    assert learner.resolve(new['model_version']).version == r['id']


def test_demo_cannot_promote_and_censored_labels_are_excluded(learner, engine):
    df = daily(engine)
    learner.ingest('demo.csv', df.to_csv(index=False).encode(), 'm2', 'demo')
    report = learner.train('m2', 'demo')
    assert report['status'] == 'demo_only'
    with pytest.raises(ValueError, match='demo'):
        learner.promote(report['id'], engine.version, 'Attempt promotion')
    censored = df.copy()
    censored['prepared_qty'], censored['sold_qty'], censored['waste_qty'], censored['stockout'] = 80,80,0,1
    result = learner.ingest('real.csv', censored.to_csv(index=False).encode(), 'm2')
    assert result['excluded_stockout'] == len(censored)
    with pytest.raises(ValueError, match='chưa đủ'):
        learner.train('m2')
    assert learner.active().version == engine.version


def test_ingestion_is_atomic_rejects_conflicts_and_future_weather(learner, engine):
    df = daily(engine, 1)
    df.loc[1, 'waste_qty'] = 999
    with pytest.raises(ValueError, match='Đối soát'):
        learner.ingest('bad.csv', df.to_csv(index=False).encode(), 'm2')
    assert learner.rows('m2', 'real') == []
    df = daily(engine, 1)
    learner.ingest('ok.csv', df.to_csv(index=False).encode(), 'm2')
    df.loc[0, 'sold_qty'], df.loc[0, 'waste_qty'] = 70,50
    with pytest.raises(ValueError, match='xung đột'):
        learner.ingest('conflict.csv', df.to_csv(index=False).encode(), 'm2')
    df.loc[0, 'issued_at'] = '2024-01-01T12:00:00+07:00'
    with pytest.raises(ValueError, match='06:00'):
        learner.ingest('leak.csv', df.to_csv(index=False).encode(), 'm2')
    with pytest.raises(ValueError, match='63 ngày'):
        learner.train('m2')


def test_artifact_tampering_is_blocked_before_promotion(learner, engine):
    learner.ingest('real.csv', daily(engine).to_csv(index=False).encode(), 'm2')
    r = learner.train('m2')
    learner.resolve(r['id'])  # even cached previews must not bypass artifact validation
    path = learner.root / r['id'] / 'm2.txt'
    path.write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        learner.promote(r['id'], engine.version, 'Attempt promotion')
    assert learner.active().version == engine.version


def test_m1_learns_only_measured_increment_and_keeps_m2(learner, engine):
    records = []
    for base in daily(engine, 42).to_dict('records'):
        for slot in range(5):
            for tier in LADDER:
                if FLOORS[slot] <= tier <= CAPS[slot]:
                    records.append({**base, 'slot': slot, 'discount_pct': tier, 'incremental_promo_qty': 0,
                                    'measurement_method': 'controlled_increment', 'experiment_id': f'test-{slot}-{tier}'})
    df = pd.DataFrame(records)
    bad = df.iloc[:1].copy()
    bad['measurement_method'] = 'raw_sales'
    with pytest.raises(ValueError, match='controlled_increment'):
        learner.ingest('bad.csv', bad.to_csv(index=False).encode(), 'm1')
    learner.ingest('trials.csv', df.to_csv(index=False).encode(), 'm1')
    report = learner.train('m1')
    assert report['candidate']['mae'] == 0
    assert report['passed'], report
    candidate = learner.resolve(report['id'])
    assert candidate.manifest['native_model_hashes']['m2.txt'] == engine.manifest['native_model_hashes']['m2.txt']
    response = candidate.promo('BK-001', weather(records[-1]))
    assert all(response[j, LADDER.index(t)] == 0 for j in range(5) for t in LADDER if FLOORS[j] <= t <= CAPS[j])


def test_same_day_demand_does_not_leak_into_features(learner, engine):
    df = daily(engine)
    learner.ingest('real.csv', df.to_csv(index=False).encode(), 'm2')
    r = learner.train('m2')
    assert r['test_rows'] == 56 and r['training_rows'] == 112
    # New evaluation must use a wholly fresh holdout, not a sliding overlap.
    extra = daily(engine, 64).iloc[-8:]
    learner.ingest('one-new-day.csv', extra.to_csv(index=False).encode(), 'm2')
    with pytest.raises(ValueError, match='7 ngày kiểm tra mới'):
        learner.train('m2')


def test_heldout_labels_cannot_change_trained_weights_or_calibration(learner, engine, tmp_path):
    df = daily(engine)
    learner.ingest('real.csv', df.to_csv(index=False).encode(), 'm2')
    first = learner.train('m2')
    other = Learning(Store(tmp_path/'independent.sqlite3'), engine, tmp_path/'independent-models')
    df.loc[df.date >= first['test_from'], ['sold_qty', 'waste_qty']] = [90, 30]
    other.ingest('changed-test-only.csv', df.to_csv(index=False).encode(), 'm2')
    second = other.train('m2')
    a, b = learner.resolve(first['id']), other.resolve(second['id'])
    assert a.manifest['native_model_hashes'] == b.manifest['native_model_hashes']
    assert a.offsets == b.offsets
    assert second['candidate']['mae'] > first['candidate']['mae']


def test_worse_candidate_cannot_replace_incumbent(learner, engine):
    df = daily(engine)
    df.loc[df.date >= '2024-02-26', ['sold_qty', 'waste_qty']] = [20, 100]
    learner.ingest('regime-change.csv', df.to_csv(index=False).encode(), 'm2')
    report = learner.train('m2')
    assert not report['passed'] and report['status'] == 'rejected'
    with pytest.raises(ValueError, match='không đạt'):
        learner.promote(report['id'], engine.version, 'Attempt bad candidate')
    assert learner.active().version == engine.version


def test_collect_uses_closed_actuals_and_excludes_discounted_baseline(learner, engine):
    row = daily(engine, 1).iloc[0].to_dict()
    s = {'id': 'closed-test', 'day': row['date'], 'mode': 'live', 'phase': 'closed', 'minute': 1320,
         'weather': {**weather(row), 'issued_at': row['issued_at']},
         'products': {sku: {'prepared': 120, 'sold': 80, 'stock': 40, 'forecast': 999} for sku in engine.master},
         'ledger': [{'sku': sku, 'qty': 80, 'discount': 20 if sku == 'BK-001' else 0} for sku in engine.master]}
    report = learner.collect(s)
    assert report['added'] == 8 and report['excluded_discounted_days'] == 1
    learned = learner.rows('m2', 'real')
    assert all(r['sold_qty'] == 80 for r in learned)
    assert not next(r for r in learned if r['sku_code'] == 'BK-001')['eligible']
    assert learner.collect(s)['added'] == 0
    with pytest.raises(ValueError, match='Chỉ thu'):
        learner.collect({**s, 'mode': 'simulation'})

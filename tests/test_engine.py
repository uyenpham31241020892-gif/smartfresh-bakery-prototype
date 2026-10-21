"""Compare implementation with the supplied original frozen policy functions."""
import ast
import functools
import hashlib
import json
import math
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from services.engine import ROOT, SLOTS, LADDER, CAPS, FLOORS


def original(engine, weather):
    source = ROOT / 'reference/drive_v9/policy.py'
    frozen = engine.manifest['source_model_hashes']
    expected = next(v for k, v in frozen.items() if k.endswith('/policy.py'))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
    tree = ast.parse(source.read_text())
    functions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
    ns = dict(np=np, pd=pd, math=math, functools=functools, SLOTS=SLOTS, LADDER=LADDER, CAPS=CAPS,
              FLOORS=FLOORS, BATCH=4, calendar=pd.DataFrame([weather], index=['2022-08-16']),
              means=engine.means, P={s:int(r['unit_price_vnd_reference']) for s,r in engine.master.items()},
              COLS=engine.manifest['COLS'], MCOLS=engine.manifest['MCOLS'], M1COL=engine.manifest['M1COL'],
              emp=engine.emp, organic_fracs=engine.organic, residual_offsets=engine.offsets,
              m1model=SimpleNamespace(predict=lambda X:engine.m1.predict(X,num_threads=2)))
    exec(compile(functions, str(source), 'exec'), ns)
    return ns


def test_native_models_match_frozen_policy(engine, simulator):
    day='2022-08-16'
    weather=simulator.calendar[day]
    oracle=original(engine, weather)
    for scale in [.5, 1, 1.6]:
        visible={k:int(v*scale) for k,v in simulator.seed.items()}
        for plan in engine.plan(day,visible,weather):
            sku=plan['sku']
            assert plan['features'] == oracle['features'](day,sku,visible)
            X=oracle['train_encoder'](pd.DataFrame([oracle['features'](day,sku,visible)]),engine.manifest['COLS'])
            expected_forecast=max(0,float(engine.m2.predict(X,num_threads=2)[0]))
            baseline=oracle['prep_baseline'](day,sku,visible)
            expected=max(4,4*math.ceil((expected_forecast+engine.offsets[(.85,sku)])/4),4*math.ceil(.9*baseline/4))
            assert plan['forecast'] == pytest.approx(expected_forecast,abs=1e-10)
            assert plan['prepared'] == expected
            assert plan['prepared'] % 4 == 0
            # Full TreeSHAP contributions reconstruct the raw prediction.
            shap=engine.m2.predict(X,pred_contrib=True,num_threads=2)[0]
            assert shap.sum() == pytest.approx(expected_forecast,abs=1e-8)


@pytest.mark.parametrize('stock',[0,3,18,55])
def test_m1_matches_original_optimizer(engine,simulator,stock):
    weather=simulator.calendar['2022-08-16']
    oracle=original(engine,weather)
    for sku in engine.master:
        promo=oracle['expected_promo']('2022-08-16',sku)
        np.testing.assert_allclose(engine.promo(sku,weather),promo,atol=1e-10)
        previous=0
        for j,t in enumerate(SLOTS):
            actual=engine.price(sku,j,stock,60,previous,2,5,48.5,weather)
            expected,_=oracle['price_optimizer'](t,j,sku,stock,60,previous,2,5,60-stock,48.5,promo,engine.organic)
            assert actual['discount'] == expected
            assert max(previous,FLOORS[j]) <= actual['discount'] <= CAPS[j]
            assert actual['discount'] in LADDER
            assert actual['new_price'] == round(actual['price']*(1-actual['discount']/100))
            previous=actual['discount']


def test_future_history_does_not_change_prediction(engine,simulator):
    day='2022-08-16'
    past=dict(simulator.seed)
    a=engine.plan(day,past,simulator.calendar[day])
    for sku in engine.master:
        past[(day,sku)] = 999999
        past[('2022-09-30',sku)] = 999999
    assert engine.plan(day,past,simulator.calendar[day]) == a


def test_seeds_repeat_without_mutating_model(simulator,engine):
    before=dict(engine.manifest['native_model_hashes'])
    a=simulator.events('2022-08-16',42)
    assert a == simulator.events('2022-08-16',42)
    assert a != simulator.events('2022-08-16',43)
    for n,h in before.items():
        assert hashlib.sha256((ROOT/'models'/n).read_bytes()).hexdigest() == h

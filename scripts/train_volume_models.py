"""Refit the user-selected V4 architecture in x10 units; never overwrite V4.

Only TRAINED_TESTED fit files enter fitting. Validation is retrospective and
reported separately. Scaling increases volume, not independent sample count.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys

os.environ.setdefault('OMP_NUM_THREADS', '2')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from services.volume_scenario import SCALE, MODEL_VERSION, QUANTITY_FIELDS, scaled

SOURCE = ROOT / 'TRAINED_TESTED'
DEST = ROOT / 'models/joint'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scale_matrix(x, prep, m1=False):
    out = x.copy()
    offset = len(prep.sku_list) + len(prep.event_list) + (2 if m1 else 0)
    for i, key in enumerate(prep.numeric_cols):
        if key in QUANTITY_FIELDS:
            out[:, offset + i] *= SCALE
    out[:, -3] *= SCALE  # capacity, followed by unscaled lead time and unit cost
    return out


def validation(prep, lookup, kind):
    folder = SOURCE / '02_TRAIN_VALIDATION/validation'
    if kind == 'm2':
        a = pd.read_csv(folder / 'm2_morning_features.csv')
        b = pd.read_csv(folder / 'm2_censor_aware_targets.csv')
        b = b[b.target_horizon == 'day']
        frame = a.merge(b, on=['date', 'sku_code'], suffixes=('', '_label'), validate='one_to_one')
        x = np.array([prep.transform_row(r, r['sku_code'], lookup[r['sku_code']]) for r in frame.to_dict('records')])
        y = frame.served_sales_lower_bound.to_numpy(float)
    else:
        a = pd.read_csv(folder / 'm1_checkpoint_features.csv')
        b = pd.read_csv(folder / 'm1_logged_actions_TREATMENT_ONLY.csv')
        c = pd.read_csv(folder / 'm1_outcomes_LABELS_ONLY.csv')
        frame = a.merge(b, on='sample_id', suffixes=('', '_action'), validate='one_to_one').merge(c, on='sample_id', validate='one_to_one')
        action = next(k for k in ['action_discount_pct', 'logged_action_discount_pct', 'requested_discount_pct', 'discount_pct'] if k in frame)
        x = np.array([prep.transform_row(r, r[action], r['sku_code'], lookup[r['sku_code']]) for r in frame.to_dict('records')])
        y = frame.sold_next30_observed.to_numpy(float)
    return x, y, frame


def main():
    # Resolve the exact user-selected preprocessor, never a legacy sys.modules alias.
    selected_adapter=SOURCE/'agent_sandbox/smartfresh_adapter.py'
    adapter_spec=importlib.util.spec_from_file_location('smartfresh_adapter',selected_adapter)
    adapter=importlib.util.module_from_spec(adapter_spec)
    sys.modules['smartfresh_adapter']=adapter
    adapter_spec.loader.exec_module(adapter)
    spec = importlib.util.spec_from_file_location('volume_training_source', SOURCE / 'train_v4_original_pipeline.py')
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    # The source target file also contains to-21:30 and late-evening horizons.
    # M2 predicts the day: never join those shorter labels onto morning rows.
    original_read_csv = pd.read_csv
    class TrainingPandas:
        def __getattr__(self, name):return getattr(pd, name)
        def read_csv(self, path, *args, **kwargs):
            frame = original_read_csv(path, *args, **kwargs)
            return frame[frame.target_horizon == 'day'] if Path(path).name == 'm2_censor_aware_targets.csv' else frame
    pipeline.pd = TrainingPandas()
    lookup = pipeline.build_operational_lookup()
    x2, raw, target, w2, p2 = pipeline.load_all_m2_data(lookup)
    x1, y1, w1, p1, support = pipeline.load_all_m1_data(lookup)
    if not len(x1) or not len(x2):
        raise ValueError('Missing selected V4 fit data')
    from scripts.joint_training_data import build
    z2 = scale_matrix(x2, p2)
    scaled_lookup={k:scaled(v) for k,v in lookup.items()}
    z1,y1,pos_fit=build(ROOT,p1,scaled_lookup)
    v1,vy1,pos_validation=build(ROOT,p1,scaled_lookup,validation=True)
    w1=np.ones(len(y1));x1=z1.copy()
    print(f'Fit only: M2 {len(x2)} rows; M1 {len(x1)} rows. Quantities x10.', flush=True)
    mono2, mono1 = [0] * z2.shape[1], [0] * z1.shape[1]
    mono2[-3], mono2[-1], mono1[13] = 1, -1, 1
    # Quantile loss alone does not uncensor observed sales. Preserve them as
    # lower bounds, using an uncensored-fit Q75 estimate for censored rows.
    censored2=target>raw
    recovery=HistGradientBoostingRegressor(loss='quantile',quantile=.75,max_iter=180,
        max_depth=4,min_samples_leaf=20,learning_rate=.05,random_state=pipeline.SEED,
        early_stopping=False).fit(z2[~censored2],raw[~censored2]*SCALE,sample_weight=w2[~censored2])
    target=np.where(censored2,np.maximum(raw,recovery.predict(z2)/SCALE),raw)
    w2=np.where(censored2,w2*.5,w2)
    m2 = {'preprocessor': p2}
    for name, quantile, depth, iterations, leaf, l2, target_y, seed in [
        ('model', .50, 5, 220, 20, 1.5, target, 0),
        ('model_q10', .10, 4, 180, 25, 2., raw, 1),
        ('model_q25', .25, 4, 180, 25, 2., raw, 2),
        ('model_q45', .45, 5, 220, 20, 1.5, target, 5),
        ('model_q75', .75, 5, 200, 20, 1.5, target, 3),
        ('model_q90', .90, 5, 200, 20, 1.5, target, 4),
    ]:
        m2[name] = pipeline.strip_rng_for_portability(HistGradientBoostingRegressor(
            loss='quantile', quantile=quantile, max_depth=depth, max_iter=iterations,
            learning_rate=.05, min_samples_leaf=leaf, l2_regularization=l2,
            early_stopping=False,
            monotonic_cst=mono2, random_state=pipeline.SEED + seed,
        ).fit(z2, target_y * SCALE, sample_weight=w2))
        print('Fitted M2 ' + name, flush=True)
    support={}
    for sku_index,sku in enumerate(p1.sku_list):
        for tier in sorted(set(pos_fit['actions'])):
            mask=(z1[:,sku_index]==1)&(z1[:,13]==tier)
            if mask.any():support[f'{sku}|{tier}']=dict(count=int(mask.sum()),mean_sales_next30=float(y1[mask].mean()))
    m1 = {'preprocessor': p1, 'action_support': support}
    for name, loss, depth, iterations, l2, seed in [('model', 'squared_error', 5, 220, 2.5, 10), ('model_q25', 'quantile', 4, 180, 2.5, 11)]:
        m1[name] = pipeline.strip_rng_for_portability(HistGradientBoostingRegressor(
            loss=loss, quantile=.25 if loss == 'quantile' else None, max_depth=depth,
            max_iter=iterations, learning_rate=.05, min_samples_leaf=30,
            early_stopping=False,
            l2_regularization=l2, monotonic_cst=mono1, random_state=pipeline.SEED + seed,
        ).fit(z1, y1, sample_weight=w1))
        print('Fitted M1 ' + name, flush=True)
    metrics = {}
    for kind, bundle, prep in [('m2', m2, p2), ('m1', m1, p1)]:
        if kind=='m1':
            x,y,frame=v1,vy1/SCALE,pd.DataFrame({'date':pos_validation['dates']})
            prediction=bundle['model'].predict(x)
        else:
            x, y, frame = validation(prep, lookup, kind)
            prediction = bundle['model'].predict(scale_matrix(x, prep))
        # Compare against a train-only per-SKU observed mean, not leaked labels.
        tx, ty = (x2, raw) if kind == 'm2' else (x1, y1/SCALE)
        means = np.array([ty[tx[:, j] == 1].mean() * SCALE for j in range(len(prep.sku_list))])
        baseline = means[np.argmax(x[:, :len(means)], axis=1)]
        metrics[kind] = dict(rows=len(y), mae=float(np.abs(prediction - y*SCALE).mean()),
            sku_mean_mae=float(np.abs(baseline - y*SCALE).mean()),
            finite=bool(np.isfinite(prediction).all()), from_date=str(frame.date.min()), through=str(frame.date.max()))
    passed = all(v['finite'] and v['mae'] <= v['sku_mean_mae'] for v in metrics.values())
    source_files = sorted({p for d in [SOURCE/'02_TRAIN_VALIDATION/fit', SOURCE/'SmartFresh_V610_01_TRAIN_AUGMENTATION/01_TRAIN_AUGMENTATION/fit'] for p in d.rglob('*.csv')})
    sources = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in source_files}
    selected = SOURCE/'agent_sandbox/smartfresh_adapter.py'
    sources[str(selected.relative_to(ROOT)).replace('\\', '/')] = sha(selected)
    for p in [SOURCE/'train_v4_original_pipeline.py', Path(__file__), ROOT/'services/volume_scenario.py',ROOT/'services/joint_policy.py',ROOT/'scripts/joint_training_data.py',ROOT/pos_fit['source']]:
        sources[str(p.relative_to(ROOT)).replace('\\', '/')] = sha(p)
    report = dict(version=MODEL_VERSION, scale=SCALE, parent='SMARTFRESH_V4_LOCKED',
        adapter_source='TRAINED_TESTED/agent_sandbox/smartfresh_adapter.py', adapter_sha256=sha(selected),
        training_pipeline='TRAINED_TESTED/train_v4_original_pipeline.py',
        trained_until='2022-04-30', validation_through='2022-06-30', evaluated_until='2022-06-30',
        evaluation_protocol='RETROSPECTIVE_SCALED_VALIDATION_NOT_BLIND_HOLDOUT',
        training_rows={'m2':len(x2), 'm1':len(x1)}, validation=metrics, passed=passed,
        m1_pos_fit={k:v for k,v in pos_fit.items() if k not in ('dates','actions','censored')},
        m1_pos_validation={k:v for k,v in pos_validation.items() if k not in ('dates','actions','censored')},
        quantile_levels={'model':.50,'model_q10':.10,'model_q25':.25,'model_q45':.45,'model_q75':.75,'model_q90':.90},
        censoring_method='Observed sales remain lower bounds; uncensored-fit Q75 imputation with half weight, not identified true demand',
        censored_m2_rows=int(censored2.sum()),
        limitations='Synthetic x10 units; no increase in independent days. New intraday profile is a user assumption, not AEON measurement. No claim of improved real-store accuracy or profit.',
        source_sha256=sources)
    DEST.mkdir(parents=True, exist_ok=True)
    for kind, bundle, name in [('m1', m1, 'm1_pricing_q_bundle.joblib'), ('m2', m2, 'm2_forecast_bundle.joblib')]:
        bundle['metadata'] = dict(version=MODEL_VERSION, scale=SCALE, fit_samples=report['training_rows'][kind])
        joblib.dump(bundle, DEST/name)
    (DEST/'operational_lookup.json').write_text(json.dumps({k:scaled(v) for k,v in lookup.items()}, indent=2, ensure_ascii=False), encoding='utf-8')
    from services.joint_policy import POLICY
    (DEST/'policy_config.json').write_text(json.dumps(POLICY,indent=2),encoding='utf-8')
    report['artifact_sha256'] = {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(DEST.iterdir()) if p.name != 'manifest.json' and p.is_file()}
    (DEST/'manifest.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256', 'artifact_sha256')}, indent=2))
    if not passed:
        raise SystemExit('Validation failed: candidate must not be loaded.')


if __name__ == '__main__':
    main()

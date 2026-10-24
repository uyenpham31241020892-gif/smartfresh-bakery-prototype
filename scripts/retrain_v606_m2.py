"""Bounded M2 development using ZIP 02 only. No runtime, SQLite or private inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def frame(data, columns):
    result=data[columns].copy()
    for col in result:
        if result[col].dtype=='object':
            numeric=pd.to_numeric(result[col],errors='coerce')
            if numeric.notna().sum() and numeric.notna().sum()>=.95*result[col].notna().sum():result[col]=numeric
    return result


def loss(pred,y,censored):
    e=pred-y
    return float(np.mean(np.where(censored,np.minimum(e,0)**2,e**2)))


def metrics(pred,data):
    y=data.served_sales_lower_bound.to_numpy(float);c=data.demand_right_censored.to_numpy(bool)
    return dict(censor_aware_loss=loss(pred,y,c),uncensored_mae=float(np.abs(pred[~c]-y[~c]).mean()),
                censored_underforecast_rate=float((pred[c]<y[c]).mean()),mean_prediction=float(pred.mean()))


def load(root,split,horizon):
    x=pd.read_csv(root/split/'m2_morning_features.csv')
    y=pd.read_csv(root/split/'m2_censor_aware_targets.csv')
    y=y[y.target_horizon==horizon]
    data=x.merge(y,on=['date','sku_code'],validate='one_to_one')
    assert len(data)==len(x)
    assert (data.history_through<data.date).all() and (data.weather_reference_date<data.date).all()
    assert (pd.to_datetime(data.label_available_at)>pd.to_datetime(data.decision_at)).all()
    assert data.date.max()<='2022-06-30'
    return data


def train(a,data,config):
    y=data.served_sales_lower_bound.to_numpy(float);c=data.demand_right_censored.to_numpy(bool)
    def objective(pred,dm):
        e=pred-dm.get_label();active=(~c)|(e<0)
        q=config.get('underweight',.5);weights=np.where(e<0,2*q,2*(1-q))
        return (2*e*active*weights).astype(float),2*active.astype(float)*weights+1e-6
    return xgb.train(dict(max_depth=config['depth'],eta=config['eta'],min_child_weight=8,subsample=1,
        colsample_bytree=1,seed=606,nthread=2,tree_method='hist',base_score=float(np.median(y))),
        xgb.DMatrix(a,label=y),num_boost_round=config['rounds'],obj=objective)


def main(root,out):
    assert root.name=='02_TRAIN_VALIDATION'
    sources=json.loads((root/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name,expected in sources.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('Training source checksum mismatch: '+name)
    contract=json.loads((root/'feature_contract.json').read_text(encoding='utf-8'))
    columns=contract['m2_predictive_columns']
    tr=load(root,'fit','day');va=load(root,'validation','day')
    assert tr.date.max()<va.date.min()
    x=frame(tr,columns);v=frame(va,columns)
    cat=[c for c in columns if x[c].dtype=='object'];num=[c for c in columns if c not in cat]
    pre=ColumnTransformer([('num',SimpleImputer(strategy='median'),num),('cat',Pipeline([
        ('impute',SimpleImputer(strategy='most_frequent')),('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),cat)],sparse_threshold=0)
    a=pre.fit_transform(x).astype(float);b=pre.transform(v).astype(float)
    out.mkdir(parents=True,exist_ok=True)
    report=dict(scope='ZIP02_FIT_VALIDATION_DEVELOPMENT_ONLY',selection='validation_not_independent_holdout',
        train_from=tr.date.min(),fit_through=tr.date.max(),validation_from=va.date.min(),trained_until='2022-06-30',
        fit_rows=len(tr),validation_rows=len(va),features=columns,input_sha256=sources,
        max_candidates_per_horizon=32,refit='DEVELOPMENT_CANDIDATE_ONLY; deployment uses fit-only selected artifact',no_july_august_training=True,
        limitations=['Censored targets are lower bounds, not complete demand.',
                    'Weather is retrospective previous-day reanalysis, not an issued same-day forecast.',
                    'Busy-store scaling and service buffer are declared scenario policies, not learned AEON demand.',
                    'Past simulation days already inspected are development data, not a fresh blind holdout.'],horizons={})
    selected={}
    for horizon in ('day','to_2130'):
        ht=load(root,'fit',horizon);hv=load(root,'validation',horizon);choices=[]
        for depth in (2,3):
            for eta in (.03,.055):
                for rounds in (50,75,120,200,320):
                    config=dict(depth=depth,eta=eta,rounds=rounds)
                    model=train(a,ht,config);pred=np.maximum(0,model.predict(xgb.DMatrix(b)))
                    score=metrics(pred,hv);choices.append(dict(config=config,metrics=score))
        for q in (.6,.7,.8):
            for depth in (2,3):
                for rounds in (75,160):
                    config=dict(depth=depth,eta=.055,rounds=rounds,underweight=q)
                    model=train(a,ht,config);pred=np.maximum(0,model.predict(xgb.DMatrix(b)))
                    choices.append(dict(config=config,metrics=metrics(pred,hv)))
        choices.sort(key=lambda r:r['metrics']['censor_aware_loss'])
        original_config=dict(depth=2,eta=.055,rounds=75)
        original=train(a,ht,original_config);oldpred=np.maximum(0,original.predict(xgb.DMatrix(b)))
        oldmetrics=metrics(oldpred,hv)
        eligible=[c for c in choices if c['metrics']['censor_aware_loss']<oldmetrics['censor_aware_loss'] and
            c['metrics']['censored_underforecast_rate']<=oldmetrics['censored_underforecast_rate'] and
            c['metrics']['uncensored_mae']<=oldmetrics['uncensored_mae']]
        best=eligible[0] if eligible else choices[0]
        model=train(a,ht,best['config']);pred=np.maximum(0,model.predict(xgb.DMatrix(b)))
        model.save_model(out/('M2_'+horizon+'_validated_fit.json'))
        joblib.dump(pre,out/'M2_preprocessor_validated_fit.joblib')
        diagnostics={}
        # Permutation sensitivity is diagnostic only; it is not causal weather evidence.
        rng=np.random.default_rng(606)
        for group,cols in {'weather':['prior_day_rain_mm','prior_day_temp_c'],
            'history':['sold_calendar_lag1','sold_calendar_lag7','sold_last7_observed_mean','prepared_last_observed']}.items():
            permuted=v.copy();idx=rng.permutation(len(v))
            for col in cols:permuted[col]=v[col].to_numpy()[idx]
            pp=np.maximum(0,model.predict(xgb.DMatrix(pre.transform(permuted).astype(float))))
            diagnostics[group]=dict(permuted_metrics=metrics(pp,hv),mean_absolute_prediction_change=float(np.abs(pp-pred).mean()))
        # Save challenger evidence separately; runtime never auto-promotes these artifacts.
        selected[horizon]=best['config']
        accepted=bool(eligible)
        hreport=dict(selected=best,original_reproduced=oldmetrics,candidates=choices,
            lowest_loss_unconstrained=choices[0],promotion_eligible=accepted,
            promotion_gate='Strictly lower validation censor-aware loss AND no higher censored underforecast rate AND no higher uncensored MAE',
            sensitivity=diagnostics,validation_uncensored_positive_error_q90=float(max(0,np.quantile(
                hv.loc[hv.demand_right_censored==0,'served_sales_lower_bound'].to_numpy()-pred[hv.demand_right_censored.to_numpy()==0],.90))))
        report['horizons'][horizon]=hreport
        print(json.dumps(dict(horizon=horizon,best=best,original=hreport['original_reproduced'],sensitivity=diagnostics)),flush=True)
    report['promoted']=False
    report['deployment']='NOT_PROMOTED; retained original frozen artifacts. Candidate refits below are development-only.'
    # Candidate refit sees Jan-Jun only. Never loaded by the operating prototype.
    both=pd.concat([tr,va],ignore_index=True);pre.fit(frame(both,columns));allx=pre.transform(frame(both,columns)).astype(float)
    joblib.dump(pre,out/'M2_preprocessor.joblib')
    for horizon in selected:
        labels=pd.concat([load(root,'fit',horizon),load(root,'validation',horizon)],ignore_index=True)
        train(allx,labels,selected[horizon]).save_model(out/('M2_'+horizon+'.json'))
    (out/'feature_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
    (out/'training_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    artifact_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
    (out/'SHA256SUMS.json').write_text(json.dumps(artifact_hashes,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--train-dir',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();main(args.train_dir.resolve(),args.out.resolve())

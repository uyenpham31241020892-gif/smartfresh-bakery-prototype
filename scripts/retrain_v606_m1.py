"""Train remaining observed sales, never pretend logged prices identify elasticity.

Only the checksummed ZIP 02 directory is read. Future intervals are labels, never X.
Validation selects tree size; original artifacts and July/August stay untouched.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
import xgboost as xgb

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v606/V606_M1_remaining_v7'


def dataset(root, split, columns):
    x=pd.read_csv(root/split/'m1_checkpoint_features.csv')
    z=pd.read_csv(root/split/'observed_15min.csv')
    upper='2022-04-30' if split=='fit' else '2022-06-30'
    lower='2022-01-02' if split=='fit' else '2022-05-01'
    assert x.date.between(lower,upper).all() and z.date.between(lower,upper).all()
    assert not x.duplicated(['date','sku_code','time']).any()
    groups={k:v for k,v in z.groupby(['date','sku_code'])}
    targets=[];censors=[]
    for r in x.itertuples():
        future=groups[(r.date,r.sku_code)]
        future=future[future.time>=r.time]
        assert (pd.to_datetime(future.available_at)>pd.Timestamp(r.decision_at)).all()
        targets.append([future.sold_qty.sum(),future.loc[future.time<'21:30','sold_qty'].sum()])
        censors.append([bool(future.observed_censored_interval_flag.any()),
                        bool(future.loc[future.time<'21:30','observed_censored_interval_flag'].any())])
    return x[columns].copy(),np.asarray(targets,float),np.asarray(censors,bool)


def run(root, out=OUT):
    hashes=json.loads((root/'SHA256SUMS.json').read_text(encoding='utf-8-sig'))
    for name,expected in hashes.items():
        p=(root/name).resolve()
        assert p.is_relative_to(root.resolve()),'Source path escaped ZIP 02'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
    columns=json.loads((root/'feature_contract.json').read_text())['m1_pre_action_columns']
    a,y,c=dataset(root,'fit',columns);b,v,cv=dataset(root,'validation',columns)
    cat=['sku_code','time'];num=[k for k in columns if k not in cat]
    pre=ColumnTransformer([('num',SimpleImputer(strategy='constant',fill_value=0,keep_empty_features=True),num),
                          ('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),cat)],sparse_threshold=0)
    A=pre.fit_transform(a);B=pre.transform(b)
    report=dict(scope='ZIP02_FIT_VALIDATION_ONLY',fit_rows=len(a),validation_rows=len(b),trained_until='2022-04-30',
                selected_on='2022-05-01/2022-06-30',test_access=False,columns=columns,
                labels='Future observed sales under historical logged actions; censored = lower bound',
                causal_price_response_learned=False,source_hashes=hashes,horizons={})
    selected={}
    for j,name in enumerate(['close','to2130']):
        choices=[];dt=xgb.DMatrix(A,label=y[:,j]);dv=xgb.DMatrix(B)
        def objective(pred,dm):
            e=pred-dm.get_label();active=(~c[:,j])|(e<0)
            return 2*e*active,2*active.astype(float)+1e-6
        for depth in [2,3]:
            for rounds in [60,120]:
                model=xgb.train(dict(max_depth=depth,eta=.05,min_child_weight=12,seed=607,nthread=2,
                    tree_method='hist',base_score=float(np.mean(y[:,j]))),dt,rounds,obj=objective)
                pred=np.maximum(0,model.predict(dv));e=pred-v[:,j]
                loss=float(np.mean(np.where(cv[:,j],np.minimum(e,0)**2,e**2)))
                exact=~cv[:,j]
                choices.append((loss,depth,rounds,model,float(np.mean(abs(e[exact])))))
        best=min(choices,key=lambda t:t[0]);selected[name]=best[3]
        minutes=b.time.map(lambda t:int(t[:2])*60+int(t[3:]))
        pace=np.maximum(b.sold_last_30min/30,b.sold_last_60min/60)
        naive=pace*np.maximum(0,(1320 if j==0 else 1290)-minutes);error=naive-v[:,j]
        report['horizons'][name]=dict(selected_depth=best[1],selected_rounds=best[2],validation_censored_loss=best[0],
            validation_uncensored_mae=best[4],validation_exact_rows=int((~cv[:,j]).sum()),
            pace_baseline_censored_loss=float(np.mean(np.where(cv[:,j],np.minimum(error,0)**2,error**2))),
            pace_baseline_uncensored_mae=float(np.mean(abs(error[~cv[:,j]]))),
            candidates=[dict(loss=t[0],depth=t[1],rounds=t[2],uncensored_mae=t[4]) for t in choices])
    out.mkdir(parents=True,exist_ok=True)
    joblib.dump(dict(preprocessor=pre,columns=columns),out/'preprocessor.joblib')
    for name,model in selected.items():model.save_model(out/(name+'.json'))
    report['artifact_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.name in ['preprocessor.joblib','close.json','to2130.json']}
    (out/'training_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args();run(args.source)

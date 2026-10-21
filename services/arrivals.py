"""Independent, trained count model for synthetic customer arrivals (not a POS feed)."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
from .engine import DATA, ROOT


def design(rows, skus):
    result=[]
    for r in rows:
        d=pd.Timestamp(r['date'])
        result.append([float(r['rain']),float(r['temp'])] + [int(d.dayofweek==j) for j in range(7)] + [int(r['sku']==s) for s in skus])
    return np.asarray(result,dtype=float)


def train(directory=None):
    from sklearn.linear_model import PoissonRegressor
    directory=Path(directory or ROOT/'models/arrivals')
    data=pd.read_csv(DATA/'M2_TRAIN_JUN_AUG.csv')
    calendar=pd.read_csv(DATA/'weather_forecast_feed_2022.csv').set_index('date')
    logs=pd.read_csv(DATA/'M1_Policy_Label_Train.csv')
    source=json.loads((ROOT/'models/manifest.json').read_text(encoding='utf-8'))
    skus=sorted(data.sku_code.unique())
    rows=[{'date':r.date,'sku':r.sku_code,'rain':calendar.loc[r.date,'forecast_rain_mm_previous_day1'],
           'temp':calendar.loc[r.date,'forecast_temperature_max_c_previous_day1']} for r in data.itertuples()]
    dates=sorted(data.date.unique());cal_start,test_start=dates[-28],dates[-14]
    masks=[data.date<cal_start,(data.date>=cal_start)&(data.date<test_start),data.date>=test_start]
    X=design(rows,skus);y=data.target_base_demand_SIMULATOR_ONLY.to_numpy(float)
    center=X[masks[0]].mean(axis=0);scale=X[masks[0]].std(axis=0);scale[scale==0]=1
    Z=(X-center)/scale
    candidates=[]
    for alpha in [.1,1.,10.]:
        model=PoissonRegressor(alpha=alpha,max_iter=1000).fit(Z[masks[0]],y[masks[0]])
        mae=float(np.abs(model.predict(Z[masks[1]])-y[masks[1]]).mean())
        candidates.append((mae,alpha,model))
    _,alpha,model=min(candidates,key=lambda x:x[0])
    train_rows=data[masks[0]]
    means=train_rows.groupby('sku_code').target_base_demand_SIMULATOR_ONLY.mean().to_dict()
    # August 2–15 was inspected during development; final untouched evaluation is August 16–31.
    holdout=pd.read_csv(DATA/'M2_VALIDATION_AUG16_31.csv')
    test_rows=[{'date':r.date,'sku':r.sku_code,'rain':calendar.loc[r.date,'forecast_rain_mm_previous_day1'],
                'temp':calendar.loc[r.date,'forecast_temperature_max_c_previous_day1']} for r in holdout.itertuples()]
    baseline=np.array([means[s] for s in holdout.sku_code])
    prediction=model.predict((design(test_rows,skus)-center)/scale)
    test_y=holdout.target_base_demand_SIMULATOR_ONLY.to_numpy(float)
    residual=y[masks[1]]-model.predict(Z[masks[1]])
    noise={}
    for sku in skus:
        values=residual[data[masks[1]].sku_code.to_numpy()==sku]
        noise[sku]=(values-values.mean()).tolist()
    profile={}
    for sku in skus:
        first=logs[(logs.sku_code==sku)&(logs.time_19_30==1)&(logs.date<cal_start)]
        n=float(train_rows[train_rows.sku_code==sku].target_base_demand_SIMULATOR_ONLY.sum())
        late=[float(next(r['value'] for r in source['organic_fracs'] if r['key']==[sku,j])) for j in range(5)]
        last30=float(first.sales_last30.sum())/max(n,1)
        prior30=float((first.sales_last60-first.sales_last30).clip(lower=0).sum())/max(n,1)
        probabilities=np.array([max(0.,1-sum(late)-last30-prior30),prior30,last30]+late)
        profile[sku]=(probabilities/probabilities.sum()).tolist()
    report={'version':'trained-arrivals-v2','type':'Poisson mean + calibrated discrete residual sampler','alpha':alpha,'training_rows':int(masks[0].sum()),
            'train_until':max(data[masks[0]].date),'validation_from':cal_start,'calibrated_until':max(data[masks[1]].date),'test_from':min(holdout.date),
            'evaluated_until':max(holdout.date), 'test_rows':len(holdout),
            'test_mae':float(np.abs(prediction-test_y).mean()),
            'sku_mean_baseline_mae':float(np.abs(baseline-test_y).mean()),
            'passed':bool(np.abs(prediction-test_y).mean()<=np.abs(baseline-test_y).mean()),
            'validation_candidates':[{'alpha':a,'mae':m} for m,a,_ in candidates],
            'source':'V9 synthetic TRAIN only; not observed AEON transactions',
            'timing':'Last 30/60 minute shares fitted from pre-test V9 training labels; early-day shape assumed; late shares and promo uplift inherited from frozen V9 calibration.',
            'limitations':'No original intraday arrival observations in ZIP. This does not establish real-store realism or validate M1/M2 profit.',
            'input_sha256':{n:hashlib.sha256((DATA/n).read_bytes()).hexdigest() for n in ['M2_TRAIN_JUN_AUG.csv','M2_VALIDATION_AUG16_31.csv','M1_Policy_Label_Train.csv','weather_forecast_feed_2022.csv']}}
    artifact={**report,'skus':skus,'center':center.tolist(),'scale':scale.tolist(),'coef':model.coef_.tolist(),
              'intercept':float(model.intercept_),'means':means,'profiles':profile,'noise':noise,
              'daily_caps':{s:float(train_rows[train_rows.sku_code==s].target_base_demand_SIMULATOR_ONLY.max()*1.5) for s in skus},
              'promo':source['emp']}
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'model.json').write_text(json.dumps(artifact,indent=2),encoding='utf-8')
    return report


class Arrivals:
    def __init__(self,path=None):
        self.path=Path(path or ROOT/'models/arrivals/model.json')
        if not self.path.exists():
            train(self.path.parent)
        self.model=json.loads(self.path.read_text(encoding='utf-8'))
        self.version=self.model['version']
        self.hash=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.promo={tuple(r['key']):r['value'] for r in self.model['promo']}

    def mean(self,day,sku,weather):
        row={'date':day,'sku':sku,'rain':weather['forecast_rain_mm_previous_day1'],
             'temp':weather['forecast_temperature_max_c_previous_day1']}
        x=design([row],self.model['skus'])[0]
        z=(x-np.array(self.model['center']))/np.array(self.model['scale'])
        mu=float(np.exp(np.clip(z@np.array(self.model['coef'])+self.model['intercept'],-10,10)))
        return min(self.model['daily_caps'][sku],max(.25,mu if self.model['passed'] else self.model['means'][sku]))

    def report(self):
        return {k:v for k,v in self.model.items() if k not in ['center','scale','coef','intercept','promo','profiles','means','daily_caps','noise'] }|{'sha256':self.hash}

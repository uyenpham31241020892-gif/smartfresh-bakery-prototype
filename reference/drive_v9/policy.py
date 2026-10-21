"""Frozen inference; JSON observations only. No holdout labels read here."""
from pathlib import Path
import json,sys,math,functools
import numpy as np,pandas as pd,joblib
ROOT=Path(__file__).resolve().parent
r=joblib.load(ROOT/'models/runtime.joblib');globals().update(r)
m1model=joblib.load(ROOT/'models/M1_Price_Response_LightGBM.joblib')
m2final=joblib.load(ROOT/'models/M2_JMA_LightGBM.joblib')
SLOTS=[1170,1200,1230,1260,1290]
calendar=pd.DataFrame();LADDER=[0,20,25,30,35,40,45,50];CAPS=[20,25,35,45,50];FLOORS=[0,0,0,30,30];BATCH=4
def wday(d):return pd.Timestamp(d).weekday()

def features(d,s,visible):
    day=pd.Timestamp(d);c=calendar.loc[d]; hist=[]
    for k in range(1,36):
        dd=str((day-pd.Timedelta(days=k)).date())
        if (dd,s) in visible:hist.append(float(visible[(dd,s)]))
        else:break
    arr=np.asarray(hist,dtype=float);m=means[s]
    def lag(k):return float(arr[k-1]) if len(arr)>=k else m
    def rav(k):return float(arr[:k].mean()) if len(arr) else m
    return {'sku_code':s,'weekday':c.weekday_iso,'is_weekend':c.is_weekend,'is_holiday':c.is_public_holiday,
     'festival_nonpublic':c.is_festival_non_public,'month':c.month,'dayofyear':c.day_of_year,
     'weekday_sin':math.sin(2*math.pi*c.weekday_iso/7),'weekday_cos':math.cos(2*math.pi*c.weekday_iso/7),
     'rain_forecast_proxy':c.forecast_rain_mm_previous_day1,'temp_forecast_jma':c.forecast_temperature_max_c_previous_day1,
     'calendar_month_trend':c.month-6,'lag1_sales':lag(1),'lag7_sales':lag(7),
     'rolling7_sales':rav(7),'rolling14_sales':rav(14),'rolling7_std':float(arr[:7].std()) if len(arr)>1 else .11*m,
     'history_days':len(arr),'ref_mean_train_only':m}

def train_encoder(frame,cols=None):
    X=pd.get_dummies(frame,columns=['sku_code'],dtype=float).astype(float)
    return X if cols is None else X.reindex(columns=cols,fill_value=0.)

def base_discount(t,j,s,stock,p,prev,s30,s60,base_sold,f,pred,organic):return (30 if t>=1260 else 0),'AS_IS_FIXED_21H_30PCT'

def prep_baseline(d,s,visible,buffer=.29):
    day=pd.Timestamp(d);lst=[]
    for k in range(1,8):
        dd=str((day-pd.Timedelta(days=k)).date())
        if (dd,s) in visible:lst.append(float(visible[(dd,s)]))
    mu=float(np.mean(lst)) if lst else means[s]
    return max(4,int(BATCH*math.ceil(mu*(1+buffer)*(1.07 if wday(d)>=5 else 1)/BATCH)))

@functools.lru_cache(None)
def schedules(start,previous):
    possibilities=[]
    def rec(j,prev,path):
        if j==5: possibilities.append(tuple(path));return
        for v in LADDER:
            if prev<=v and FLOORS[j]<=v<=CAPS[j]: rec(j+1,v,path+[v])
    rec(start,previous,[])
    return np.array(possibilities,dtype=np.int16)

@functools.lru_cache(maxsize=4000)
def expected_promo(d,s):
    c=calendar.loc[d];entries=[]
    for j,t in enumerate(SLOTS):
        for tier in LADDER:
            entries.append({'slot':j,'discount_pct':tier,'weekday':c.weekday_iso,'is_weekend':c.is_weekend,
             'is_holiday':c.is_public_holiday,'rain_jma':c.forecast_rain_mm_previous_day1,
             'temp_jma':c.forecast_temperature_max_c_previous_day1,'sku_code':s})
    X=train_encoder(pd.DataFrame(entries)[M1COL],MCOLS)
    fit=m1model.predict(X).reshape(5,len(LADDER));fallback=np.array([[emp.get((s,j,tier),0) for tier in LADDER] for j in range(5)])
    estimates=np.maximum(0,.35*fit+.65*fallback)
    estimates=np.maximum.accumulate(estimates,axis=1)
    estimates[:,0]=0 # no discount, no price-sensitive candidate buys (synthetic generator)
    return estimates

def price_optimizer(t,j,s,stock,prepared,prev,s30,s60,base_sold,fcast,promo,frac):
    if stock<=0:return max(prev,FLOORS[j]),'OUT_OF_STOCK_MAINTAIN_PUBLIC_FLOOR'
    if promo is None:promo=expected_promo('__invalid__',s) # should not occur
    sched=schedules(j,prev)
    predicted_total=max(float(fcast or means[s]),float(base_sold))
    base_arr=np.array([predicted_total*organic_fracs[(s,k)] for k in range(j,5)],dtype=float)
    # Preserve a little of observed momentum without assuming that last-hour pace persists at full strength.
    remfrac=sum(organic_fracs[(s,k)] for k in range(j,5))
    expected_rem_base=max(float(base_arr.sum()), min(10.,.12*s60*len(base_arr)))
    if base_arr.sum()>0:base_arr*=expected_rem_base/base_arr.sum()
    pred_stock=np.full(len(sched),float(stock));score=np.zeros(len(sched))
    for k in range(j,5):
        tiers=sched[:,k-j];idx=np.searchsorted(LADDER,tiers)
        demand=np.maximum(0,base_arr[k-j]+promo[k,idx]);can_sell=np.minimum(pred_stock,demand)
        score+=can_sell*P[s]*(1-tiers/100)
        pred_stock-=can_sell
    # small handling cost for disposal, do not subtract sunk production cost twice
    score-=pred_stock*0.025*P[s]
    # slight tie breaking toward smaller discount
    score-=sched.sum(axis=1)*.00001
    pick=int(np.argmax(score));choice=int(sched[pick,0]);return choice,'JOINT_FORECAST_REVENUE_PLANNING'

def prepare_predict(d,s,visible,model,q):
    xt=train_encoder(pd.DataFrame([features(d,s,visible)]),COLS)
    forecast=max(0,float(model.predict(xt)[0]));raw=forecast+residual_offsets[(q,s)]
    return max(4,BATCH*math.ceil(raw/BATCH)),forecast

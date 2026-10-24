import json, pathlib, numpy as np,pandas as pd, joblib
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingRegressor,RandomForestRegressor,RandomForestClassifier
from sklearn.metrics import mean_absolute_error,accuracy_score
from scipy.optimize import minimize
import xgboost as xgb
R=pathlib.Path('/mnt/data/sf606_work/02_TRAIN_VALIDATION'); O=pathlib.Path('/mnt/data/SmartFresh_V606_Trained_Models');O.mkdir(exist_ok=True)
C=json.loads((R/'feature_contract.json').read_text()); report={'version':'V6.06','scope':'TRAIN_VALIDATION_ONLY','no_test_access':True,'m2_horizon':'day','model_selection':'validation','limitations':[]}
def load(split,filename): return pd.read_csv(R/split/filename)
def xy(frame,columns):
 d=frame[columns].copy()
 for c in d.columns:
  if d[c].dtype=='object':
   converted=pd.to_numeric(d[c],errors='coerce')
   if converted.notna().sum()>0 and converted.notna().sum()>=.95*d[c].notna().sum():d[c]=converted
 return d
# M2: one horizon, joined on keys, do not use final same-day observations as features.
def m2(split):
 x=load(split,'m2_morning_features.csv'); y=load(split,'m2_censor_aware_targets.csv');y=y[y.target_horizon=='day'];
 assert not y.duplicated(['date','sku_code']).any()
 m=x.merge(y,on=['date','sku_code'],how='inner',validate='one_to_one');assert len(m)==len(x)
 assert (pd.to_datetime(m.history_through)<pd.to_datetime(m.date)).all()
 assert (pd.to_datetime(m.weather_reference_date)<pd.to_datetime(m.date)).all()
 return m
tr,va=m2('fit'),m2('validation');cols=C['m2_predictive_columns'];X=xy(tr,cols);V=xy(va,cols)
cat=[c for c in cols if X[c].dtype=='object']; num=[c for c in cols if c not in cat]
pre=ColumnTransformer([('num',Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=False))]),num),('cat',Pipeline([('impute',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),cat)],sparse_threshold=0)
A=pre.fit_transform(X).astype(float);B=pre.transform(V).astype(float)
yt=tr.served_sales_lower_bound.to_numpy(float);yv=va.served_sales_lower_bound.to_numpy(float);ct=tr.demand_right_censored.to_numpy(bool);cv=va.demand_right_censored.to_numpy(bool)
# Asymmetric censored squared loss: exact targets use squared error; right-censored labels contribute only when prediction < known lower bound.
def cens_loss(p,y,c):
 residual=p-y
 return float(np.mean(np.where(c,np.minimum(residual,0)**2,residual**2)))
def obj(pred,dm):
 y=dm.get_label(); c=ct
 e=pred-y; active=(~c)|(e<0)
 return (2*e*active).astype(float),(2*active.astype(float)+1e-6)
dtrain=xgb.DMatrix(A,label=yt);dval=xgb.DMatrix(B,label=yv)
choices=[]
for depth in [2,4]:
 for n in [75,160]:
  params={'max_depth':depth,'eta':0.055,'min_child_weight':8,'subsample':1,'colsample_bytree':1,'seed':606,'nthread':2,'tree_method':'hist','base_score':float(np.median(yt))}
  mdl=xgb.train(params,dtrain,num_boost_round=n,obj=obj)
  p=np.maximum(0,mdl.predict(dval));choices.append((cens_loss(p,yv,cv),depth,n,mdl))
choices.sort(key=lambda a:a[0]);best=choices[0]; m2model=best[3];m2model.save_model(str(O/'M2_censored_xgboost.json'));joblib.dump(pre,O/'M2_preprocessor.joblib')
report['M2']={'fit_rows':len(tr),'validation_rows':len(va),'fit_censored':int(ct.sum()),'validation_censored':int(cv.sum()),'objective':'asymmetric_squared_error_right_censored_lower_bounds','selected_max_depth':best[1],'selected_rounds':best[2],'validation_censor_aware_loss':round(best[0],4),'validation_uncensored_MAE':round(mean_absolute_error(yv[~cv],np.maximum(0,m2model.predict(dval))[~cv]),4),'alternatives':[{'max_depth':d,'rounds':n,'val_censored_loss':round(s,4)} for s,d,n,_ in choices]}
# M1: imitation of logged action (not causal uplift), using only pre-action allowlist.
def m1(split):
 a=load(split,'m1_checkpoint_features.csv');b=load(split,'m1_logged_actions_TREATMENT_ONLY.csv'); c=load(split,'m1_outcomes_LABELS_ONLY.csv')
 m=a.merge(b,on=['date','sku_code','time'],validate='one_to_one').merge(c,on=['date','sku_code','time'],validate='one_to_one');assert len(m)==len(a)
 assert (pd.to_datetime(m.reward_available_at)>pd.to_datetime(m.decision_at)).all()
 return m
tr1,va1=m1('fit'),m1('validation');cols1=C['m1_pre_action_columns'];U=xy(tr1,cols1);W=xy(va1,cols1)
cat1=[c for c in cols1 if U[c].dtype=='object'];num1=[c for c in cols1 if c not in cat1]
prep1=ColumnTransformer([('num',SimpleImputer(strategy='median'),num1),('cat',Pipeline([('imp',SimpleImputer(strategy='most_frequent')),('enc',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),cat1)],sparse_threshold=0)
D=prep1.fit_transform(U);E=prep1.transform(W)
# Logged cash price may have 3 exact markdown prices, one per SKU group, and HOLD.
ycls=np.where(tr1.logged_action_discount_pct.to_numpy()>0,'MARKDOWN_LOGGED','HOLD');vcls=np.where(va1.logged_action_discount_pct.to_numpy()>0,'MARKDOWN_LOGGED','HOLD')
models=[]
for leaf in [5,20,50]:
 clf=RandomForestClassifier(n_estimators=100,min_samples_leaf=leaf,random_state=606,n_jobs=2,class_weight='balanced');clf.fit(D,ycls)
 score=accuracy_score(vcls,clf.predict(E));models.append((score,leaf,clf))
models.sort(key=lambda x:(-x[0],x[1]));mc=models[0][2];joblib.dump({'preprocessor':prep1,'classifier':mc,'columns':cols1},O/'M1_logged_action_imitation.joblib')
# Outcome regressor trained strictly on logged-action outcomes; no claim about counterfactuals.
reg_choices=[]
for leaf in [5,20,50]:
 rg=RandomForestRegressor(n_estimators=100,min_samples_leaf=leaf,random_state=606,n_jobs=2)
 rg.fit(D,tr1.sold_next30_observed);pred=rg.predict(E)
 reg_choices.append((mean_absolute_error(va1.sold_next30_observed,pred),leaf,rg))
reg_choices.sort(key=lambda x:x[0]);joblib.dump({'preprocessor':prep1,'regressor':reg_choices[0][2],'columns':cols1},O/'M1_logged_outcome_forecast.joblib')
report['M1']={'fit_checkpoints':len(tr1),'validation_checkpoints':len(va1),'objective':'IMITATION_OF_LOGGED_BASELINE_ACTION_NOT_PRICE_OPTIMIZATION','selected_action_min_samples_leaf':models[0][1],'validation_logged_action_accuracy':round(models[0][0],4),'fit_logged_markdown_rows':int((ycls=='MARKDOWN_LOGGED').sum()),'validation_logged_markdown_rows':int((vcls=='MARKDOWN_LOGGED').sum()),'outcome_target':'sold_next30_observed_ONLY_UNDER_LOGGED_ACTION','validation_logged_outcome_MAE':round(reg_choices[0][0],4)}
report['limitations']=['Neither M1 nor M2 has causal discount uplift evidence','M2 objective is not a demand point-label regression; censored rows provide lower-bound constraints','Models are training artifacts; adapter/runtime integration not performed because runtime ZIP 03 was not provided','No formal TEST executed; no revenue/service/lost-sales claims','Validation selection is not independent test performance']
(O/'train_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(O/'feature_contract.json').write_text((R/'feature_contract.json').read_text(),encoding='utf-8')
(O/'build_config_original.json').write_text((R/'build_config.json').read_text(),encoding='utf-8')
(O/'TRAINING_NOTES.md').write_text('''# SmartFresh V6.06 — Training-only artifacts\n\nOnly ZIP 02 was read. M2 uses `day` target and a right-censored lower-bound asymmetric squared loss, selected on validation. X strictly follows the allowlist in `feature_contract.json`. M1 imitates logged baseline HOLD/markdown actions and separately forecasts next-30-minute observed sales under logged actions. It **does not** estimate causal discount uplift and is **not** an optimized discount policy.\n\nDo not describe these artifacts as TEST-ready or POS-integrated. No 01/private, 03/test-runtime, 04 external data was accessed. No July/August data used, no official test, freeze, simulator adjustment, or profit claims. M2 fallbacks/OOD and M1 approval/price constraints must be enforced by a properly integrated future adapter/runtime before any test. Validation is development only.\n''',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

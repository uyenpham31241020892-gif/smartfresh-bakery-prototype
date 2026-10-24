"""Development-only retrospective diagnostics. No hidden demand or predictive model fit.
Quantiles are donor-scenario spread, NOT calibrated demand prediction intervals.
"""
from datetime import date,timedelta
import math,statistics
MIN_DONORS=7
LOOKBACK_DAYS=90

def quantile(a,q):
 a=sorted(a)
 if not a:return None
 p=(len(a)-1)*q;i=math.floor(p);return a[i] if i==len(a)-1 else a[i]*(1-(p-i))+a[i+1]*(p-i)

def reconstruct(day,sku,sold,censor,donors):
 """Donors list (date,56 served quantities), wholly uncensored, same SKU, strictly past.
Keep current uncensored slots exact; replace censored slots with max(served, donor).
One donor provides a whole-day profile, preserving donor intraday covariance.
"""
 floor=sum(sold);ds=[(d,v) for d,v in donors if d<day and (date.fromisoformat(day)-date.fromisoformat(d)).days<=LOOKBACK_DAYS]
 latest=max([d for d,_ in ds],default=None)
 r={'date':day,'sku_code':sku,'observed_demand_lower_bound':floor,'donor_count':len(ds),'donors_through':latest,'estimate_available_at':day+'T22:00:00+07:00','estimate_role':'RETROSPECTIVE_DIAGNOSTIC_NOT_MORNING_FEATURE_OR_GROUND_TRUTH','method':'PAST_SAME_SKU_UNCENSORED_DAY_PROFILE_90D','selection_bias_warning':'UNCENSORED_DONORS_MAY_UNDERREPRESENT_HIGH_DEMAND'}
 if not any(censor):
  r.update(donor_scenario_q10=floor,donor_scenario_q50=floor,donor_scenario_q90=floor,reconstruction_status='OBSERVED_UNCENSORED_SCENARIO_SALES',finite_true_upper_bound=None);return r
 if len(ds)<MIN_DONORS:
  r.update(donor_scenario_q10=None,donor_scenario_q50=None,donor_scenario_q90=None,reconstruction_status='INSUFFICIENT_PRIOR_DONORS_USE_RIGHT_CENSOR_LIKELIHOOD_OR_REVIEW',finite_true_upper_bound=None);return r
 draws=[sum(max(v[i],sold[i]) if censor[i] else sold[i] for i in range(len(sold))) for d,v in ds]
 r.update(donor_scenario_q10=quantile(draws,.10),donor_scenario_q50=quantile(draws,.50),donor_scenario_q90=quantile(draws,.90),reconstruction_status='EXPLORATORY_DONOR_SCENARIOS_NOT_CALIBRATED',finite_true_upper_bound=None)
 return r

def make_artificial_censor(sold,fraction=.80):
 """Keep only first80% of served units, with an empty-shelf flag from cap attainment.
Use only known uncensored development days. Held-out suffix never enters donors.
"""
 cap=max(1,math.floor(sum(sold)*fraction));left=cap;out=[];flags=[]
 for n in sold:
  take=min(left,n);left-=take;out.append(take);flags.append(int(left==0))
 return out,flags

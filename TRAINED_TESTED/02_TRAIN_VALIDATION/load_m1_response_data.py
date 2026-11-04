"""Prepare X/action/y; no training. Use simulation episodes, never optimal-action labels."""
import csv,json
from pathlib import Path
def load(root,split='fit',scenario='central'):
 root=Path(root)
 if split not in ('fit','validation') or scenario not in ('null','weak','central','strong'):raise ValueError('Invalid partition/scenario')
 columns=json.loads((root/'feature_contract.json').read_text())['m1_pre_action_columns']
 folder=root/split/'EXPLORATION_ASSUMED'/scenario
 def read(name):
  with (folder/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
 states=read('m1_checkpoint_features.csv');actions={r['sample_id']:r for r in read('m1_logged_actions_TREATMENT_ONLY.csv')};labels={r['sample_id']:r for r in read('m1_outcomes_LABELS_ONLY.csv')}
 out=[]
 for state in states:
  a=actions[state['sample_id']];y=labels[state['sample_id']]
  if y['label_available_at']<=state['decision_at']:raise ValueError('Invalid outcome availability')
  out.append(dict(X={k:state[k] for k in columns},candidate_action={k:a[k] for k in ('action_price_vnd','action_discount_pct')},y={k:y[k] for k in ('sold_next30_observed','revenue_next30_observed_vnd','censored_next30')},audit=dict(sample_id=state['sample_id'],source_date_group=state['source_date_group'],scenario_id=scenario,behavior_propensity=a['behavior_propensity'],label_available_at=y['label_available_at'])))
 return out

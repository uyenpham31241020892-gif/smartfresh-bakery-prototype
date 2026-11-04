import csv,json
from pathlib import Path
def load_features(root,split,module):
 root=Path(root);contract=json.loads((root/'feature_contract.json').read_text())
 if split not in ('fit','validation') or module not in ('M1','M2'):raise ValueError('Invalid split/module')
 name='m2_morning_features.csv' if module=='M2' else 'm1_checkpoint_features.csv';columns=contract['m2_predictive_columns' if module=='M2' else 'm1_pre_action_columns']
 with open(root/split/name,newline='',encoding='utf-8-sig') as f:
  reader=csv.DictReader(f)
  if any(any(t in c for t in ('hidden','intent','logged_action','logged_requested','next30')) for c in reader.fieldnames):raise ValueError('Forbidden feature columns')
  rows=list(reader)
 for r in rows:
  if module=='M2' and (r['history_through']>=r['date'] or r['weather_reference_date']>=r['date']):raise ValueError('Futureas-ofviolation')
 return [{k:r[k] for k in columns} for r in rows]

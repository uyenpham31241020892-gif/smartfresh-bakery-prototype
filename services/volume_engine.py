"""Primary JOINT models, plus version-pinned historical models."""
import hashlib
import importlib.util
import json
import sys
import math
from datetime import date
import numpy as np
from .engine import Engine, ROOT, MODEL_LOCK
from .volume_scenario import MODEL_VERSION, LEGACY_MODEL_VERSION, SCALE, scaled
from .seasonal_reference import anchor as seasonal_anchor


class VolumeEngine(Engine):
    def __init__(self,version=MODEL_VERSION):
        self._volume_ready = False
        super().__init__()
        if version not in (MODEL_VERSION,LEGACY_MODEL_VERSION):raise ValueError('Unknown model version')
        self.version = version
        self.model_dir = ROOT / ('models/joint' if version==MODEL_VERSION else 'models/volume_x10')
        report = json.loads((self.model_dir / 'manifest.json').read_text(encoding='utf-8'))
        if report['version'] != version or report['scale'] != SCALE or not report['passed']:
            raise ValueError('Model ×10 chưa qua kiểm tra hoặc sai phiên bản.')
        self._hashes.update(report['artifact_sha256'])
        self.adapter_path=ROOT/report['adapter_source'] if version==MODEL_VERSION else self.model_dir/'adapter_snapshot.py'
        self._hashes[self.adapter_path.relative_to(ROOT).as_posix()] = report['adapter_sha256']
        if version==MODEL_VERSION:self._hashes['services/joint_policy.py']=report['source_sha256']['services/joint_policy.py']
        self._hashes[(self.model_dir/'manifest.json').relative_to(ROOT).as_posix()] = hashlib.sha256((self.model_dir/'manifest.json').read_bytes()).hexdigest()
        self.manifest.update(report, no_retraining=False, COLS=[], MCOLS=[],
            native_model_hashes={**report['artifact_sha256'], report['adapter_source']: report['adapter_sha256']})
        if version==MODEL_VERSION:self.manifest['native_model_hashes']['services/joint_policy.py']=self._hashes['services/joint_policy.py']
        self.skus = [scaled(r) for r in self.skus]
        self.master = {r['sku_code']: r for r in self.skus}
        self.observed = [scaled(r) for r in self.observed]
        self.seed_rows = [r for r in self.observed if r['date'] < '2022-05-01']
        self.means = {s:float(np.mean([r['sold_qty'] for r in self.seed_rows if r['sku_code']==s])) for s in self.master}
        self.morning = {k:scaled(r) for k,r in self.morning.items()}
        self.selection.update(version=version, volume_scale=SCALE)
        self._volume_ready = True
        self.reload_if_needed()

    def reload_if_needed(self):
        if not self._volume_ready:
            return super().reload_if_needed()
        self.require_integrity()
        with MODEL_LOCK:
            name = 'smartfresh_volume_adapter_'+self.version
            spec = importlib.util.spec_from_file_location(name, self.adapter_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            module.MODELS_DIR = self.model_dir
            module.M1_BUNDLE_PATH = self.model_dir/'m1_pricing_q_bundle.joblib'
            module.M2_BUNDLE_PATH = self.model_dir/'m2_forecast_bundle.joblib'
            module.LOOKUP_PATH = self.model_dir/'operational_lookup.json'
            module.POLICY_PATH = self.model_dir/'policy_config.json'
            original_alias=sys.modules.get('smartfresh_adapter')
            sys.modules['smartfresh_adapter']=module
            try:module._load_artifacts()
            finally:
                if original_alias is not None:sys.modules['smartfresh_adapter']=original_alias
                else:sys.modules.pop('smartfresh_adapter',None)
            self.adapter, self.m1, self.m2 = module, module._M1_BUNDLE, module._M2_BUNDLE
            for bundle in (self.m1,self.m2):
                if bundle['metadata']['version'] != self.version or bundle['metadata']['scale'] != SCALE:
                    raise ValueError('Không được trộn bundle cũ với model ×10.')
            self.manifest['COLS'] = list(self.m2['preprocessor'].numeric_cols)
            self.manifest['MCOLS'] = list(self.m1['preprocessor'].numeric_cols)
        self.artifact_error = None

    def features(self,day,sku,visible,weather,outcomes=None):
        f=super().features(day,sku,visible,weather,outcomes)
        if self.version==MODEL_VERSION:
            history=[dict((outcomes or {}).get((d,s),{}),date=d,sku_code=s,sold_qty=n) for (d,s),n in sorted(visible.items()) if s==sku and d<day]
            f=self.adapter.prepare_features(f,history)
        return f

    def baseline(self,day,sku,visible,outcomes=None):
        """Seasonal ×10 baseline with stockout labels treated as lower bounds."""
        if self.version!=MODEL_VERSION:
            return super().baseline(day,sku,visible,outcomes)
        cutoff='2022-07-01' if day>='2022-07-01' else '2022-05-01'
        history=[dict((outcomes or {}).get((d,s),{}),date=d,sku_code=s,sold_qty=n)
                 for (d,s),n in visible.items() if s==sku and d<day]
        holiday=False  # The calendar flag is applied by M2; baseline is weekday-only.
        reference=seasonal_anchor(day,history,cutoff,holiday)
        weekday=date.fromisoformat(day).weekday()
        own=sorted((r for r in history if cutoff<=r['date']<day and
                    date.fromisoformat(r['date']).weekday()==weekday),key=lambda r:r['date'])[-4:]
        observed=[]
        for r in own:
            sold=float(r['sold_qty'])
            observed.append(max(sold,reference) if r.get('stockout') or r.get('censored_demand_flag') else sold)
        estimate=.65*reference+.35*(sum(observed)/len(observed)) if observed else reference
        batch=int(self.master[sku]['batch_size_units_assumed'])
        cap=int(self.master[sku]['daily_capacity_units_assumed'])
        return min(cap//batch*batch,max(batch,math.ceil(estimate*1.08/batch)*batch))

    def plan(self, *args, **kwargs):
        plans = super().plan(*args, **kwargs)
        for row in plans:
            row['supply'].update(demand_scale=SCALE, policy=self.version)
            if self.version==MODEL_VERSION:
                result=row['v4_plan'];q=result['quantiles']
                row['quantile']=result['selected_quantile']
                row['forecast']=q['50'];row['buffer']=row['prepared']-q['50']
                row['supply'].update(q45=q['45'],q75=q['75'],q90=q['90'],raw_forecast=q['50'],
                    selected_quantile=result['selected_quantile'],selected_forecast=result['selected_forecast'],
                    critical_fractile=result['critical_fractile'],depromo_removed_last7=result['depromo_removed_last7'])
        return plans

    def price(self,sku,j,stock,prepared,previous,sales30,sales60,forecast,weather,as_of=None,observed_context=None):
        with MODEL_LOCK:
            row=super().price(sku,j,stock,prepared,previous,sales30,sales60,forecast,weather,as_of,observed_context)
            if self.version!=MODEL_VERSION:return row
            minute=row['minute'];key=(weather['date']+f'T{minute//60:02}:{minute%60:02}:00+07:00',sku)
            evidence=self.adapter._LAST_PRICE_EVIDENCE[key]
            row.update(candidates=evidence['candidates'],predicted_hold_next30=evidence['hold_next30'],
                cap=evidence['cap'],pricing_policy=dict(version=self.version,**evidence),
                decision_reason=evidence['reason'],depromo_natural_next30=evidence['natural_next30'])
            row['economic_gate'].update(net_gain=evidence['net_gain'],sellout_probability=evidence['sellout_probability_hold'])
            return row

"""Verify original freeze hashes and export trusted V9 models to native LightGBM.

Only the locally supplied, hash-verified reference bundle is deserialized here.
Uploaded files are never deserialized by the web application.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import joblib
    import lightgbm
    import numpy as np
    source = ROOT / 'reference/drive_v9'
    frozen = json.loads((source / 'freeze.json').read_text())['sha256']
    for name in ['M1_Price_Response_LightGBM.joblib', 'M2_JMA_LightGBM.joblib', 'runtime.joblib']:
        p = source / 'models' / name
        expected = next(v for k, v in frozen.items() if k.endswith('/' + name))
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Frozen model hash mismatch: {name}')
    runtime = joblib.load(source / 'models/runtime.joblib')
    dest = ROOT / 'models'
    dest.mkdir(exist_ok=True)
    for name, short in [('M1_Price_Response_LightGBM', 'm1'), ('M2_JMA_LightGBM', 'm2')]:
        model = joblib.load(source / 'models' / (name + '.joblib'))
        model.booster_.save_model(str(dest / (short + '.txt')))
    def simple(value):
        if isinstance(value, dict):
            if any(isinstance(k, tuple) for k in value):
                return [{'key': list(k), 'value': simple(v)} for k, v in value.items()]
            return {str(k): simple(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [simple(v) for v in value]
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        return value
    metadata = simple(runtime)
    metadata['selection'] = json.loads((source / 'selection.json').read_text())
    metadata['version'] = 'V9-frozen-d8b621a5'
    metadata['lightgbm'] = lightgbm.__version__
    metadata['source_model_hashes'] = frozen
    metadata['native_model_hashes'] = {n: hashlib.sha256((dest / n).read_bytes()).hexdigest() for n in ['m1.txt', 'm2.txt']}
    (dest / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verified and exported frozen V9 models. Runtime keys:', list(runtime))


if __name__ == '__main__':
    main()

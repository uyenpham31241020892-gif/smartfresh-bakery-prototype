"""Build reproducible source/model/data manifest; no environment or private runtime."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.engine import ROOT
from services.readiness import SCHEMA_CONTRACT

def build(root=ROOT):
    root=Path(root);files={}
    for f in root.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(root);name=rel.as_posix()
        if set(rel.parts)&{'.venv','.tools','runtime','__pycache__','.pytest_cache','.git','node_modules'}:continue
        if not (rel.parts[0] in ['services','web','models','data','reference','scripts','tests','.github'] or name=='app.py' or name.startswith('requirements') or name.endswith('.cmd')):continue
        b=f.read_bytes()
        # Hash canonical LF for command launchers; packaging preserves CRLF for Windows.
        if name.endswith('.cmd'):b=b.replace(b'\r\n',b'\n')
        files[name]=hashlib.sha256(b).hexdigest()
    canonical=json.dumps(files,sort_keys=True).encode();ident=hashlib.sha256(canonical).hexdigest()
    manifest={'release':'SmartFresh GD9','release_id':ident,'hash_algorithm':'SHA256','cmd_line_endings':'canonical LF','files':dict(sorted(files.items())),'schema_version':'GD9-additive-v1','schema_contract':SCHEMA_CONTRACT,'schema_contract_sha256':hashlib.sha256(json.dumps(SCHEMA_CONTRACT,sort_keys=True).encode()).hexdigest(),'frozen_model_version':json.loads((root/'models/manifest.json').read_text())['version'],'policy_sha256':hashlib.sha256(json.dumps(json.loads((root/'models/manifest.json').read_text())['selection'],sort_keys=True).encode()).hexdigest()}
    (root/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');return manifest
if __name__=='__main__':print(build()['release_id'])

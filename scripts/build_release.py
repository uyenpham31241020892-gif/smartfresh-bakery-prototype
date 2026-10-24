"""Build the V606 source/artifact manifest; excludes secrets, runtime and legacy checkout."""
import hashlib,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.engine import ROOT
from services.v606 import Engine
from services.readiness import SCHEMA_CONTRACT

def build(root=ROOT):
 root=Path(root);files={};allowed={'services','web','scripts','tests','.github','v606'}
 for directory,dirs,names in os.walk(root):
  rel=Path(directory).relative_to(root)
  dirs[:]=[d for d in dirs if d not in {'.git','__pycache__','.pytest_cache','node_modules'} and (rel.parts or d in allowed)]
  for name in names:
   f=Path(directory)/name;r=f.relative_to(root);key=r.as_posix()
   if name=='local_config.json' or (not r.parent.parts and not(name=='app.py' or name.startswith('requirements') or name.endswith('.cmd'))):continue
   data=f.read_bytes().replace(b'\r\n',b'\n') if name.endswith('.cmd') else f.read_bytes()
   files[key]=hashlib.sha256(data).hexdigest()
 ident=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
 engine=Engine()
 manifest=dict(release='SmartFresh V606 service2130 v2',release_id=ident,files=dict(sorted(files.items())),hash_algorithm='SHA256',cmd_line_endings='canonical LF',schema_version='V606-prototype-v2',schema_contract=SCHEMA_CONTRACT,frozen_model_version=engine.version,policy_sha256=hashlib.sha256(json.dumps(engine.selection,sort_keys=True).encode()).hexdigest())
 (root/'release_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
 return manifest
if __name__=='__main__':print(build()['release_id'])

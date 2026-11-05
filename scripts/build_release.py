"""Content-address the app release. Frozen V4 model/data must still match their lock."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.engine import Engine
EVIDENCE={'docs/V4_QA_RESULTS.json','docs/V4_pytest.xml','docs/V4_TEST_OUTPUT.txt','docs/V4_BROWSER_QA.json','docs/PATCH_QA.json'}
EVIDENCE.update({'docs/JOINT_QA_RESULTS.json','docs/JOINT_pytest.xml','docs/JOINT_BROWSER_QA.json'})
def build(root=ROOT):
    from services.volume_engine import VolumeEngine
    root=Path(root);Engine().require_integrity();active=VolumeEngine();active.require_integrity();files={}
    exclude={'.venv','.tools','.git','runtime','__pycache__','.pytest_cache','node_modules'}
    for folder,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in exclude and not d.startswith('.test_tmp')]
        for name in names:
            p=Path(folder)/name;rel=p.relative_to(root).as_posix()
            if rel in ['release_manifest.json','.env'] or p.is_symlink() or p.suffix=='.pyc':continue
            data=p.read_bytes();data=data.replace(b'\r\n',b'\n') if rel.endswith('.cmd') else data
            files[rel]=hashlib.sha256(data).hexdigest()
    core={k:v for k,v in sorted(files.items()) if k not in EVIDENCE}
    ident=hashlib.sha256(json.dumps(core,sort_keys=True).encode()).hexdigest()
    manifest=dict(release='SmartFresh JOINT primary operating model 2026-11-05',release_id=ident,files=dict(sorted(files.items())),hash_algorithm='SHA256',cmd_line_endings='canonical LF',active_model_version=active.version,frozen_model_version='SMARTFRESH_V4_LOCKED',evidence_excluded_from_release_id=sorted(EVIDENCE))
    (root/'release_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest
if __name__=='__main__':print(build()['release_id'])

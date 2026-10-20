"""Read all document/workbook/notebook content; create a curated runtime bundle."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import fitz
    import openpyxl
    inv = json.loads((ROOT / 'docs/source_inventory.json').read_text(encoding='utf-8'))
    source = ROOT / 'data/source_archives' / Path(inv['archive']).stem / 'V9'
    corpus, seen = [], set()
    for item in inv['entries']:
        p = ROOT / item['local_path']
        if item['sha256'] in seen:
            continue
        seen.add(item['sha256'])
        text = item.get('text')
        if p.suffix == '.pdf':
            with fitz.open(p) as doc:
                text = '\n'.join(page.get_text() for page in doc)
        elif p.suffix == '.docx':
            with zipfile.ZipFile(p) as z:
                x = ET.fromstring(z.read('word/document.xml'))
                text = '\n'.join(''.join(e.itertext()) for e in x.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
        elif p.suffix == '.xlsx':
            book = openpyxl.load_workbook(p, data_only=True, read_only=True)
            text = '\n'.join('SHEET ' + ws.title + '\n' + '\n'.join(json.dumps(list(row), ensure_ascii=False, default=str) for row in ws.values) for ws in book)
            book.close()
        elif p.suffix == '.ipynb':
            notebook = json.loads(p.read_text(encoding='utf-8-sig'))
            text = '\n'.join(''.join(c.get('source', [])) for c in notebook['cells'])
        if text:
            corpus.append({'path': item['path'], 'content': text})
    (ROOT / 'docs/bundle_content.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding='utf-8')
    for folder, target in [('01_Dataset_moi', 'data/current_v9'), ('11_V9_Final_Model_Analysis', 'data/current_v9/outputs')]:
        dest = ROOT / target
        dest.mkdir(parents=True, exist_ok=True)
        for p in (source / folder).iterdir():
            if p.is_file() and p.suffix in ['.csv', '.json']:
                shutil.copy2(p, dest / p.name)
    ref = ROOT / 'reference/drive_v9'
    mapping = {'policy.py': source / '11_V9_Final_Model_Analysis/policy.py',
               'worker.py': source / '11_V9_Final_Model_Analysis/worker.py',
               'selection.json': source / '11_V9_Final_Model_Analysis/selection_manifest.json',
               'summary.json': source / '11_V9_Final_Model_Analysis/RUN_SUMMARY.json',
               'freeze.json': source / 'Test_SmartFresh v9/output/MODEL_FREEZE.json'}
    for name, p in mapping.items():
        shutil.copy2(p, ref / name)
    for p in (source / '11_V9_Final_Model_Analysis/models').glob('*.joblib'):
        shutil.copy2(p, ref / 'models' / p.name)
    curated = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (ROOT / 'data/current_v9').rglob('*') if p.is_file() and p.name != 'provenance.json'}
    (ROOT / 'data/current_v9/provenance.json').write_text(json.dumps({'archive': inv['archive'], 'archive_sha256': inv['sha256'],
            'files': curated, 'missing_original_observations': True}, indent=2), encoding='utf-8')
    print('Read', len(corpus), 'distinct text/document/workbook/notebook artifacts;', len(curated), 'curated runtime files.')
    for entry in corpus:
        if entry['path'].endswith('.docx'):
            print('\nDOCUMENT', entry['path'], '\n', entry['content'][:26000])


if __name__ == '__main__':
    main()

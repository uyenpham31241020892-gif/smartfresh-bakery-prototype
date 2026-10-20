"""Inventory the complete supplied archive without executing its contents."""
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(archive):
    archive = Path(archive)
    target = ROOT / "data" / "source_archives" / archive.stem
    target.mkdir(parents=True, exist_ok=True)
    entries = []
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            raw = z.read(info)
            item = {"path": info.filename, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            safe_name = '/'.join(part.rstrip(' .') for part in info.filename.split('/'))
            item['local_path'] = str((target / safe_name).relative_to(ROOT))
            out = (target / safe_name).resolve()
            if not out.is_relative_to(target.resolve()):
                raise ValueError("Unsafe archive path")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(raw)
            try:
                if info.filename.endswith('.csv'):
                    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                    item.update(rows=len(rows), columns=list(rows[0]) if rows else [])
                elif info.filename.endswith('.json'):
                    value = json.loads(raw.decode('utf-8-sig'))
                    item['keys'] = list(value) if isinstance(value, dict) else [f'{len(value)} records']
                elif info.filename.endswith(('.md', '.py', '.txt')):
                    item['text'] = raw.decode('utf-8-sig')
            except (UnicodeError, ValueError) as e:
                item['parse_error'] = str(e)
            entries.append(item)
    report = {"archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
              "requested_archive": "V9-20261020T063226Z-1-001.zip", "exact_requested_archive": archive.name == "V9-20261020T063226Z-1-001.zip",
              "files": len(entries), "entries": entries}
    (ROOT / 'docs' / 'source_inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'entries'}, indent=2))


if __name__ == '__main__':
    audit(sys.argv[1])

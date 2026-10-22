"""Offline full SQLite + learned artifacts backup. Restore only to a new directory."""
import argparse,hashlib,json,os,sqlite3,sys,tempfile,zipfile
from pathlib import Path
from datetime import datetime,timezone

def sha(b):return hashlib.sha256(b).hexdigest()
def backup(db,learning,output,server_stopped=False):
    if not server_stopped:raise ValueError('Dừng server rồi truyền --server-stopped để xác nhận.')
    db,learning,output=map(Path,[db,learning,output])
    if not db.is_file() or output.exists():raise ValueError('Database phải tồn tại; file backup đích phải chưa tồn tại.')
    files={}
    with tempfile.TemporaryDirectory() as tmp:
        copy=Path(tmp)/'state.sqlite3'
        source=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);target=sqlite3.connect(copy)
        try:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite không toàn vẹn.')
        finally:source.close();target.close()
        files['state.sqlite3']=copy.read_bytes()
    if learning.exists():
        for f in learning.rglob('*'):
            if f.is_symlink():raise ValueError('Không backup symlink.')
            if f.is_file() and f.suffix not in ['.txt','.json']:raise ValueError('Learning folder chứa file ngoài định dạng model hỗ trợ.')
            if f.is_file():files['learning/'+f.relative_to(learning).as_posix()]=f.read_bytes()
    manifest={'format':1,'created':datetime.now(timezone.utc).isoformat(),'files':{k:sha(v) for k,v in files.items()},'note':'Chứa tài khoản băm, lịch sử và model học; bảo quản như dữ liệu nội bộ. Không có .env hoặc API key.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
            for k,v in files.items():z.writestr(k,v)
            z.writestr('backup_manifest.json',json.dumps(manifest))
    except Exception:
        output.unlink(missing_ok=True);raise
    return manifest

def restore(archive,destination,server_stopped=False):
    if not server_stopped:raise ValueError('Dừng server rồi truyền --server-stopped để xác nhận.')
    destination=Path(destination)
    if destination.exists():raise ValueError('Chỉ phục hồi vào thư mục mới, không ghi đè runtime đang có.')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();names=[x.filename for x in infos]
        if len(names)!=len(set(names)) or len(names)>10000 or sum(i.file_size for i in infos)>512*1024*1024:raise ValueError('Backup quá lớn hoặc trùng tên.')
        m=json.loads(z.read('backup_manifest.json'));expected=m['files']
        if m.get('format')!=1 or set(names)!=set(expected)|{'backup_manifest.json'} or 'state.sqlite3' not in expected:raise ValueError('Manifest backup không hợp lệ.')
        for name in expected:
            parts=Path(name).parts
            if '\\' in name or ':' in name or name.startswith('/') or '..' in parts or (name!='state.sqlite3' and not name.startswith('learning/')):raise ValueError('Đường dẫn backup không an toàn.')
            if sha(z.read(name))!=expected[name]:raise ValueError('Checksum backup không khớp.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
            stage=Path(tmp)/'restored';stage.mkdir()
            for name in expected:
                f=stage/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(name))
            db=sqlite3.connect(stage/'state.sqlite3')
            try:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Database phục hồi lỗi.')
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'sessions','audit','local_users','learning_runs','model_active'}<=tables:raise ValueError('Không phải database SmartFresh đầy đủ.')
                active=db.execute('SELECT version FROM model_active WHERE id=1').fetchone()
                required={r[0] for r in db.execute("SELECT DISTINCT json_extract(state,'$.model_version') FROM sessions")}
                if active:required.add(active[0])
                for version in required:
                    if not version or not version.startswith('learn-'):continue
                    if not version.removeprefix('learn-').isalnum():raise ValueError('Phiên bản model backup không hợp lệ.')
                    folder=stage/'learning'/version
                    try:
                        model_manifest=json.loads((folder/'manifest.json').read_text())
                        for name in ['m1.txt','m2.txt']:
                            if sha((folder/name).read_bytes())!=model_manifest['native_model_hashes'][name]:raise ValueError('Artifact model phục hồi không khớp.')
                        if sha((folder/'training_data.json').read_bytes())!=model_manifest['training_data_sha256']:raise ValueError('Training snapshot phục hồi không khớp.')
                    except (OSError,KeyError):raise ValueError('Backup thiếu artifact của model đang dùng hoặc ca đã ghim.') from None
                # Invalidate old login sessions, stop clocks/jobs; retain users and business audit.
                if 'login_sessions' in tables:db.execute('DELETE FROM login_sessions')
                if 'simulation_clocks' in tables:db.execute('UPDATE simulation_clocks SET enabled=0')
                if 'monitoring_jobs' in tables:db.execute("UPDATE monitoring_jobs SET status='interrupted' WHERE status='running'")
                db.execute('INSERT INTO audit(action,detail) VALUES (?,?)',('BACKUP_RESTORED',json.dumps({'at':datetime.now(timezone.utc).isoformat(),'login_sessions_invalidated':True})));db.commit()
            finally:db.close()
            os.rename(stage,destination)
    return {'restored_to':str(destination),'requires_login':True,'old_runtime_overwritten':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore']);parser.add_argument('--db',type=Path);parser.add_argument('--learning',type=Path);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--destination',type=Path);parser.add_argument('--server-stopped',action='store_true');args=parser.parse_args()
    try:
        if args.action=='backup':
            if not args.db or not args.learning:raise ValueError('Cần --db và --learning.')
            result=backup(args.db.resolve(),args.learning.resolve(),args.archive.resolve(),args.server_stopped)
        else:
            if not args.destination:raise ValueError('Cần --destination mới.')
            result=restore(args.archive,args.destination,args.server_stopped)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,zipfile.BadZipFile,KeyError,sqlite3.Error) as e:parser.exit(1,str(e)+'\n')
if __name__=='__main__':main()

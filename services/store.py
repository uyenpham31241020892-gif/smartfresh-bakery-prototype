import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .engine import ROOT


class Store:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'runtime/smartfresh.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, action TEXT, detail TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def save(self, db, state, action, detail=None):
        db.execute('INSERT INTO sessions(id,state) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,updated=CURRENT_TIMESTAMP',
                   (state['id'], json.dumps(state, ensure_ascii=False, allow_nan=False)))
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                   (state['id'], action, json.dumps(detail or {}, ensure_ascii=False)))

    def get(self, session_id=None):
        with self.connect() as db:
            row = db.execute('SELECT state FROM sessions WHERE id=?', (session_id,)).fetchone() if session_id else db.execute('SELECT state FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
            if not row:
                raise ValueError('Không tìm thấy ca vận hành.')
            return json.loads(row['state'])

    def audit(self, sid):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit WHERE session_id=? ORDER BY id DESC LIMIT 100', (sid,))]

    def sessions(self):
        with self.connect() as db:
            return [json.loads(r['state']) for r in db.execute('SELECT state FROM sessions ORDER BY rowid DESC LIMIT 30')]

    def closed_before(self,day,mode,seed=None):
        with self.connect() as db:
            rows=db.execute("SELECT state FROM sessions WHERE json_extract(state,'$.phase')='closed' AND json_extract(state,'$.day')<? AND json_extract(state,'$.mode')=? ORDER BY rowid",(day,mode))
            result=[json.loads(r['state']) for r in rows]
        return [s for s in result if seed is None or s['seed']==seed]

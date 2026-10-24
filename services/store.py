import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .engine import ROOT
from .identity import actor,request_trace


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
    def connect(self, write=True):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous = NORMAL')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def read(self):
        return self.connect(write=False)

    def save(self, db, state, action, detail=None):
        old=db.execute('SELECT state FROM sessions WHERE id=?',(state['id'],)).fetchone()
        before=json.loads(old['state']) if old else {}
        def prices(s):return {sku:{'discount':p['discount'],'unit_price':round(p['price']*(1-p['discount']/100))} for sku,p in s.get('products',{}).items()}
        def proposal(s):
            p=s.get('pending') or {}
            return {'id':p.get('id'),'origin':p.get('origin'),'rows':[{k:r.get(k) for k in ['sku','previous','discount','approved']} for r in p.get('rows',[])]}
        def quantities(s):return {p['sku']:{'proposed':p['prepared'],'approved':p.get('approved')} for p in s.get('plan',[])}
        detail={**(detail or {}),'actor':actor.get(),'request_id':request_trace.get(),'model_version':state.get('model_version'),
                'model_hashes':state.get('model_hashes'),'feature_snapshot_id':state.get('feature_snapshot_id'),
                'minute':state['minute'],'before':{'phase':before.get('phase'),'prices':prices(before),'proposal':proposal(before),'quantities':quantities(before)},
                'after':{'phase':state['phase'],'prices':prices(state),'proposal':proposal(state),'quantities':quantities(state)},
                'prediction_origin':state.get('prediction_origin')}
        if action=='PLAN_APPROVE':detail['production_approval']=state.get('production_approval')
        db.execute('INSERT INTO sessions(id,state) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,updated=CURRENT_TIMESTAMP',
                   (state['id'], json.dumps(state, ensure_ascii=False, allow_nan=False)))
        db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                   (state['id'], action, json.dumps(detail or {}, ensure_ascii=False)))

    def get(self, session_id=None):
        with self.read() as db:
            row = db.execute('SELECT state FROM sessions WHERE id=?', (session_id,)).fetchone() if session_id else db.execute('SELECT state FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
            if not row:
                raise ValueError('Không tìm thấy ca vận hành.')
            return json.loads(row['state'])

    def audit(self, sid):
        with self.read() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit WHERE session_id=? ORDER BY id DESC LIMIT 100', (sid,))]

    def sessions(self):
        with self.read() as db:
            return [json.loads(r['state']) for r in db.execute('SELECT state FROM sessions ORDER BY rowid DESC LIMIT 30')]

    def closed_before(self,day,mode,seed=None):
        with self.read() as db:
            rows=db.execute("SELECT state FROM sessions WHERE json_extract(state,'$.phase')='closed' AND json_extract(state,'$.day')<? AND json_extract(state,'$.mode')=? ORDER BY rowid",(day,mode))
            result=[json.loads(r['state']) for r in rows]
        return [s for s in result if seed is None or s['seed']==seed]

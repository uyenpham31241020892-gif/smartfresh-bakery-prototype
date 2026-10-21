"""Server-owned virtual clock: continues while the browser is closed, never injects live sales."""
import json
import threading
import time


class Realtime:
    def __init__(self,workflow,store):
        self.workflow,self.store=workflow,store
        self.stop_event=threading.Event()
        self.thread=None
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS simulation_clocks(sid TEXT PRIMARY KEY,enabled INTEGER,speed REAL,pause_confirm INTEGER,last_wall REAL,error TEXT)')

    def status(self,sid):
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM simulation_clocks WHERE sid=?',(sid,)).fetchone()
        return dict(row) if row else {'enabled':False,'speed':5.,'pause_confirm':True,'error':None}

    def configure(self,sid,enabled,speed=5.,pause_confirm=True):
        s=self.store.get(sid)
        if s['mode']!='simulation':
            raise ValueError('Không chèn bán giả vào ca dữ liệu thật. Hãy tạo bản mô phỏng riêng.')
        if speed not in [1/60,1.,5.,30.]:
            raise ValueError('Tốc độ mô phỏng không hợp lệ.')
        if enabled and s['phase'] not in ['running','price_pending','price_approved']:
            raise ValueError('Cần xác nhận đã chuẩn bị trước khi bắt đầu bán tự động.')
        if enabled and s['minute']<480:
            self.workflow.mutate(sid,s['revision'],'tick',{'target':480})
        with self.store.connect() as db:
            db.execute('INSERT INTO simulation_clocks VALUES (?,?,?,?,?,?) ON CONFLICT(sid) DO UPDATE SET enabled=excluded.enabled,speed=excluded.speed,pause_confirm=excluded.pause_confirm,last_wall=excluded.last_wall,error=NULL',
                       (sid,int(enabled),speed,int(pause_confirm),time.time(),None))
            db.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',(sid,'SIMULATION_CLOCK',json.dumps({'enabled':enabled,'speed':speed,'pause_confirm':pause_confirm})))
        return self.status(sid)

    def step(self,wall=None):
        wall=time.time() if wall is None else wall
        with self.store.connect() as db:
            jobs=[dict(r) for r in db.execute('SELECT * FROM simulation_clocks WHERE enabled=1')]
        for job in jobs:
            sid=job['sid']
            try:
                s=self.store.get(sid)
                if s['phase'] in ['closed','close_pending']:
                    self.configure(sid,False,job['speed'],bool(job['pause_confirm']));continue
                waiting=s['phase'] in ['price_pending','price_approved'] and job['pause_confirm']
                elapsed=max(0.,wall-job['last_wall'])
                minutes=min(30,int(elapsed*job['speed']))
                if waiting:
                    with self.store.connect() as db:
                        db.execute('UPDATE simulation_clocks SET last_wall=? WHERE sid=?',(wall,sid))
                    continue
                if not minutes:continue
                self.workflow.mutate(sid,s['revision'],'tick',{'target':min(1320,s['minute']+minutes)})
                with self.store.connect() as db:
                    db.execute('UPDATE simulation_clocks SET last_wall=? WHERE sid=?',(wall,sid))
            except ValueError as exc:
                if 'thay đổi' in str(exc):
                    continue  # a human action won the revision race; retry with fresh state
                with self.store.connect() as db:
                    db.execute('UPDATE simulation_clocks SET enabled=0,error=? WHERE sid=?',(str(exc),sid))

    def start(self):
        if self.thread and self.thread.is_alive():return
        with self.store.connect() as db:
            db.execute('UPDATE simulation_clocks SET enabled=0,last_wall=?',(time.time(),))
        self.stop_event.clear()
        def run():
            while not self.stop_event.wait(.5):
                self.step()
        self.thread=threading.Thread(target=run,name='smartfresh-virtual-clock',daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)

"""Local password authentication, opaque expiring sessions and backend roles."""
from contextvars import ContextVar
import hashlib
import hmac
import json
import re
import secrets
import time

request_trace = ContextVar('smartfresh_request_id',default=None)

actor = ContextVar('smartfresh_actor', default={'id':'system','username':'system','role':'system'})


class AccessError(ValueError):
    pass


class Identity:
    def __init__(self, store):
        self.store=store
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS local_users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS login_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS login_limits(username TEXT PRIMARY KEY,failures INTEGER NOT NULL,blocked_until REAL NOT NULL);
            ''')

    @staticmethod
    def password(value,salt):
        return hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

    def setup_needed(self):
        with self.store.connect() as db:return not db.execute('SELECT 1 FROM local_users LIMIT 1').fetchone()

    def create(self,username,password,role='manager',bootstrap=False):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username) or not 8<=len(password)<=128 or role not in ['manager','staff','viewer']:
            raise ValueError('Tên tài khoản 3–40 ký tự A–Z/0–9/._-, mật khẩu 8–128 ký tự, vai trò manager/staff/viewer.')
        if not bootstrap and actor.get()['role']!='manager':raise AccessError('Chỉ Manager được tạo tài khoản.')
        salt=secrets.token_hex(16);uid=secrets.token_hex(12);hashed=self.password(password,salt)
        with self.store.connect() as db:
            if bootstrap and db.execute('SELECT 1 FROM local_users LIMIT 1').fetchone():raise AccessError('Đã có tài khoản; không thể thiết lập lần đầu lại.')
            if db.execute('SELECT 1 FROM local_users WHERE username=?',(username,)).fetchone():raise ValueError('Tên tài khoản đã tồn tại.')
            db.execute('INSERT INTO local_users VALUES (?,?,?,?,?)',(uid,username,hashed,salt,'manager' if bootstrap else role))
            db.execute('INSERT INTO audit(session_id,action,detail) VALUES (NULL,?,?)',('USER_CREATED',json.dumps({'actor':actor.get(),'username':username,'role':role})))
        return {'id':uid,'username':username,'role':role}

    def login(self,username,password):
        now=time.time()
        with self.store.connect() as db:
            lock=db.execute('SELECT * FROM login_limits WHERE username=?',(username,)).fetchone()
            if lock and lock['blocked_until']>now:raise AccessError('Đăng nhập sai nhiều lần; thử lại sau 5 phút.')
            row=db.execute('SELECT * FROM local_users WHERE username=?',(username,)).fetchone()
            valid=row is not None and hmac.compare_digest(self.password(password,row['salt']),row['password_hash'])
            if not valid:
                failures=(lock['failures'] if lock and lock['blocked_until']<=now and lock['blocked_until']==0 else 0)+1
                db.execute('INSERT INTO login_limits VALUES (?,?,?) ON CONFLICT(username) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until',
                           (username,failures,now+300 if failures>=5 else 0))
            else:
                db.execute('DELETE FROM login_limits WHERE username=?',(username,))
                token=secrets.token_urlsafe(32)
                db.execute('INSERT INTO login_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],now+8*3600))
                db.execute('INSERT INTO audit(session_id,action,detail) VALUES (NULL,?,?)',('LOGIN',json.dumps({'actor':{'id':row['id'],'username':username,'role':row['role']}})))
        if not valid:raise AccessError('Sai tài khoản hoặc mật khẩu.')
        return token,{'id':row['id'],'username':row['username'],'role':row['role']}

    def authenticate(self,token):
        if not token:return None
        with self.store.connect() as db:
            r=db.execute('SELECT u.id,u.username,u.role FROM login_sessions s JOIN local_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',
                         (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(r) if r else None

    def logout(self,token):
        with self.store.connect() as db:db.execute('DELETE FROM login_sessions WHERE token_hash=?',(hashlib.sha256((token or '').encode()).hexdigest(),))

    @staticmethod
    def authorize(user,path,method):
        if method in ['GET','HEAD']:return
        if path=='/api/auth/logout':return
        if user['role']=='viewer':raise AccessError('Viewer chỉ được xem; không có quyền thay đổi dữ liệu.')
        manager = (path.startswith(('/api/evaluation/','/api/monitoring/','/api/safety/','/api/auth/users','/api/learning/','/api/ai/')) or
                   path.rsplit('/',1)[-1] in ['plan_approve','plan_reject','price_approve','price_reject','price_apply'])
        if manager and user['role']!='manager':raise AccessError('Thao tác này cần tài khoản Manager đã đăng nhập.')

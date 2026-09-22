"""Durable SQLite intents, signals, fills and risk state, with OS single-writer lock."""
from __future__ import annotations
import csv,hashlib,json,os,sqlite3,time
from pathlib import Path
from contextlib import contextmanager

class SingleProcess:
    def __init__(self,path):self.path=Path(str(path)+'.lock');self.handle=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.handle=self.path.open('a+b')
        self.handle.seek(0);self.handle.write(b'0');self.handle.flush();self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,IOError):self.handle.close();raise RuntimeError('another process owns this state database') from None
        return self
    def __exit__(self,*args):
        if self.handle:
            if os.name=='nt':
                import msvcrt;self.handle.seek(0);msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
            self.handle.close()

class Store:
    def __init__(self,path,readonly=False):
        self.path=Path(path)
        if readonly:
            self.db=sqlite3.connect(self.path.resolve().as_uri()+"?mode=ro",uri=True,timeout=10,isolation_level=None)
            self.db.row_factory=sqlite3.Row;self.db.execute("BEGIN");return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,available_ms INTEGER,symbol TEXT,payload TEXT,state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,kind TEXT,symbol TEXT,state TEXT,payload TEXT,response TEXT,created_ms INTEGER,updated_ms INTEGER);
        CREATE TABLE IF NOT EXISTS fills(symbol TEXT,id INTEGER,payload TEXT,PRIMARY KEY(symbol,id));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,at_ms INTEGER,kind TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS bars(symbol TEXT,interval TEXT,open_ms INTEGER,open REAL,high REAL,low REAL,close REAL,volume REAL,taker_buy_volume REAL,trades REAL,PRIMARY KEY(symbol,interval,open_ms));
        CREATE TABLE IF NOT EXISTS equity(at_ms INTEGER PRIMARY KEY,equity REAL,available REAL);
        CREATE TABLE IF NOT EXISTS income(kind TEXT,tran_id TEXT,payload TEXT,PRIMARY KEY(kind,tran_id));
        CREATE TABLE IF NOT EXISTS closed_positions(id TEXT PRIMARY KEY,payload TEXT);
        ''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(bars)')}
        for name in ('taker_buy_volume','trades'):
            if name not in columns:self.db.execute('ALTER TABLE bars ADD COLUMN '+name+' REAL')
        try:os.chmod(self.path,0o600)
        except OSError:pass
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.execute('ROLLBACK');raise
        else:self.db.execute('COMMIT')
    def close(self):self.db.close()
    def get(self,key,default=None):
        r=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return json.loads(r[0]) if r else default
    def set(self,key,value):
        self.db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,allow_nan=False)))
    def bind(self,identity:dict):
        prior=self.get('binding')
        if prior is None:self.set('binding',identity)
        elif prior!=identity:raise ValueError('state belongs to a different account, mode, symbol or strategy; do not reuse it')
    def event(self,kind,payload):
        self.db.execute('INSERT INTO events(at_ms,kind,payload) VALUES(?,?,?)',(int(time.time()*1000),kind,json.dumps(payload,allow_nan=False)))
    def claim_signal(self,ident,symbol,available_ms,payload):
        cur=self.db.execute('INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?)',(ident,available_ms,symbol,json.dumps(payload,allow_nan=False),'CLAIMED'));return cur.rowcount==1
    def signal_state(self,ident,state):self.db.execute('UPDATE signals SET state=? WHERE id=?',(state,ident))
    def intent(self,ident,kind,symbol,payload):
        now=int(time.time()*1000);body=json.dumps(payload,sort_keys=True,allow_nan=False)
        r=self.db.execute('SELECT payload,kind FROM intents WHERE id=?',(ident,)).fetchone()
        if r:
            if r['payload']!=body or r['kind']!=kind:raise ValueError('client ID payload collision')
            return False
        self.db.execute('INSERT INTO intents VALUES(?,?,?,?,?,?,?,?)',(ident,kind,symbol,'PLANNED',body,'null',now,now));return True
    def update_intent(self,ident,state,response=None):
        self.db.execute('UPDATE intents SET state=?,response=?,updated_ms=? WHERE id=?',(state,json.dumps(response,allow_nan=False),int(time.time()*1000),ident))
    def get_intent(self,ident):
        r=self.db.execute('SELECT * FROM intents WHERE id=?',(ident,)).fetchone()
        return dict(r) if r else None
    def pending(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM intents WHERE state IN ('PLANNED','SUBMITTED','UNKNOWN','NEW','PARTIALLY_FILLED') ORDER BY created_ms")]
    def put_income(self,row):
        return self.db.execute('INSERT OR IGNORE INTO income VALUES(?,?,?)',(row['incomeType'],str(row['tranId']),json.dumps(row,allow_nan=False))).rowcount==1
    def put_fills(self,rows):
        for r in rows:self.db.execute('INSERT OR IGNORE INTO fills VALUES(?,?,?)',(r['symbol'],int(r['id']),json.dumps(r,allow_nan=False)))
    def put_bars(self,symbol,interval,rows,server_ms):
        added=0
        for r in rows:
            if int(r[6])>=server_ms:continue
            vals=tuple(float(r[i]) for i in [1,2,3,4,5]);start=int(r[0])
            import math
            op,hi,lo,cl,vol=vals
            if not all(math.isfinite(x) for x in vals) or min(op,hi,lo,cl)<=0 or hi<max(op,cl) or lo>min(op,cl) or vol<0:raise ValueError('invalid exchange candle')
            flow=float(r[9]) if len(r)>9 else None;trades=float(r[8]) if len(r)>8 else None
            if flow is not None and (not math.isfinite(flow) or flow<0 or flow>vol*1.000001):raise ValueError('invalid taker volume')
            if trades is not None and (not math.isfinite(trades) or trades<0):raise ValueError('invalid trade count')
            old=self.db.execute('SELECT open,high,low,close,volume,taker_buy_volume,trades FROM bars WHERE symbol=? AND interval=? AND open_ms=?',(symbol,interval,start)).fetchone()
            if old is not None:
                if any(abs(a-b)>max(1e-9,abs(b)*1e-10) for a,b in zip(vals,tuple(old)[:5])):
                    raise ValueError('exchange revised an already completed bar; stop and review source identity')
                for new,previous in zip((flow,trades),tuple(old)[5:]):
                    if new is not None and previous is not None and abs(new-previous)>max(1e-9,abs(previous)*1e-10):raise ValueError('exchange revised completed order-flow data')
                self.db.execute('UPDATE bars SET taker_buy_volume=COALESCE(taker_buy_volume,?),trades=COALESCE(trades,?) WHERE symbol=? AND interval=? AND open_ms=?',(flow,trades,symbol,interval,start))
                continue
            self.db.execute('INSERT INTO bars(symbol,interval,open_ms,open,high,low,close,volume,taker_buy_volume,trades) VALUES(?,?,?,?,?,?,?,?,?,?)',(symbol,interval,start,*vals,flow,trades));added+=1
        return added
    def bars(self,symbol,interval):
        return [dict(r) for r in self.db.execute('SELECT * FROM bars WHERE symbol=? AND interval=? ORDER BY open_ms',(symbol,interval))]
    def export(self,directory):
        dest=Path(directory);dest.mkdir(parents=True,exist_ok=True)
        for table in ['signals','intents','fills','events','equity','closed_positions','income']:
            cur=self.db.execute('SELECT * FROM '+table)
            with (dest/(table+'.csv')).open('w',newline='') as f:
                w=csv.writer(f);w.writerow([x[0] for x in cur.description]);w.writerows(cur)
        return dest

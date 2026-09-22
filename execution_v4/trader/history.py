"""Seed a causal, checksum-pinned public bar cache. Does not access an account."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
from .store import Store,SingleProcess
from .strategy import aggregate_minutes

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def seed(path,expected,dbpath,spec,settings):
    if digest(path)!=expected:raise ValueError('market input SHA-256 mismatch')
    with np.load(path,allow_pickle=False) as z:
        raw={k:z[k] for k in ['timestamp','open','high','low','close','volume','taker_buy_volume','trades']}
    ts=raw['timestamp'];now=int(pd.Timestamp.now(tz='UTC').timestamp()*1000)
    if len(ts)<2 or not np.all(np.diff(ts)==60000) or ts[-1]+60000>now:raise ValueError('noncontinuous or future market history')
    if int(pd.Timestamp(settings.bootstrap_start_utc).timestamp()*1000)!=int(ts[0]):raise ValueError('bootstrap start must match seeded input start for indicator parity')
    bars=aggregate_minutes(raw,spec.timeframe_minutes)
    rich=pd.DataFrame({k:raw[k] for k in ['taker_buy_volume','trades']},index=pd.to_datetime(ts,unit='ms',utc=True)).resample(f'{spec.timeframe_minutes}min',origin='epoch').sum()
    bars=bars.join(rich);step=spec.timeframe_minutes*60000
    interval=f'{spec.timeframe_minutes}m' if spec.timeframe_minutes<60 else ('1h' if spec.timeframe_minutes==60 else '4h')
    rows=[]
    for t,r in bars.iterrows():
        start=int(t.timestamp()*1000)
        rows.append([start,r.open,r.high,r.low,r.close,r.volume,start+step-1,0,int(r.trades),r.taker_buy_volume,0,0])
    with SingleProcess(dbpath):
        store=Store(dbpath)
        try:
            if store.get('binding') is not None:raise ValueError('seed only a new/unbound state database; never replace a live cache or reset risk')
            with store.transaction():
                count=store.put_bars(settings.symbol,interval,rows,now)
                receipt={'symbol':settings.symbol,'interval':interval,'source_sha256':expected,'first_bar_ms':int(bars.index[0].timestamp()*1000),'last_bar_ms':int(bars.index[-1].timestamp()*1000),'bars_added':count,'not_a_live_trade':True}
                store.set('history_seed',receipt)
            return receipt
        finally:store.close()

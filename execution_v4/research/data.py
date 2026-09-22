from __future__ import annotations
import hashlib
import numpy as np
from .simulator import COLS,validate_data

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
    return h.hexdigest()

def load(path):
    with np.load(path,allow_pickle=False) as z:raw={k:z[k] for k in z.files}
    ts=(raw['timestamp']//1000).astype(np.int64)
    if not np.all(np.diff(ts)==60):raise ValueError('missing or duplicate trade minutes')
    if not raw['funding_verified'].all():raise ValueError('unverified funding history')
    m=np.column_stack([raw[k] for k in COLS]).astype(float)
    missing=np.flatnonzero(~np.isfinite(m[:,5:9]).all(axis=1))
    for i in missing:
        previous=m[i-1,8];lo=raw['missing_mark_15m_low'][i];hi=raw['missing_mark_15m_high'][i]
        if not np.isfinite(lo+hi):lo=min(raw['low'][i],previous)*.95;hi=max(raw['high'][i],previous)*1.05
        m[i,5]=previous;m[i,8]=previous;m[i,6]=max(hi,previous);m[i,7]=min(lo,previous)
    validate_data(m,ts)
    return np.ascontiguousarray(m),ts,raw,missing

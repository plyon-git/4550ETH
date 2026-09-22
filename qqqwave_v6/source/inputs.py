from pathlib import Path
import hashlib
import numpy as np,pandas as pd

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def daily_crypto(raw,iv_path=None):
    ts=raw['timestamp']
    if not len(ts)%1440==0 or ts[0]%86400000 or not np.all(np.diff(ts)==60000):raise ValueError('complete UTC minute days required')
    idx=pd.to_datetime(ts[::1440],unit='ms',utc=True)
    f=pd.DataFrame({'open':raw['open'][::1440],'high':raw['high'].reshape(-1,1440).max(axis=1),
        'low':raw['low'].reshape(-1,1440).min(axis=1),'close':raw['close'][1439::1440],
        'volume':raw['volume'].reshape(-1,1440).sum(axis=1)},index=idx)
    if iv_path is not None:
        iv=pd.read_csv(iv_path);iv['available_ms']=iv.timestamp+86400000+60000
        r=pd.merge_asof(pd.DataFrame({'origin':ts[::1440]}),iv[['available_ms','close']],left_on='origin',right_on='available_ms',direction='backward',tolerance=172800000)
        f['iv_daily_sigma']=r.close.to_numpy()/100/np.sqrt(365)
        f['iv_available_ms']=r.available_ms.to_numpy()
    return f

def daily_equity(path):
    f=pd.read_csv(path)
    f.index=pd.to_datetime(f.pop('timestamp'),unit='s',utc=True)
    return f

def load_crypto(path):
    with np.load(path,allow_pickle=False) as z:raw={k:z[k] for k in z.files}
    ts=(raw['timestamp']//1000).astype('int64')
    if not np.all(raw['funding_verified']):raise ValueError('unverified funding')
    m=np.column_stack([raw[k] for k in ['open','high','low','close','volume','mark_open','mark_high','mark_low','mark_close','funding_rate']])
    missing=np.flatnonzero(~np.isfinite(m[:,5:9]).all(axis=1))
    for i in missing:
        previous=m[i-1,8];low=raw['missing_mark_15m_low'][i];high=raw['missing_mark_15m_high'][i]
        if not np.isfinite(low+high):low=min(raw['low'][i],previous)*.95;high=max(raw['high'][i],previous)*1.05
        m[i,5]=m[i,8]=previous;m[i,6]=max(high,previous);m[i,7]=min(low,previous)
    if not np.isfinite(m).all():raise ValueError('nonfinite execution inputs')
    return np.ascontiguousarray(m),ts,raw,missing

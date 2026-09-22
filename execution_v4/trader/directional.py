"""Causal order-flow/price features and portable gradient-boosted return models.
JSON numerical trees are trained only on fully matured labels. No repainting.
"""
from __future__ import annotations
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
FEATURE_VERSION=1

def rich_features(b):
    required=['open','high','low','close','volume','taker_buy_volume','trades']
    if not all(k in b for k in required):raise ValueError('actual taker volume and trade counts required for directional ML')
    c,h,l,v=[b[k].astype(float) for k in ['close','high','low','volume']]
    if not np.isfinite(b[required]).all().all():raise ValueError('nonfinite order-flow input')
    if (v<=0).any() or (b.trades<=0).any() or ((b.taker_buy_volume<0)|(b.taker_buy_volume>v*1.000001)).any():raise ValueError('invalid order-flow input')
    ret=np.log(c/c.shift(1));tr=pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    atr=(tr.ewm(span=32,adjust=False).mean()/c).clip(.0005,.10)
    f=pd.DataFrame(index=b.index)
    for n in [1,2,4,8,16,24,72,168]:f[f'return_{n}_atr']=np.log(c/c.shift(n))/atr
    for n in [24,72,168]:
        f[f'ema_distance_{n}']=(c/c.ewm(span=n,adjust=False).mean()-1)/atr
        f[f'volume_ratio_{n}']=v/v.rolling(n,min_periods=n).mean()
    flow=b.taker_buy_volume/v*2-1
    f['taker_imbalance']=flow;f['taker_ema8']=flow.ewm(span=8,adjust=False).mean();f['taker_ema24']=flow.ewm(span=24,adjust=False).mean()
    f['body_atr']=(c/b.open-1)/atr;f['close_location']=(c-l)/(h-l+1e-12);f['range_atr']=(h-l)/c/atr
    f['atr_fraction']=atr;f['volatility48']=ret.rolling(48).std()/atr
    size=v/b.trades;f['trade_size_ratio']=size/size.rolling(72).mean()
    for period,value in [(24,b.index.hour),(7,b.index.dayofweek)]:
        f[f'sin_{period}']=np.sin(2*np.pi*value/period);f[f'cos_{period}']=np.cos(2*np.pi*value/period)
    return f

def aggregate_rich(raw,minutes=60):
    from .strategy import aggregate_minutes
    b=aggregate_minutes(raw,minutes)
    x=pd.DataFrame({k:raw[k] for k in ['taker_buy_volume','trades']},index=pd.to_datetime(raw['timestamp'],unit='ms',utc=True))
    x=x.resample(f'{minutes}min',origin='epoch').sum();return b.join(x)

def fit(bars,cutoff_ms,horizon=12,lookback_days=1095):
    from sklearn.ensemble import HistGradientBoostingRegressor
    if not isinstance(horizon,int) or not 1<=horizon<=168 or lookback_days<180:raise ValueError('invalid directional learning horizon/window')
    if not isinstance(bars.index,pd.DatetimeIndex) or bars.index.tz is None or not np.all(np.diff(bars.index.asi8)==3600000000000):raise ValueError('directional model requires continuous timezone-aware hourly bars')
    f=rich_features(bars);ts=bars.index.asi8//1_000_000;step=3600000
    y=np.log(bars.close.shift(-horizon)/bars.open.shift(-1))/f.atr_fraction
    mature=ts+(horizon+1)*step
    use=(ts>=cutoff_ms-lookback_days*86400000)&(mature<=cutoff_ms)&np.isfinite(y)&np.isfinite(f).all(axis=1)
    if use.sum()<3000:raise ValueError('insufficient matured directional regression labels')
    model=HistGradientBoostingRegressor(loss='squared_error',max_iter=100,learning_rate=.05,max_leaf_nodes=15,max_depth=5,min_samples_leaf=128,l2_regularization=20,early_stopping=False,random_state=20260922)
    x=f.loc[use].to_numpy();model.fit(x,y[use].clip(-8,8))
    trees=[]
    for stage in model._predictors:
        assert len(stage)==1
        nodes=stage[0].nodes
        if nodes['is_categorical'].any():raise ValueError('categorical model cannot be exported by this numerical schema')
        trees.append({k:nodes[k].tolist() for k in ['value','feature_idx','num_threshold','left','right','is_leaf']})
    doc={'schema':1,'model_type':'directional_hgb_return','feature_version':FEATURE_VERSION,'features':list(f.columns),'baseline':float(model._baseline_prediction.ravel()[0]),'trees':trees,
         'timeframe_minutes':60,'horizon_bars':horizon,'trained_at_cutoff_ms':int(cutoff_ms),'max_label_maturity_ms':int(mature[use].max()),'samples':int(use.sum()),'valid_until_ms':int(cutoff_ms+100*86400000),
         'training_parameters':model.get_params(),'label':'log(next-horizon close / next-bar open) divided by known current ATR fraction, clipped +/-8 on training only; not realized execution return'}
    np.testing.assert_allclose(predict(doc,f.loc[use].iloc[::7]),model.predict(x[::7]),rtol=1e-10,atol=1e-10)
    return doc

def predict(model,frame):
    if model['schema']!=1 or model['feature_version']!=FEATURE_VERSION or model['model_type']!='directional_hgb_return':raise ValueError('unsupported numerical model schema')
    x=frame[model['features']].to_numpy(dtype=float)
    if not np.isfinite(x).all():raise ValueError('nonfinite directional features')
    out=np.full(len(x),float(model['baseline']))
    for tree in model['trees']:
        nodes=np.zeros(len(x),dtype=np.int64);active=np.ones(len(x),bool)
        leaf=np.asarray(tree['is_leaf'],bool);feat=np.asarray(tree['feature_idx'],int);threshold=np.asarray(tree['num_threshold'],float);left=np.asarray(tree['left'],int);right=np.asarray(tree['right'],int);value=np.asarray(tree['value'],float)
        for _ in range(64):
            idx=np.flatnonzero(active)
            if not len(idx):break
            at=nodes[idx];done=leaf[at];out[idx[done]]+=value[at[done]];active[idx[done]]=False
            idx=idx[~done];at=nodes[idx]
            if len(idx):nodes[idx]=np.where(x[idx,feat[at]]<=threshold[at],left[at],right[at])
        else:raise ValueError('tree depth bound exceeded')
    if not np.isfinite(out).all():raise ValueError('nonfinite model output')
    return out

def load_verified(path,digest,now_ms):
    p=Path(path)
    if p.stat().st_size>10_000_000:raise ValueError('model exceeds size bound')
    data=p.read_bytes()
    if not digest or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('directional model identity mismatch')
    doc=json.loads(data)
    if not doc['max_label_maturity_ms']<=doc['trained_at_cutoff_ms']<=now_ms<=doc['valid_until_ms']:raise ValueError('stale, future or leaking model')
    return doc

def decision(model,bars,threshold_r,cost_fraction=.0014):
    f=rich_features(bars).iloc[[-1]];value=float(predict(model,f)[0]);atr=float(f.atr_fraction.iloc[0])
    side=int(np.sign(value)) if int(bars.index[-1].timestamp()*1000)>=model['trained_at_cutoff_ms'] and abs(value)>=threshold_r and abs(value)*atr>=1.5*cost_fraction else 0
    return side,atr,value

"""Portable logistic meta-filter. JSON weights, not executable pickle.
Proxy labels measure direction-adjusted horizon return after costs, not realized exits.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd
from dataclasses import asdict
from .strategy import closed_bar_features,StrategySpec
FEATURES=['signal','atr_fraction','volume_ratio','rsi7','ema_distance_atr','return_1','return_4','return_16']

def feature_matrix(frame):
    x=frame[FEATURES].to_numpy(dtype=float)
    if not np.isfinite(x).all():raise ValueError('nonfinite model inputs')
    return x

def fit_model(bars,spec,cutoff_ms,horizon_bars=16,lookback_days=1095,cost_fraction=.0014):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    if horizon_bars<1 or lookback_days<90 or cost_fraction<0:raise ValueError('invalid learning parameters')
    spec.validate();feat=closed_bar_features(bars,spec);step=spec.timeframe_minutes*60000
    times=bars.index.asi8//1_000_000;entry=bars.open.shift(-1)
    exitprice=bars.close.shift(-horizon_bars)
    label_mature=times+(horizon_bars+1)*step
    y=(feat.signal*(exitprice/entry-1)>cost_fraction).astype(int)
    use=(feat.signal!=0)&(times>=cutoff_ms-lookback_days*86400000)&(label_mature<=cutoff_ms)&exitprice.notna()
    selected=feat.loc[use,FEATURES]
    if len(selected)<100 or y[use].nunique()<2:raise ValueError('insufficient matured directional training labels')
    x=feature_matrix(selected);scaler=StandardScaler().fit(x)
    model=LogisticRegression(C=.1,solver='lbfgs',max_iter=1000,random_state=20260922)
    model.fit(scaler.transform(x),y[use])
    doc={'schema':1,'model_type':'logistic_meta_filter','strategy_identity':spec.identity,
         'strategy':asdict(spec),'features':FEATURES,'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
         'coefficient':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),
         'trained_at_cutoff_ms':int(cutoff_ms),'max_label_maturity_ms':int(label_mature[use].max()),
         'earliest_training_bar_ms':int(times[use].min()),'samples':int(use.sum()),'positive_labels':int(y[use].sum()),
         'horizon_bars':horizon_bars,'lookback_days':lookback_days,'cost_fraction':cost_fraction,
         'label':'directional next-open to fixed-horizon-close return exceeds cost; not realized stop/target win',
         'valid_until_ms':int(cutoff_ms+100*86400000),'class_weight':None,'regularization_C':.1}
    expected=model.predict_proba(scaler.transform(x))[:,1]
    np.testing.assert_allclose(probabilities(doc,selected),expected,rtol=1e-12,atol=1e-12)
    return doc

def probabilities(model,frame):
    if model['features']!=FEATURES or model['schema']!=1:raise ValueError('unsupported model schema')
    x=feature_matrix(frame);scale=np.array(model['scale'],float)
    if len(scale)!=len(FEATURES) or not np.isfinite(scale).all() or (scale<=0).any():raise ValueError('invalid model scaling')
    z=((x-np.array(model['mean'],float))/scale)@np.array(model['coefficient'],float)+float(model['intercept'])
    if not np.isfinite(z).all():raise ValueError('invalid model coefficients')
    return 1/(1+np.exp(-np.clip(z,-700,700)))

def predict_probability(path,row,spec,now_ms,expected_sha256=None):
    p=Path(path)
    if p.stat().st_size>1_000_000:raise ValueError('model JSON too large')
    data=p.read_bytes()
    if expected_sha256 is None or hashlib.sha256(data).hexdigest()!=expected_sha256:raise ValueError('model hash missing or mismatched')
    m=json.loads(data)
    if m['strategy_identity']!=spec.identity:raise ValueError('model belongs to another strategy')
    if m['max_label_maturity_ms']>m['trained_at_cutoff_ms'] or now_ms<m['trained_at_cutoff_ms'] or now_ms>m['valid_until_ms']:raise ValueError('future, leaking or stale model')
    if hasattr(row.name,'timestamp') and int(row.name.timestamp()*1000)<m['trained_at_cutoff_ms']:return 0.
    return float(probabilities(m,pd.DataFrame([row]))[0])

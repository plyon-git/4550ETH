"""Scheduled causal refits using cached completed bars and immutable JSON weights."""
from __future__ import annotations
from pathlib import Path
import hashlib,json,os
import pandas as pd

def active_model(store,settings):
    return store.get('active_model',{'path':settings.ml_model_path,'sha256':settings.ml_model_sha256})

def maybe_refit(store,bars,spec,settings,now_ms):
    if not settings.ml_model_path:return None
    active=active_model(store,settings);path=Path(active['path'])
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=active['sha256']:raise ValueError('active model hash mismatch')
    doc=json.loads(payload)
    if doc['max_label_maturity_ms']>doc['trained_at_cutoff_ms'] or doc['trained_at_cutoff_ms']>now_ms:raise ValueError('model contains future training information')
    if not settings.auto_refit:return active
    anchor=int(pd.Timestamp(settings.refit_anchor_utc).timestamp()*1000);step=settings.refit_weeks*7*86400000
    if now_ms<anchor:raise ValueError('refit anchor lies in the future')
    activation_time=min(now_ms,int(bars.index[-1].timestamp()*1000))
    if activation_time<anchor:return active
    cutoff=anchor+((activation_time-anchor)//step)*step
    if doc['trained_at_cutoff_ms']>=cutoff:return active
    if int(bars.index[-1].timestamp()*1000)+spec.timeframe_minutes*60000<cutoff:raise ValueError('completed bar cache does not cover refit cutoff')
    if spec.family=='ml_directional':
        from .directional import fit
        new=fit(bars,cutoff,doc['horizon_bars'])
    else:
        from .learning import fit_model
        new=fit_model(bars,spec,cutoff,doc['horizon_bars'])
    data=(json.dumps(new,sort_keys=True,separators=(',',':'))+'\n').encode();sha=hashlib.sha256(data).hexdigest()
    directory=store.path.parent/'models';directory.mkdir(parents=True,exist_ok=True)
    target=directory/f'{cutoff}_{sha}.json';tmp=directory/(target.name+'.tmp')
    with tmp.open('wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    os.replace(tmp,target)
    saved={'path':str(target.resolve()),'sha256':sha,'cutoff_ms':cutoff,'max_label_maturity_ms':new['max_label_maturity_ms'],'samples':new['samples']}
    with store.transaction():
        store.set('active_model',saved);store.event('CAUSAL_MODEL_REFIT',saved)
    return saved

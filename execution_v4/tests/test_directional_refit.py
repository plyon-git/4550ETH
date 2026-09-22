from dataclasses import replace
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd,pytest
from trader.directional import rich_features,fit,predict,load_verified,decision
from trader.strategy import StrategySpec
from trader.config import Settings,load_config
from trader.store import Store
from trader.refit import maybe_refit

def bars(n=5000):
    rng=np.random.default_rng(2717);c=2000*np.exp(np.cumsum(rng.normal(0,.004,n)));o=np.r_[c[0],c[:-1]];v=rng.uniform(100,200,n)
    return pd.DataFrame({'open':o,'close':c,'high':np.maximum(o,c)*1.004,'low':np.minimum(o,c)*.996,'volume':v,'taker_buy_volume':v*rng.uniform(.2,.8,n),'trades':rng.integers(100,400,n)},index=pd.date_range('2024-01-01',periods=n,freq='h',tz='UTC'))

def test_directional_features_prefix_and_future_perturbation():
    b=bars();full=rich_features(b);prefix=rich_features(b.iloc[:2000]);pd.testing.assert_frame_equal(prefix,full.iloc[:2000])
    altered=b.copy();altered.iloc[2000:,altered.columns.get_loc('close')]*=1.2
    pd.testing.assert_frame_equal(full.iloc[:2000],rich_features(altered).iloc[:2000])

def test_numerical_trees_fit_parity_maturity_and_future_independence(tmp_path):
    b=bars();cut=int(b.index[4500].timestamp()*1000);doc=fit(b,cut,4)
    assert doc['max_label_maturity_ms']<=cut and doc['samples']>=3000
    changed=b.copy();changed.iloc[4500:,:4]*=1.4
    assert doc==fit(changed,cut,4)
    p=tmp_path/'model.json';p.write_text(json.dumps(doc));sha=hashlib.sha256(p.read_bytes()).hexdigest()
    recovered=load_verified(p,sha,cut);assert np.isfinite(predict(recovered,rich_features(b).iloc[-5:])).all()
    with pytest.raises(ValueError):load_verified(p,'0'*64,cut)
    with pytest.raises(ValueError):load_verified(p,sha,doc['valid_until_ms']+1)
    with pytest.raises(ValueError):load_verified(p,sha,cut-1)

@pytest.mark.parametrize('h',[-1,0,169,1.5])
def test_invalid_training_horizons_rejected(h):
    with pytest.raises(ValueError):fit(bars(),1780000000000,h)

def test_no_model_fallback_for_directional_strategy(tmp_path):
    p=tmp_path/'config.json';p.write_text(json.dumps({'strategy':{'family':'ml_directional','timeframe_minutes':60}}))
    with pytest.raises(ValueError):load_config(p)

def test_scheduled_refit_preserves_journal_and_exact_cutoff(tmp_path,monkeypatch):
    b=bars();anchor=int(b.index[4000].timestamp()*1000);oldcut=anchor-13*7*86400000
    path=tmp_path/'initial.json';doc={'max_label_maturity_ms':oldcut,'trained_at_cutoff_ms':oldcut,'horizon_bars':4};path.write_text(json.dumps(doc));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    fake={'max_label_maturity_ms':anchor-3600000,'trained_at_cutoff_ms':anchor,'horizon_bars':4,'samples':4000}
    calls=[]
    def train(history,cut,h):calls.append((cut,h));return fake
    monkeypatch.setattr('trader.directional.fit',train)
    settings=Settings(ml_model_path=str(path),ml_model_sha256=sha,auto_refit=True,refit_anchor_utc=pd.Timestamp(anchor,unit='ms',tz='UTC').isoformat())
    store=Store(tmp_path/'state.sqlite');store.set('risk',{'sentinel':123})
    try:
        saved=maybe_refit(store,b,StrategySpec(family='ml_directional',timeframe_minutes=60),settings,anchor+3600000)
        assert saved['cutoff_ms']==anchor and calls==[(anchor,4)] and store.get('risk')=={'sentinel':123}
        assert Path(saved['path']).is_file()
        maybe_refit(store,b,StrategySpec(family='ml_directional',timeframe_minutes=60),settings,anchor+7200000)
        assert len(calls)==1
    finally:store.close()

def test_refit_does_not_backdate_to_bar_before_cutoff(tmp_path,monkeypatch):
    b=bars();anchor=int(b.index[4000].timestamp()*1000);oldcut=anchor-13*7*86400000
    path=tmp_path/'initial.json';doc={'max_label_maturity_ms':oldcut,'trained_at_cutoff_ms':oldcut,'horizon_bars':4};path.write_text(json.dumps(doc));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    settings=Settings(ml_model_path=str(path),ml_model_sha256=sha,auto_refit=True,refit_anchor_utc=pd.Timestamp(anchor,unit='ms',tz='UTC').isoformat())
    monkeypatch.setattr('trader.directional.fit',lambda *a,**k:pytest.fail('must retain previous fold for the bar before cutoff'))
    store=Store(tmp_path/'state.sqlite')
    try:
        got=maybe_refit(store,b.iloc[:4000],StrategySpec(family='ml_directional',timeframe_minutes=60),settings,anchor+1000)
        assert got['sha256']==sha
    finally:store.close()

def test_directional_feature_builder_has_no_untrained_buy_fallback():
    from trader.strategy import closed_bar_features
    assert not closed_bar_features(bars(),StrategySpec(family='ml_directional',timeframe_minutes=60)).signal.any()

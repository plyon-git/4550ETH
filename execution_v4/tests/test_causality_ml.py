from dataclasses import replace
import json,hashlib
import numpy as np,pandas as pd,pytest
from trader.strategy import StrategySpec,closed_bar_features,minute_signals
from trader.learning import fit_model,probabilities,predict_probability

def bars(n=12000):
    rng=np.random.default_rng(83);c=2000*np.exp(np.cumsum(rng.normal(0,.007,n)))
    op=np.r_[c[0],c[:-1]];hi=np.maximum(op,c)*1.002;lo=np.minimum(op,c)*.998
    return pd.DataFrame({'open':op,'high':hi,'low':lo,'close':c,'volume':rng.uniform(50,200,n)},index=pd.date_range('2021-01-01',periods=n,freq='h',tz='UTC'))

@pytest.mark.parametrize('family',['breakout','momentum','pullback','reversal'])
@pytest.mark.parametrize('direction',['both','long','short'])
def test_signal_prefix_invariant(family,direction):
    b=bars(1400);s=StrategySpec(family=family,direction=direction,timeframe_minutes=60,lookback=12,trend_span=200)
    full=closed_bar_features(b,s);prefix=closed_bar_features(b.iloc[:1117],s)
    pd.testing.assert_frame_equal(full.iloc[:1117],prefix)
    changed=b.copy();changed.iloc[1117:]=changed.iloc[1117:]*1.5
    pd.testing.assert_frame_equal(full.iloc[:1117],closed_bar_features(changed,s).iloc[:1117])

def test_signals_available_only_after_complete_frame():
    n=15000;rng=np.random.default_rng(93);c=2000*np.exp(np.cumsum(rng.normal(0,.001,n)))
    ts=np.arange(n)*60000+1609459200000;op=np.r_[c[0],c[:-1]]
    raw={'timestamp':ts,'open':op,'high':np.maximum(op,c)*1.0001,'low':np.minimum(op,c)*.9999,'close':c,'volume':rng.uniform(10,100,n)}
    sig,stop,_=minute_signals(raw,StrategySpec(lookback=12,volume_multiple=0))
    ix=np.flatnonzero(sig);assert len(ix)>0
    assert ((ts[ix]+60000)%(15*60000)==0).all()
    short={k:v[:14177] for k,v in raw.items()};s2,st2,_=minute_signals(short,StrategySpec(lookback=12,volume_multiple=0))
    np.testing.assert_array_equal(sig[:14175],s2[:14175]);assert s2[-2:].sum()==0

def test_ml_uses_only_matured_labels_and_portable_probabilities(tmp_path):
    b=bars();s=StrategySpec(family='momentum',timeframe_minutes=60,lookback=12,volume_multiple=0,minimum_price=0)
    cutoff=int(b.index[9500].timestamp()*1000);m=fit_model(b,s,cutoff,horizon_bars=8)
    assert m['max_label_maturity_ms']<=cutoff and m['samples']>=100
    changed=b.copy();changed.iloc[9500:]*=3
    m2=fit_model(changed,s,cutoff,horizon_bars=8)
    assert m['coefficient']==m2['coefficient'] and m['mean']==m2['mean']
    p=tmp_path/'model.json';p.write_text(json.dumps(m));h=hashlib.sha256(p.read_bytes()).hexdigest()
    row=closed_bar_features(b,s).iloc[9600];prob=predict_probability(p,row,s,cutoff+1000,h)
    assert 0<=prob<=1
    with pytest.raises(ValueError):predict_probability(p,row,s,cutoff-1,h)
    with pytest.raises(ValueError):predict_probability(p,row,s,m['valid_until_ms']+1,h)
    with pytest.raises(ValueError):predict_probability(p,row,replace(s,target_r=2),cutoff+1000,h)
    with pytest.raises(ValueError):predict_probability(p,row,s,cutoff+1000,'0'*64)

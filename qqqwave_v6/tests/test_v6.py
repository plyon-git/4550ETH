import json
from dataclasses import replace
from pathlib import Path
import numpy as np,pandas as pd,pytest
from source.surface import SurfaceSpec,build_surface,event_evidence,event_summary
from source.trades import TradeSpec,bar_view,signals,make_config,simulate
from source.reporting import independent
from source.engine import Config

def daily(n=500):
    rng=np.random.default_rng(97);c=100*np.exp(np.cumsum(rng.normal(0,.008,n)));o=np.r_[100,c[:-1]]
    return pd.DataFrame({'open':o,'high':np.maximum(c,o)*1.005,'low':np.minimum(c,o)*.995,'close':c,
       'volume':10000.,'iv_daily_sigma':.015},index=pd.date_range('2020-01-01',periods=n,tz='UTC'))

@pytest.mark.parametrize('h',[1,5])
@pytest.mark.parametrize('matching',['all','weekday'])
@pytest.mark.parametrize('scale',['percent','realized','iv_scaled'])
def test_surface_has_no_future_dependency(h,matching,scale):
    data=daily();spec=SurfaceSpec(horizon=h,matching=matching,scale=scale)
    full=build_surface(data,spec);cut=350
    prefix=build_surface(data.iloc[:cut],spec)
    pd.testing.assert_frame_equal(full.iloc[:cut],prefix)
    changed=data.copy();changed.iloc[cut:,:4]*=1.8
    pd.testing.assert_frame_equal(full.iloc[:cut],build_surface(changed,spec).iloc[:cut])
    valid=full.sample_count>0
    assert (full.loc[valid,'latest_matured_session_utc']<full.index[valid]).all()

@pytest.mark.parametrize('matching,count',[('all',196),('weekday',28)])
def test_count_definition(matching,count):
    s=build_surface(daily(),SurfaceSpec(matching=matching))
    assert s.sample_count.iloc[-1]==count

def test_iv_not_silently_replaced():
    with pytest.raises(ValueError):build_surface(daily().drop(columns='iv_daily_sigma'),SurfaceSpec(scale='iv_scaled'))

def test_intraday_revisions_do_not_move_origin_levels():
    d=daily();a=build_surface(d);d.iloc[-1,d.columns.get_indexer(['open','high','low','close'])]*=2
    b=build_surface(d)
    for col in ['reference_price','mean_low_proxy','mean_high_proxy','low_q0.973684']:
        assert a[col].iloc[-1]==b[col].iloc[-1]

def test_screenshot_rank_candidate_matches_every_visible_row():
    data=json.loads((Path(__file__).resolve().parents[1]/'SCREENSHOT_ANALYSIS.json').read_text())
    assert len(data['count_rows'])==25
    assert all(x['adjusted_matches_rounding'] for x in data['count_rows'])
    assert data['count_rows'][0]['raw_count_percent']!=data['count_rows'][0]['displayed_percent']

def synthetic():
    n=30;ts=1577836800+np.arange(n)*60;m=np.zeros((n,10))
    m[:,0:4]=[100,100.5,99.5,100];m[:,4]=1e6;m[:,5:9]=m[:,0:4]
    sig=np.zeros(n,np.int8);sig[4]=-1;stop=np.full(n,np.nan);stop[4]=105
    target=np.full(n,np.nan);target[4]=95;expiry=np.zeros(n,np.int64);expiry[4]=ts[-1]+60
    return m,ts,(sig,stop,target,expiry),Config(fee_bps=0,slippage_bps=0,participation=1,minimum_notional=1,price_tick=.01)

def test_stop_wins_same_bar_ambiguity_and_audit():
    m,ts,sg,cfg=synthetic();m[5,1:3]=[106,94];m[5,6:8]=[106,94]
    o=simulate(m,ts,sg,cfg,0,len(ts));assert len(o[3])==1 and o[3][0,12]==1 and o[3][0,10]<0
    assert independent(o,m,ts,0,len(ts),cfg,sg)['passed']

def test_later_target_touch_does_not_reverse_a_stopped_loss():
    m,ts,sg,cfg=synthetic();m[5,1]=m[5,6]=106;m[6,2]=m[6,7]=94
    o=simulate(m,ts,sg,cfg,0,len(ts));assert o[3][0,10]<0 and o[3][0,1]==5
    assert m[6,2]<=sg[2][4]

def test_absolute_stops_remain_fixed():
    m,ts,sg,cfg=synthetic();m[5,0:4]=[102,104,101,103];m[5,5:9]=m[5,0:4]
    m[6,0:4]=[103,106,102,103];m[6,5:9]=m[6,0:4]
    o=simulate(m,ts,sg,cfg,0,len(ts));assert o[3][0,4]==102 and o[3][0,5]==105

def test_gap_through_stop_skips_entry():
    m,ts,sg,cfg=synthetic();m[5,0:4]=[106,107,106,106];m[5,5:9]=m[5,0:4]
    assert len(simulate(m,ts,sg,cfg,0,len(ts))[3])==0

def test_forecast_deadline_closes_position():
    m,ts,sg,cfg=synthetic();sg[3][4]=ts[10]
    o=simulate(m,ts,sg,cfg,0,len(ts));assert o[3][0,1]==10 and o[3][0,12]==4

def test_no_post_expiry_entry():
    m,ts,sg,cfg=synthetic();sg[3][4]=ts[5]
    assert len(simulate(m,ts,sg,cfg,0,len(ts))[3])==0

def test_costs_change_net_pnl():
    m,ts,sg,cfg=synthetic();m[6,2]=m[6,7]=94
    a=simulate(m,ts,sg,cfg,0,len(ts));b=simulate(m,ts,sg,replace(cfg,fee_bps=5,slippage_bps=2),0,len(ts))
    assert b[3][0,10]<a[3][0,10]

def test_short_hit_can_be_unprofitable_after_costs():
    m,ts,sg,cfg=synthetic();sg[2][4]=99.98
    o=simulate(m,ts,sg,replace(cfg,fee_bps=5,slippage_bps=0),0,len(ts))
    assert o[3][0,12]==2 and o[3][0,10]<0

def test_independent_audit_detects_ledger_damage():
    m,ts,sg,cfg=synthetic();out=simulate(m,ts,sg,cfg,0,len(ts));out[3][0,10]+=10
    with pytest.raises(AssertionError):independent(out,m,ts,0,len(ts),cfg,sg)

def test_panel_samples_reconcile_without_current_session_ohlc():
    from panel import snapshot
    d=daily();spec=SurfaceSpec();m,t,s=snapshot(d,spec)
    assert m['sample_count']==28 and len(t)==101
    assert t.low_touch_empirical_frequency.is_monotonic_increasing
    assert t.high_touch_empirical_frequency.is_monotonic_decreasing
    d.iloc[-1,d.columns.get_indexer(['open','high','low','close'])]*=3
    m2,t2,s2=snapshot(d,spec)
    assert m==m2
    pd.testing.assert_frame_equal(t,t2);pd.testing.assert_frame_equal(s,s2)

def test_panel_rejects_unknown_origin():
    from panel import snapshot
    with pytest.raises(ValueError):snapshot(daily(),SurfaceSpec(),'2030-01-01T00:00:00Z')

def test_panel_does_not_apply_unverified_vendor_rank_rule():
    from panel import snapshot
    meta,table,trials=snapshot(daily(),SurfaceSpec())
    np.testing.assert_allclose(table.low_touch_empirical_frequency,table.low_at_or_below_count/len(trials))
    assert meta['vendor_rank_adjustment_applied'] is False

def test_bad_daily_envelope_rejected():
    d=daily();d.iloc[-1,d.columns.get_loc('high')]=1
    with pytest.raises(ValueError):build_surface(d)

def test_short_history_rejected():
    with pytest.raises(ValueError):build_surface(daily(20))

def test_bootstrap_refuses_overwriting_an_unexpected_engine(tmp_path):
    import shutil
    from bootstrap_engine import build,ROOT
    (tmp_path/'source').mkdir()
    shutil.copy2(ROOT/'source/engine_v5_original.py',tmp_path/'source/engine_v5_original.py')
    build(tmp_path)
    (tmp_path/'source/engine.py').write_text('modified')
    with pytest.raises(ValueError):build(tmp_path)

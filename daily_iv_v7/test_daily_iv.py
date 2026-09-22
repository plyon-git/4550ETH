"""Offline causal, clock, order-count and accounting tests. No exchange access."""
import hashlib,json
from dataclasses import replace
from pathlib import Path
import numpy as np,pandas as pd,pytest
from core import *
from research import audit,summarize

def synthetic(days=3):
    n=days*1440;ts=1609459200000+np.arange(n)*60000;m=np.zeros((n,10))
    m[:,:4]=[100,100.5,99.5,100];m[:,4]=100000.;m[:,5:9]=m[:,:4]
    sg=np.ones(days,np.int8);sl=np.full(days,98.);tp=np.full(days,103.);en=np.full(days,2,np.int64)
    return ts,m,np.zeros(n,bool),sg,sl,tp,en

def sim(data,side=None,fee=.0005,slip=.0002,risk=.01):
    ts,m,miss,sg,sl,tp,en=data
    if side is not None:sg=sg*side
    return evaluate(m,miss,sg,sl,tp,en,0,len(sg),risk,5,fee,slip,.001,.01,20.)

def market(days=350):
    rng=np.random.default_rng(20260922);n=days*1440;ts=1609459200000+np.arange(n)*60000
    c=100*np.exp(np.cumsum(rng.normal(0,.0001,n)));o=np.r_[100,c[:-1]]
    m=np.zeros((n,10));m[:,0]=o;m[:,1]=np.maximum(o,c)*1.0001;m[:,2]=np.minimum(o,c)*.9999;m[:,3]=c;m[:,4]=10000
    m[:,5:9]=m[:,:4]
    iv=pd.DataFrame({'timestamp':ts[::1440]-DAY,'open':60.,'high':62.,'low':58.,'close':60.+np.sin(np.arange(days)/12)})
    return ts,m,iv

def test_daily_is_365_not_252():
    ts,m,iv=market();d=daily_inputs(ts,m,iv)
    np.testing.assert_allclose(d.sigma,d.iv_close/100/np.sqrt(365))

def test_latest_IV_is_previous_candle_only():
    ts,m,iv=market();d=daily_inputs(ts,m,iv)
    assert (d.iv_candle_ms.to_numpy()==ts[::1440]-DAY).all()
    assert (d.iv_available_ms.to_numpy()==ts[::1440]+60000).all()
    assert (d.iv_available_ms<ts[::1440]+120000).all()

@pytest.mark.parametrize('rule',RULES[:12])
def test_future_changes_do_not_repaint_scheduled_rules(rule):
    ts,m,iv=market();d=daily_inputs(ts,m,iv);p=Policy(rule=rule);a=decision_arrays(d,p)
    cut=300;changed=m.copy();changed[cut*1440:,:4]*=2
    iv2=iv.copy();iv2.loc[iv2.timestamp>=ts[cut*1440],['open','high','low','close']]*=2
    b=decision_arrays(daily_inputs(ts,changed,iv2),p)
    for aa,bb in zip(a,b):np.testing.assert_allclose(aa[:cut],bb[:cut],equal_nan=True)

def test_original_day_future_high_low_not_in_its_forecast():
    ts,m,iv=market();a=daily_inputs(ts,m,iv);changed=m.copy();changed[-100,1]*=3
    b=daily_inputs(ts,changed,iv)
    for col in ['reference','sigma','history_up_mean','history_down_mean','return1','conditional_mean']:
        np.testing.assert_allclose(a[col],b[col],equal_nan=True)

def test_missing_IV_has_no_rv_fallback():
    ts,m,iv=market();iv=iv.drop(320);d=daily_inputs(ts,m,iv)
    assert np.isnan(d.iv_close.iloc[320]);assert decision_arrays(d,Policy())[0][320]==0

def test_one_trade_each_day_including_weekend_flat_same_day():
    data=synthetic(8);out=sim(data);ledger=out[1]
    assert len(ledger)==8 and len(np.unique(ledger[:,0]))==8
    assert (ledger[:,2]%1440==1439).all()
    assert (ledger[:,1]//1440==ledger[:,2]//1440).all()
    assert ledger[0,1]==2

def test_stop_before_target_ambiguous_candle_no_reentry():
    data=synthetic();data[1][10,1:3]=[104,97]
    out=sim(data);assert len(out[1])==3 and out[1][0,2]==10 and out[1][0,17]==1

def test_later_target_does_not_rewrite_earlier_stop():
    data=synthetic();data[1][10,2]=97;data[1][11,1]=105
    out=sim(data);assert out[1][0,17]==1 and out[1][0,13]<0 and out[1][0,2]==10

def test_overnight_and_final_minute_extremes_not_used_after_exit():
    data=synthetic();out=sim(data);data[1][1439,1]=1000;data[1][1439,2]=1
    after=sim(data);np.testing.assert_array_equal(out[1],after[1])

def test_fee_and_funding_reconciliation():
    data=synthetic();data[1][480,9]=.001
    out=sim(data);r=out[1][0]
    assert r[11]>0
    np.testing.assert_allclose(r[13],r[12]-r[9]-r[10]-r[11])
    np.testing.assert_allclose(out[0][-1],10000+out[1][:,13].sum())

def test_zero_cost_case_still_retains_funding():
    data=synthetic();data[1][480,9]=.001
    out=sim(data,fee=0,slip=0);r=out[1][0]
    assert r[9]==0 and r[10]==0 and r[11]>0 and r[13]<0

def test_gap_beyond_stop_skips_not_pads_trade_count():
    data=synthetic();data[1][2,0]=96
    out=sim(data);assert len(out[1])==2 and out[2][0]==2 and out[0][1]==out[0][0]

def test_low_volume_never_rounds_size_up():
    data=synthetic();data[1][1,4]=.01
    out=sim(data);assert len(out[1])==2 and out[2][0]==3

def test_collateral_flag_is_not_150_times_notional():
    data=synthetic();out=sim(data);assert out[1][:,16].max()<=5
    np.testing.assert_allclose(out[1][:,16],out[1][:,4]*out[1][:,5]/out[1][:,14])

def test_wall_confirmation_not_before_completed_5m_bar():
    ts,m,iv=market();d=daily_inputs(ts,m,iv);p=Policy(rule='wall_rejection',trigger_multiple=.15)
    side,sl,tp,en=wall_decisions(d,m,p);valid=en>0
    assert valid.any() and (en[valid]%5==0).all() and en[valid].min()>=5 and en[valid].max()<=1380

def test_conditioned_training_outcomes_mature():
    ts,m,iv=market();d=daily_inputs(ts,m,iv);last=d.conditional_mean.iloc[-1]
    m[-1,3]*=100;d2=daily_inputs(ts,m,iv)
    assert d2.conditional_mean.iloc[-1]==last

def test_ledger_audit_detects_damaged_pnl():
    ts,m,iv=market();d=daily_inputs(ts,m,iv);d.attrs['grid']=(.001,.01,20.);p=Policy(rule='long')
    miss=np.zeros(len(ts),bool);out=run_policy(m,miss,d,p,300,310)
    assert audit(out,ts,m,miss,d,p,300,310)['passed']
    out[1][0,13]+=1
    with pytest.raises(AssertionError):audit(out,ts,m,miss,d,p,300,310)

def test_stop_trigger_timestamp_is_audited_independently():
    ts,m,iv=market();d=daily_inputs(ts,m,iv);d.attrs['grid']=(.001,.01,20.);p=Policy(rule='long')
    miss=np.zeros(len(ts),bool);out=run_policy(m,miss,d,p,300,310)
    out[1][0,2]-=1
    with pytest.raises(AssertionError):audit(out,ts,m,miss,d,p,300,310)

def test_actual_IV_JSON_receipts_match_supplied_csv():
    path=Path(__file__).resolve().parent/'context'/'iv_data'
    for symbol in ['BTC','ETH']:
        iv,rec=verify_iv(path,symbol);assert len(iv)==1987 and len(rec['source_receipts'])==2

def test_five_year_duration_and_trade_count_not_pooled():
    dates=pd.date_range('2021-09-01','2026-09-01',tz='UTC');assert len(dates)-1==1826
    a=pd.Timestamp('2021-11-15',tz='UTC');b=pd.Timestamp('2026-08-31',tz='UTC');assert (b-a).days==1750

def test_adaptive_selection_ignores_unmatured_outcomes():
    from adaptive import choose_policies
    rng=np.random.default_rng(3);returns=rng.normal(0,.01,(8,500));days=pd.date_range('2020-01-01',periods=500,tz='UTC')
    a,_=choose_policies(returns,days,130,500,0)
    changed=returns.copy();changed[:,320:]=.1
    b,_=choose_policies(changed,days,130,500,0)
    np.testing.assert_array_equal(a[:321],b[:321])

def test_adaptive_selection_is_frozen_for_seven_days():
    from adaptive import choose_policies
    rng=np.random.default_rng(3);returns=rng.normal(0,.01,(8,500));days=pd.date_range('2020-01-01',periods=500,tz='UTC')
    chosen,records=choose_policies(returns,days,130,500,0)
    assert all((pd.Timestamp(r['decision_day'])-pd.Timestamp(r['latest_outcome_day'])).days==1 for r in records)
    for start in range(130,500,7):assert len(set(chosen[start:min(start+7,500)]))==1

def test_adaptive_selection_rejects_insufficient_history():
    from adaptive import choose_policies
    days=pd.date_range('2020-01-01',periods=100,tz='UTC')
    with pytest.raises(ValueError):choose_policies(np.zeros((3,100)),days,20,100,0)

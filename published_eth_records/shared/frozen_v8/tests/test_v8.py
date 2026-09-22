from pathlib import Path
import sys,hashlib,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
import numpy as np,pandas as pd,pytest
from core import *
from report import audit

def market(days=7):
    n=days*1440;ts=np.arange(n,dtype=np.int64)*60000+1577836800000
    m=np.zeros((n,10));m[:,:4]=[100,100.2,99.8,100];m[:,4]=100000;m[:,5:9]=m[:,:4]
    missing=np.zeros(n,bool)
    sg=np.array([[60.,1.,98.,0.,101.,99.,ts[0],ts[0]]])
    return ts,m,missing,sg

def test_72hours_carry_and_five_R():
    ts,m,missing,sg=market();cfg=Execution(fee_bps=0,slip_bps=0)
    out=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    r=out[1][0];assert int(r[1]-r[0])==4320 and r[18]==3
    assert r[7]==110 and r[6]==98
    ck=audit(out,m,missing,ts,sg,0,len(ts),cfg,'ETHUSDT')
    assert ck['trades_carried_overnight']==1 and ck['all_hold_hours_le72']

def test_end_of_sample_forces_flat():
    ts,m,missing,sg=market(2);cfg=Execution()
    o=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    assert o[1][0,18]==7 and o[1][0,1]==len(ts)-1
    assert audit(o,m,missing,ts,sg,0,len(ts),cfg,'ETHUSDT')['passed']

@pytest.mark.parametrize('side',[1,-1])
def test_5R_target_for_long_short(side):
    ts,m,missing,sg=market();sg[0,1]=side;sg[0,2]=98 if side==1 else 102
    cfg=Execution();o=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    r=o[1][0];rr=side*(r[7]-r[4])/(side*(r[4]-r[6]));assert 5-1e-9<=rr<=5.01
    audit(o,m,missing,ts,sg,0,len(ts),cfg,'ETHUSDT')

def test_same_candle_stop_before_target():
    ts,m,missing,sg=market();m[61,1:3]=[111,97.9];m[61,6:8]=[100.1,99.9]
    o=run(m,missing,sg,0,len(ts),Execution(fee_bps=0,slip_bps=0),'ETHUSDT',True)
    assert o[1][0,18]==1 and o[1][0,12]<0

def test_gap_beyond_initial_stop_not_entered():
    ts,m,missing,sg=market();m[60,0]=97
    assert len(run(m,missing,sg,0,len(ts),Execution(),'ETHUSDT',True)[1])==0

def test_30x_with_reserve_vs_unfunded_liquidation():
    ts,m,missing,sg=market();sg[0,2]=95;m[1500,2]=96;m[1500,7]=96
    a=run(m,missing,sg,0,len(ts),Execution(),'ETHUSDT',True)
    b=run(m,missing,sg,0,len(ts),Execution(funded_collateral=False),'ETHUSDT',True)
    assert a[1][0,18]==3 and b[1][0,18]==4
    assert a[1][0,17]>a[1][0,16] and b[1][0,17]==b[1][0,16]

def test_funding_across_multiple_days_is_not_dropped():
    ts,m,missing,sg=market();m[480::480,9]=.0001;cfg=Execution(fee_bps=0,slip_bps=0)
    out=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    assert out[1][0,10]>0 and out[1][0,12]<0
    audit(out,m,missing,ts,sg,0,len(ts),cfg,'ETHUSDT')

def test_no_entry_funding_credit():
    ts,m,missing,sg=market();m[60,9]=-.005;cfg=Execution(fee_bps=0,slip_bps=0)
    out=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    assert out[1][0,10]==0

def test_no_pyramiding_overlap():
    ts,m,missing,sg=market();sg=np.r_[sg,np.array([[90,1,98,0,101,99,ts[0],ts[0]]])]
    assert len(run(m,missing,sg,0,len(ts),Execution(),'ETHUSDT',True)[1])==1

def test_signal_latency_is_applied():
    ts,m,missing,sg=market();o=run(m,missing,sg,0,len(ts),Execution(delay_minutes=2),'ETHUSDT',True)
    assert o[1][0,0]==62

def test_fee_and_size_arithmetic_audit_rejects_corruption():
    ts,m,missing,sg=market();cfg=Execution();o=run(m,missing,sg,0,len(ts),cfg,'ETHUSDT',True)
    o[1][0,12]+=1
    with pytest.raises(AssertionError):audit(o,m,missing,ts,sg,0,len(ts),cfg,'ETHUSDT')

def test_record_false_same_account():
    ts,m,missing,sg=market();a=run(m,missing,sg,0,len(ts),Execution(),'ETHUSDT',True);b=run(m,missing,sg,0,len(ts),Execution(),'ETHUSDT',False)
    np.testing.assert_array_equal(a[0],b[0]);np.testing.assert_array_equal(a[2],b[2]);assert len(b[1])==0

def create_input(days=420):
    rng=np.random.default_rng(83);ts,m,missing,sg=market(days)
    c=2000*np.exp(np.cumsum(rng.normal(0,.0007,len(ts))));op=np.r_[c[0],c[:-1]]
    m[:,:4]=np.column_stack([op,np.maximum(op,c)*1.0001,np.minimum(op,c)*.9999,c]);m[:,5:9]=m[:,:4]
    iv=pd.DataFrame({'timestamp':ts[::1440]-DAY,'open':60.,'high':61.,'low':59.,'close':60+5*np.sin(np.arange(days)/5)})
    return ts,m,iv

@pytest.mark.parametrize('scale',['latest','mean5','historical'])
def test_daily_weekly_frozen_levels_causal(scale):
    ts,m,iv=create_input();cut=350*1440;df=levels(ts,m,iv);changed=m.copy();changed[cut:,:4]*=2.5
    other=levels(ts,changed,iv)
    cols=['reference','sigma','mean5','up_calib','down_calib','week_reference','week_sigma','week_mean5','trend']
    pd.testing.assert_frame_equal(df[cols].iloc[:351],other[cols].iloc[:351])
    small=levels(ts[:cut],m[:cut],iv);pd.testing.assert_frame_equal(df[cols].iloc[:350],small[cols])

@pytest.mark.parametrize('family',['reject','break','retest'])
@pytest.mark.parametrize('horizon',['daily','weekly','confluence'])
def test_completed_bar_signals_prefix(family,horizon):
    ts,m,iv=create_input();cut=350*1440;d=levels(ts,m,iv);spec=Spec(family=family,horizon=horizon,multiplier=.75,timeframe=60)
    s=make_signals(ts,m,d,bars(ts,m,60),spec)
    t=make_signals(ts[:cut],m[:cut],levels(ts[:cut],m[:cut],iv),bars(ts[:cut],m[:cut],60),spec)
    np.testing.assert_allclose(s[s[:,0]<cut],t)
    assert (s[:,0]%60==0).all()
    assert (ts[0]+s[:,0]*60000>=s[:,6]).all() and (ts[0]+s[:,0]*60000>=s[:,7]).all()

def test_weekly_levels_constant_during_week():
    ts,m,iv=create_input();d=levels(ts,m,iv);groups=d.groupby(d.week_origin_ms)
    assert all(g.week_reference.nunique()<=1 and g.week_sigma.nunique()<=1 for _,g in groups)

def test_30x_and_5R_are_required():
    with pytest.raises(ValueError):Execution(contract_leverage=20).validate()
    with pytest.raises(ValueError):Execution(reward_risk=4).validate()
    with pytest.raises(ValueError):Execution(max_hold_hours=73).validate()

def test_numerical_model_no_future_labels():
    from learning import fit,predict,FEATURES
    rng=np.random.default_rng(4);n=1400;x=rng.normal(size=(n,len(FEATURES)));entry=np.arange(n)*3600000+1650000000000;maturity=entry+72*3600000+60000
    y=x[:,0]*.2+rng.normal(size=n);cut=entry[1200]
    a=fit(x,y,cut,maturity,entry);y2=y.copy();y2[maturity>cut]=100
    b=fit(x,y2,cut,maturity,entry)
    assert a==b and a['last_label_maturity_ms']<=cut
    assert np.isfinite(predict(a,x[-5:])).all()

"""Synthetic timing/engine controls and actual-result checks; no network/orders."""
import sys,json
from pathlib import Path
import numpy as np,pandas as pd,pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from bands import Spec,make_context,signals
from research import bounds,config,run,audit,PERIODS

@pytest.fixture(scope='module')
def market():
 n=90*1440;rng=np.random.default_rng(8101);c=2000*np.exp(np.cumsum(rng.normal(0,.0009,n)));o=np.r_[c[0],c[:-1]];ts=np.arange(n,dtype=np.int64)*60000+1609459200000
 return {'timestamp':ts,'open':o,'high':np.maximum(o,c)*1.0006,'low':np.minimum(o,c)*.9994,'close':c,'volume':rng.uniform(100,500,n)}
@pytest.fixture(scope='module')
def iv(tmp_path_factory):
 p=tmp_path_factory.mktemp('iv')/'test.csv';days=pd.date_range('2020-11-01',periods=180,freq='D',tz='UTC');x=np.arange(len(days));pd.DataFrame({'timestamp':days.asi8//1000000,'open':70+x*.03,'high':72+x*.03,'low':68+x*.03,'close':70+x*.03}).to_csv(p,index=False);return p

@pytest.mark.parametrize('source',['rv20','range20','iv1','iv5'])
@pytest.mark.parametrize('hour',[0,8])
def test_current_session_prefix_is_invariant(market,iv,source,hour):
 full=make_context(market,iv);cut=85*1440+719;prefix=make_context({k:v[:cut] for k,v in market.items()},iv)
 for family in ['rejection','breakout']:
  s=Spec(source,5,hour,.75,family,.5,'pivot' if family=='rejection' else '2R','all');a,b,c=signals(full,s);x,y,z=signals(prefix,s);last=(cut//5)*5
  np.testing.assert_array_equal(a[:last],x[:last]);np.testing.assert_allclose(b[:last],y[:last],equal_nan=True);np.testing.assert_allclose(c[:last],z[:last],equal_nan=True);assert not x[last:].any()

@pytest.mark.parametrize('source',['rv20','range20','iv1','iv5'])
def test_future_prices_and_iv_do_not_change_earlier_signals(market,iv,source,tmp_path):
 cutoff=84*1440+900;changed={k:v.copy() for k,v in market.items()}
 for key in ['open','high','low','close']:changed[key][cutoff:]*=1.25
 doc=pd.read_csv(iv);doc.loc[doc.timestamp>=market['timestamp'][cutoff],'close']*=2;path=tmp_path/'iv.csv';doc.to_csv(path,index=False);s=Spec(source,15,8,.75,'rejection',.5,'pivot','all');base=signals(make_context(market,iv),s);mutated=signals(make_context(changed,path),s)
 for a,b in zip(base,mutated):np.testing.assert_allclose(a[:cutoff],b[:cutoff],equal_nan=True)

def test_iv_no_fallback(market):
 with pytest.raises(ValueError):signals(make_context(market,None),Spec('iv1'))
def test_iv_has_explicit_available_timestamp(market,iv):
 _,_,_,d=signals(make_context(market,iv),Spec('iv1',5,0,.5,'rejection',.5,'pivot','all'),True);assert len(d)>0;assert (d.volatility_available_ms<=d.session_start_ms).all();assert (d.session_start_ms<d.signal_available_ms).all();assert ((d.signal_available_ms%300000)==0).all()
def test_exact_period_definitions():
 x,y=[pd.Timestamp(s) for s in PERIODS['five_years']];assert (y-x).days==1826;x,y=[pd.Timestamp(s) for s in PERIODS['250_weeks']];assert (y-x).days==1750;ts=np.arange(100)*60+1609459200;assert bounds(ts,[pd.Timestamp('2021-01-01',tz='UTC'),pd.Timestamp('2021-01-01T01:00Z')])==[0,60]
def small_market():
 n=600;ts=np.arange(n,dtype=np.int64)*60+1609459200;m=np.zeros((n,10));m[:,0:4]=100.;m[:,1]=100.2;m[:,2]=99.8;m[:,4]=1e6;m[:,5:9]=m[:,[0,1,2,3]];return m,ts

def test_stop_first_and_account_reconciliation():
 m,ts=small_market();sig=np.zeros(len(ts),np.int8);sig[10]=1;st=np.zeros(len(ts));st[10]=.01;targets=np.full(len(ts),np.nan);targets[10]=102.;m[11,1]=103.;m[11,2]=98.;m[11,6]=103.;m[11,7]=98.;cfg=config('ETHUSDT');out=run(m,ts,sig,st,targets,cfg,0,len(ts),True);assert len(out[3])==1 and int(out[3][0,12])==1;audit(out,m,ts,0,len(ts),cfg,sig)
def test_target_already_behind_entry_skips_trade():
 m,ts=small_market();sig=np.zeros(len(ts),np.int8);sig[10]=1;st=np.full(len(ts),.01);target=np.full(len(ts),np.nan);target[10]=99.;out=run(m,ts,sig,st,target,config('ETHUSDT'),0,len(ts),True);assert len(out[3])==0

def test_entry_after_signal_bar():
 m,ts=small_market();sig=np.zeros(len(ts),np.int8);sig[10]=1;st=np.full(len(ts),.01);target=np.full(len(ts),102.);out=run(m,ts,sig,st,target,config('ETHUSDT'),0,len(ts),True);assert len(out[3])==1 and int(out[3][0,0])==11

def test_equity_daily_adverse_path():
 from equity_research import simulate
 ohlc=np.array([[100.,102.,98.,100.]]);eq,ledger,dd=simulate(ohlc,np.array([1],np.int8),np.array([.01]),np.array([1000000.]),np.array([19000],np.int64),0,1,.5,.5,1.,True,True,.01,.0001,.0001,4.);assert len(ledger)==1 and ledger[0,9]<0;np.testing.assert_allclose(100000+ledger[:,9].sum(),eq[-1])

def test_portable_meta_forest():
 from meta_filter import export_model,portable_predict
 from sklearn.ensemble import HistGradientBoostingRegressor
 rng=np.random.default_rng(323);x=rng.normal(size=(300,4));y=x[:,0]+rng.normal(size=300)*.2;model=HistGradientBoostingRegressor(max_iter=10,max_depth=3,early_stopping=False,random_state=0).fit(x,y);doc=export_model(model,['a','b','c','d'],{});np.testing.assert_allclose(portable_predict(doc,x),model.predict(x),rtol=1e-10,atol=1e-10)

def test_actual_iv_daily_continuity():
 for s in ['BTC','ETH']:
  p=ROOT/'iv_data'/f'{s}_1D.csv'
  if not p.exists():pytest.skip('actual data not installed')
  d=pd.read_csv(p);assert len(d)==1987;assert np.all(np.diff(d.timestamp)==86400000);assert pd.Timestamp(d.timestamp.min(),unit='ms',tz='UTC')==pd.Timestamp('2021-03-24',tz='UTC');assert pd.Timestamp(d.timestamp.max(),unit='ms',tz='UTC')==pd.Timestamp('2026-08-31',tz='UTC')

def test_all_anniversary_returns_reconcile():
 paths=list((ROOT/'results').rglob('METRICS.json'))
 if not paths:pytest.skip('run experiments first')
 count=0
 for p in paths:
  r=json.loads(p.read_text());annual=r.get('annual_returns',[])
  if len(annual)==5:np.testing.assert_allclose(np.prod(1+np.asarray(annual)),1+r['net_return'],rtol=1e-9,atol=1e-8);count+=1
 assert count>0

def test_adaptive_training_precedes_prediction():
 for p in (ROOT/'results').rglob('*_FROZEN_FOLDS.json'):
  for r in json.loads(p.read_text()):assert pd.Timestamp(r['training_end_exclusive'])<=pd.Timestamp(r['prediction_start']);assert pd.Timestamp(r['training_start'])<pd.Timestamp(r['training_end_exclusive'])

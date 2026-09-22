"""Fixed development grid, validation selection, then separately frozen evaluation."""
from __future__ import annotations
import argparse,json,itertools,time
from pathlib import Path
from dataclasses import asdict,replace
import numpy as np,pandas as pd
from trader.strategy import StrategySpec,aggregate_minutes,minute_signals
from research.data import load,sha256
from research.simulator import Config,_run,summary
PERIODS={'development':('2021-01-04','2023-01-02'),'validation':('2023-01-02','2023-09-25'),'evaluation':('2023-10-02','2026-08-31')}

def cfg_for(s,symbol='ETHUSDT'):
 return Config(risk_fraction=s.risk_fraction,leverage_cap=s.exposure_cap,target_r=s.target_r,trail_r=s.trail_r,max_hold_seconds=s.max_hold_hours*3600,daily_stop=s.daily_loss,weekly_stop=s.weekly_loss,cooldown_seconds=s.cooldown_minutes*60,quantity_step={'ETHUSDT':.001,'BTCUSDT':.001,'XRPUSDT':1.}[symbol],price_tick={'ETHUSDT':.01,'BTCUSDT':.1,'XRPUSDT':.0001}[symbol],minimum_notional={'ETHUSDT':20.,'BTCUSDT':100.,'XRPUSDT':5.}[symbol])

def fast(m,ts,signals,stops,cfg,a,b,record=False):
 p=np.array([cfg.initial_equity,cfg.risk_fraction,cfg.leverage_cap,cfg.fee_bps/1e4,cfg.slippage_bps/1e4,cfg.participation,cfg.target_r,cfg.max_hold_seconds,cfg.cooldown_seconds,cfg.weekly_stop,cfg.daily_stop,cfg.maintenance,cfg.liquidation_fee_bps/1e4,cfg.trail_r,cfg.profit_lock,int(cfg.exit_on_opposite),cfg.entry_delay_bars,cfg.max_entries_daily,int(cfg.force_20x),cfg.quantity_step,cfg.price_tick,cfg.minimum_notional],float)
 return _run(m,ts,signals,stops,a,b,p,record)

def metrics(out,ts,a,b,cfg):
 d,w=summary(out,ts,a,b,cfg);years=(ts[b-1]+60-ts[a])/(365.2425*86400)
 d['cagr']=float(max(0,1+d['net_return'])**(1/years)-1)
 return d

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',default='ETHUSDT',choices=['ETHUSDT','BTCUSDT','XRPUSDT']);p.add_argument('--out',default='results');p.add_argument('--limit',type=int,default=0);a=p.parse_args()
 root=Path(a.out);root.mkdir(exist_ok=True,parents=True);specs=[]
 for family,tf,look,volume,trend,direction in itertools.product(['breakout','momentum','pullback','reversal'],[15,60,240],[12,48,192],[0.,1.],[0,200],['both','long']):
  if family=='pullback' and trend!=200:continue
  if family=='reversal' and trend!=0:continue
  if family in ('pullback','reversal') and look!=48:continue
  for stop,rr,trail in [(1.5,2.,0.),(2.5,4.,0.),(3.,6.,0.),(2.5,8.,2.),(4.,8.,3.)]:
   specs.append(StrategySpec(minimum_price=0. if a.symbol=='XRPUSDT' else 1000.,family=family,timeframe_minutes=tf,lookback=look,volume_multiple=volume,trend_span=trend,direction=direction,stop_atr=stop,target_r=rr,trail_r=trail,max_hold_hours=72,risk_fraction=.02,exposure_cap=5,daily_loss=.06,weekly_loss=.15))
 if a.limit:specs=specs[:a.limit]
 protocol={'symbol':a.symbol,'instrument_grid_assumptions':{'ETHUSDT':[.001,.01,20.],'BTCUSDT':[.001,.1,100.],'XRPUSDT':[1.,.0001,5.]},'created_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'periods':PERIODS,'grid':[asdict(s) for s in specs],'data_sha256':sha256(a.data),'selection':'Top 24 development candidates with >=100 trades,no liquidations,DD<=60%; tune risk on validation only; primary max validation CAGR with >=30 trades and DD<=50%; freeze before evaluation; all finalists reported. Prior project calendar exposure remains.','targets':{'evaluation_weeks':150,'evaluation_trades':200,'cagr':2.0,'rolling_365_day_minimum':2.0},'costs':{'fee_bps_per_side':5,'slippage_bps_per_side':2,'prior_minute_volume_participation':.01}}
 (root/'SEARCH_PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
 m,ts,raw,missing=load(a.data);bounds={k:tuple(int(np.searchsorted(ts,pd.Timestamp(t,tz='UTC').timestamp())) for t in v) for k,v in PERIODS.items()};cache={tf:aggregate_minutes(raw,tf) for tf in [15,60,240]}
 rows=[];started=time.time();lastkey=None
 for i,s in enumerate(specs):
  key=(s.family,s.timeframe_minutes,s.lookback,s.volume_multiple,s.trend_span,s.direction)
  if key!=lastkey:sig,base_st,_=minute_signals(raw,replace(s,stop_atr=1),cache[s.timeframe_minutes]);lastkey=key
  st=base_st*s.stop_atr;cfg=cfg_for(s,a.symbol);out=fast(m,ts,sig,st,cfg,*bounds['development']);d=metrics(out,ts,*bounds['development'],cfg)
  rows.append({'id':s.identity,**asdict(s),**{f'dev_{k}':v for k,v in d.items() if not isinstance(v,dict)}})
  if (i+1)%50==0:print('development',i+1,'/',len(specs),'elapsed',round(time.time()-started,1),flush=True)
 pd.DataFrame(rows).to_csv(root/'development_search.csv',index=False)
 candidates=[(s,r) for s,r in zip(specs,rows) if r['dev_trades']>=100 and r['dev_liquidations']==0 and r['dev_conservative_intrabar_drawdown']<=.60];candidates.sort(key=lambda x:x[1]['dev_cagr'],reverse=True);finalists=candidates[:24]
 if not finalists:raise RuntimeError('no eligible development candidate')
 val=[]
 for s,r in finalists:
  sig,st,_=minute_signals(raw,s,cache[s.timeframe_minutes])
  for risk in [.005,.01,.02,.04,.06]:
   for day,week in [(.03,.08),(.06,.15),(.12,.30)]:
    spec=replace(s,risk_fraction=risk,daily_loss=day,weekly_loss=week);cfg=cfg_for(spec,a.symbol);out=fast(m,ts,sig,st,cfg,*bounds['validation']);d=metrics(out,ts,*bounds['validation'],cfg);val.append({'spec':asdict(spec),'id':spec.identity,'metrics':d})
 (root/'validation_search.json').write_text(json.dumps(val,indent=2))
 eligible=[r for r in val if r['metrics']['trades']>=30 and r['metrics']['liquidations']==0 and r['metrics']['conservative_intrabar_drawdown']<=.50];eligible.sort(key=lambda r:r['metrics']['cagr'],reverse=True)
 if not eligible:raise RuntimeError('no eligible validation candidate')
 frozen={'primary':eligible[0],'finalists':eligible[:12],'frozen_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'prior_calendar_exposure':True};(root/'FROZEN_SELECTION.json').write_text(json.dumps(frozen,indent=2));evaluation=[]
 for ix,r in enumerate(frozen['finalists']):
  s=StrategySpec(**r['spec']);sig,st,_=minute_signals(raw,s,cache[s.timeframe_minutes]);cfg=cfg_for(s,a.symbol);out=fast(m,ts,sig,st,cfg,*bounds['evaluation'],True);d=metrics(out,ts,*bounds['evaluation'],cfg);evaluation.append({'id':s.identity,'primary':ix==0,'spec':asdict(s),'metrics':d});print('evaluation',ix,s.identity,d['cagr'],d['net_return'],d['trades'],d['conservative_intrabar_drawdown'],flush=True)
 (root/'EVALUATION_FINALISTS.json').write_text(json.dumps(evaluation,indent=2));print('COMPLETE',round(time.time()-started,1),flush=True)
if __name__=='__main__':main()

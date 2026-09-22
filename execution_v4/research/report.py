"""Recompute finalists, export every trade, and independently reconcile cash/equity."""
from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path
from dataclasses import asdict,replace
import numpy as np,pandas as pd
from trader.strategy import StrategySpec,aggregate_minutes,minute_signals
from research.data import load,sha256
from research.search import cfg_for,fast,metrics,PERIODS
from research.simulator import TRADE_COLS,REASONS,summary

def utc(t):return pd.Timestamp(int(t),unit='s',tz='UTC').isoformat().replace('+00:00','Z')
def save(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')

def audit(out,m,ts,start,end,cfg,signals):
    eq,eo,el,ledger,_=out;n=end-start;delta=np.zeros(n);qpos=np.zeros(n);basis=np.zeros(n);prior=-1
    for row in ledger:
        ei,xi,side=map(int,row[:3]);qty,ent,ex,ef,xf,fp,gross,net,bal,reason,pre,lev,upper=row[3:]
        assert start<=ei<=xi<end and ei>prior and side==signals[ei-cfg.entry_delay_bars]
        a,b=ei-start,xi-start;q=side*qty
        assert ts[xi]<=upper<=ts[xi]+60
        np.testing.assert_allclose(gross,q*(ex-ent),rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(net,gross-ef-xf-fp,rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(ef,qty*ent*cfg.fee_bps/10000,rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(xf,qty*ex*(cfg.liquidation_fee_bps if int(reason)==5 else cfg.fee_bps)/10000,rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(lev,qty*ent/pre,rtol=1e-10,atol=1e-10)
        assert qty*ent<=pre*cfg.leverage_cap+1e-6
        assert qty<=m[ei-1,4]*cfg.participation+1e-8
        assert abs(qty/cfg.quantity_step-round(qty/cfg.quantity_step))<1e-6
        fund=q*m[ei:xi+1,5]*m[ei:xi+1,9];fund=fund.copy();fund[0]=max(fund[0],0)
        np.testing.assert_allclose(fund.sum(),fp,rtol=1e-9,atol=1e-7)
        delta[a:b+1]-=fund;delta[a]-=ef;delta[b]+=gross-xf;qpos[a:b]=q;basis[a:b]=ent;prior=xi
    cash=cfg.initial_equity+np.cumsum(delta);ce=cash+qpos*(m[start:end,8]-basis)
    pq=np.r_[0,qpos[:-1]];pb=np.r_[0,basis[:-1]];pc=np.r_[cfg.initial_equity,cash[:-1]];oe=pc+pq*(m[start:end,5]-pb)
    np.testing.assert_allclose(ce,eq,rtol=1e-9,atol=1e-6);np.testing.assert_allclose(oe,eo,rtol=1e-9,atol=1e-6)
    if len(ledger):
        np.testing.assert_allclose(cfg.initial_equity+np.cumsum(ledger[:,10]),ledger[:,11],rtol=1e-9,atol=1e-6)
    return {'passed':True,'trade_rows':len(ledger),'minute_rows':n,'equity_series_reconstructed':2,'largest_close_error':float(np.max(np.abs(ce-eq))),'largest_open_error':float(np.max(np.abs(oe-eo))),'gross_pnl':float(ledger[:,9].sum()),'commissions':float(ledger[:,6:8].sum()),'funding_paid':float(ledger[:,8].sum()),'net_pnl':float(ledger[:,10].sum())}

def enriched(ledger,ts,st,cfg):
    d=pd.DataFrame(ledger,columns=TRADE_COLS);d.insert(0,'trade_id',np.arange(1,len(d)+1))
    ei=d.entry_index.to_numpy(dtype=int);xi=d.exit_index.to_numpy(dtype=int)
    d['signal_available_utc']=[utc(ts[i-cfg.entry_delay_bars]+60) for i in ei]
    d['entry_utc_simulated']=[utc(ts[i]) for i in ei];d['exit_bar_open_utc']=[utc(ts[i]) for i in xi];d['exit_utc_upper_bound']=d.exit_epoch_upper_bound.map(utc)
    d['exit_reason']=d.reason_code.astype(int).map(REASONS)
    d['timestamp_precision']=['simulated_bar_open_or_final_close' if int(u)==int(ts[i]) or int(r)==8 else 'within_minute_not_exact_tick' for i,u,r in zip(xi,d.exit_epoch_upper_bound,d.reason_code)]
    dist=d.entry_price.to_numpy()*st[ei-cfg.entry_delay_bars]
    d['initial_stop']=d.entry_price-d.side*dist;d['initial_target']=d.entry_price+d.side*dist*cfg.target_r
    d['target_r']=cfg.target_r;d['realized_net_r']=d.net_pnl/(d.quantity*dist)
    return d

def periods(daily,kind):
    series=daily.set_index('timestamp').equity
    start,end=series.index[0],series.index[-1];freq='MS' if kind=='month' else 'YS'
    bounds=sorted(set([start,end]+[x for x in pd.date_range(start,end,freq=freq) if start<x<end]));rows=[]
    for a,b in zip(bounds[:-1],bounds[1:]):
        ea,eb=float(series.loc[a]),float(series.loc[b]);expected=a+(pd.offsets.MonthBegin(1) if kind=='month' else pd.offsets.YearBegin(1))
        complete=a.day==1 and (kind=='month' or a.month==1) and expected==b
        rows.append({'start_utc':a.isoformat(),'end_exclusive_utc':b.isoformat(),'complete_calendar_period':bool(complete),'equity_start':ea,'equity_end':eb,'net_return':eb/ea-1})
    return pd.DataFrame(rows)

def publish_case(root,name,symbol,spec,out,m,ts,raw,st,sig,a,b,cfg,full_equity=True):
    d=root/name;d.mkdir(parents=True,exist_ok=True);stats=metrics(out,ts,a,b,cfg)
    stats.pop('gates',None);stats.pop('passes_historical_average_target',None)
    ledger=out[3];stats['wins']=int((ledger[:,10]>0).sum());stats['losses']=int((ledger[:,10]<0).sum())
    result=audit(out,m,ts,a,b,cfg,sig);save(d/'INDEPENDENT_AUDIT.json',result)
    enriched(ledger,ts,st,cfg).to_csv(d/'all_trades_UTC.csv',index=False)
    _,weeks=summary(out,ts,a,b,cfg);w=pd.DataFrame(weeks,columns=['week_start_epoch','net_return']);w['week_start_utc']=w.week_start_epoch.map(utc);w.to_csv(d/'weekly_returns.csv',index=False)
    times=ts[a:b];mask=times%86400==0;dt=list(pd.to_datetime(times[mask],unit='s',utc=True))+[pd.Timestamp(ts[b-1]+60,unit='s',tz='UTC')]
    vals=list(out[1][mask])+[float(out[0][-1])];daily=pd.DataFrame({'timestamp':dt,'equity':vals});daily.to_csv(d/'daily_equity.csv',index=False)
    for k in ('month','year'):periods(daily,k).to_csv(d/(k+'ly_returns.csv'),index=False)
    rolling=daily.copy();rolling['net_return_365_days']=rolling.equity/rolling.equity.shift(365)-1;rolling=rolling.iloc[365:];rolling.to_csv(d/'rolling_365_day_returns.csv',index=False)
    stats['minimum_rolling_365_day_return']=float(rolling.net_return_365_days.min());stats['maximum_rolling_365_day_return']=float(rolling.net_return_365_days.max());stats['rolling_365_day_windows']=len(rolling)
    gaps=[]
    for i in np.flatnonzero(~np.isfinite(raw['mark_open'])):
        if not a<=i<b:continue
        exposed=any(int(r[0])<=i<=int(r[1]) for r in ledger)
        gaps.append({'utc':utc(ts[i]),'position_exposed':exposed,'model_open':float(m[i,5]),'model_high':float(m[i,6]),'model_low':float(m[i,7]),'model_close':float(m[i,8]),'sourced_15m_bounds':bool(np.isfinite(raw['missing_mark_15m_low'][i]))})
    save(d/'MARK_GAPS.json',gaps);stats['missing_mark_minutes_during_evaluation']=len(gaps);stats['missing_mark_minutes_with_position']=sum(g['position_exposed'] for g in gaps)
    stats['targets']={'at_least_150_weeks':stats['complete_weeks']>=150,'at_least_200_closed_trades':stats['trades']>=200,'cagr_at_least_200_percent':stats['cagr']>=2,'every_rolling_year_at_least_200_percent':stats['minimum_rolling_365_day_return']>=2}
    stats['all_requested_targets_pass']=all(stats['targets'].values())
    stats['end_exclusive_utc']=utc(ts[b-1]+60);stats['start_utc']=utc(ts[a]);stats['symbol']=symbol
    save(d/'METRICS.json',stats);save(d/'strategy.json',asdict(spec));save(d/'simulation_parameters.json',asdict(cfg))
    if full_equity:
        pd.DataFrame({'timestamp_epoch':times,'equity_close':out[0],'equity_open':out[1],'conservative_intrabar_equity_low':out[2]}).to_csv(d/'minute_equity.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    return {'case':name,**stats}

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',required=True);p.add_argument('--base-results',required=True);p.add_argument('--out',required=True);args=p.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True);m,ts,raw,_=load(args.data);a,b=[int(np.searchsorted(ts,pd.Timestamp(x,tz='UTC').timestamp())) for x in PERIODS['evaluation']]
    source=Path(args.base_results);rows=json.loads((source/'EVALUATION_FINALISTS.json').read_text());reports=[];cache={}
    for i,row in enumerate(rows):
        s=StrategySpec(**row['spec']);tf=s.timeframe_minutes
        if tf not in cache:cache[tf]=aggregate_minutes(raw,tf)
        sig,st,_=minute_signals(raw,s,cache[tf]);cfg=cfg_for(s,args.symbol);out=fast(m,ts,sig,st,cfg,a,b,True)
        actual=metrics(out,ts,a,b,cfg)
        np.testing.assert_allclose(actual['net_return'],row['metrics']['net_return'],rtol=1e-11,atol=1e-9)
        name=('PRIMARY_' if i==0 else 'DIAGNOSTIC_')+s.identity
        reports.append(publish_case(root,name,args.symbol,s,out,m,ts,raw,st,sig,a,b,cfg,i==0));print('audited',args.symbol,name,flush=True)
    ml=source.parent/('ML_'+args.symbol) if args.symbol!='ETHUSDT' else source/('ML_'+args.symbol)
    if (ml/'EVALUATION.json').exists():
        doc=json.loads((ml/'EVALUATION.json').read_text());s=StrategySpec(**doc['spec'])
        with np.load(ml/'evaluation_predictions.npz',allow_pickle=False) as z:sig=z['signal'];st=z['stop']
        cfg=cfg_for(s,args.symbol);out=fast(m,ts,sig,st,cfg,a,b,True);reports.append(publish_case(root,'WALKFORWARD_ML',args.symbol,s,out,m,ts,raw,st,sig,a,b,cfg,True))
    s=StrategySpec(**rows[0]['spec']);sig,st,_=minute_signals(raw,s,cache[s.timeframe_minutes]);base=cfg_for(s,args.symbol)
    stress=[]
    for label,cfg in [('double_cost',replace(base,fee_bps=10,slippage_bps=4)),('two_minute_delay',replace(base,entry_delay_bars=2)),('five_minute_delay',replace(base,entry_delay_bars=5))]:
        out=fast(m,ts,sig,st,cfg,a,b,True);audit(out,m,ts,a,b,cfg,sig);stress.append({'case':label,'metrics':metrics(out,ts,a,b,cfg)})
    save(root/'STRESSES.json',stress);save(root/'INDEX.json',reports);save(root/'DATA_IDENTITY.json',{'sha256':sha256(args.data),'raw_rows':len(ts),'raw_start':utc(ts[0]),'raw_end_exclusive':utc(ts[-1]+60),'raw_missing_mark_rows':int((~np.isfinite(raw['mark_open'])).sum()),'missing_mark_model':'previous marked close for open/close; sourced 15m bounds when available; otherwise explicit +/-5% diagnostic envelope. Raw NaNs are preserved. Not observed tick/mark prices.'})
if __name__=='__main__':main()

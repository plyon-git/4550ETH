"""Reproducible causal wall tests. No account or order-submission calls."""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,json,itertools,time
import numpy as np,pandas as pd
from bands import Spec,make_context,signals,source_hash
from engine import Config,_run,validate_data,summary,TRADE_COLS,REASONS
ROOT=Path(__file__).resolve().parents[1]
PERIODS={'development':['2020-02-01','2021-06-01'],'validation':['2021-06-01','2021-08-25'],'five_years':['2021-09-01','2026-09-01'],'250_weeks':['2021-11-15','2026-08-31']}
EXPECTED={'ETHUSDT':'b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d','BTCUSDT':'2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3','XRPUSDT':'43678daef70287657734cf3eb6b6915ffa5df0b24d90d289d8892ee1d5f70859'}
def write(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else (_ for _ in ()).throw(TypeError(str(type(x)))))+'\n')
def load(symbol):
 path=ROOT/'data'/symbol/'aligned_repaired.npz'
 if source_hash(path)!=EXPECTED[symbol]:raise ValueError('changed market input')
 with np.load(path,allow_pickle=False) as z:raw={k:z[k] for k in z.files}
 ts=raw['timestamp']//1000
 if not np.all(np.diff(ts)==60) or not raw['funding_verified'].all():raise ValueError('incomplete timeline or funding')
 from engine import COLS
 m=np.column_stack([raw[k] for k in COLS]).astype(float);missing=np.flatnonzero(~np.isfinite(m[:,5:9]).all(axis=1))
 for i in missing:
  previous=m[i-1,8];lo=raw['missing_mark_15m_low'][i];hi=raw['missing_mark_15m_high'][i]
  if not np.isfinite(lo+hi):lo=min(raw['low'][i],previous)*.95;hi=max(raw['high'][i],previous)*1.05
  m[i,5:9]=[previous,max(hi,previous),min(lo,previous),previous]
 validate_data(m,ts);return m,ts,raw,missing

def config(symbol,risk=.01,fee=5.,slip=2.):
 return Config(initial_equity=10000.,risk_fraction=risk,leverage_cap=5.,fee_bps=fee,slippage_bps=slip,max_hold_seconds=86400,cooldown_seconds=900,max_entries_daily=3,daily_stop=.04,weekly_stop=.08,quantity_step=.001 if symbol!='XRPUSDT' else 1.,price_tick={'ETHUSDT':.01,'BTCUSDT':.1,'XRPUSDT':.0001}[symbol],minimum_notional={'ETHUSDT':20.,'BTCUSDT':100.,'XRPUSDT':5.}[symbol])
def run(m,ts,sig,st,targ,cfg,a,b,record=False):
 p=np.array([cfg.initial_equity,cfg.risk_fraction,cfg.leverage_cap,cfg.fee_bps/1e4,cfg.slippage_bps/1e4,cfg.participation,cfg.target_r,cfg.max_hold_seconds,cfg.cooldown_seconds,cfg.weekly_stop,cfg.daily_stop,cfg.maintenance,cfg.liquidation_fee_bps/1e4,cfg.trail_r,cfg.profit_lock,int(cfg.exit_on_opposite),cfg.entry_delay_bars,cfg.max_entries_daily,int(cfg.force_20x),cfg.quantity_step,cfg.price_tick,cfg.minimum_notional],float)
 return _run(m,ts,sig,st,targ,a,b,p,record)
def bounds(ts,dates):
 stamps=[pd.Timestamp(x) for x in dates];stamps=[x.tz_localize('UTC') if x.tzinfo is None else x.tz_convert('UTC') for x in stamps]
 return [int(np.searchsorted(ts,x.timestamp())) for x in stamps]
def basic(out,ts,a,b,cfg):
 d,w=summary(out,ts,a,b,cfg);d.pop('gates',None);d.pop('passes_historical_average_target',None);years=(ts[b-1]+60-ts[a])/(365.2425*86400)
 d['cagr']=max(0.,1+d['net_return'])**(1/years)-1;d['selection_score']=np.log(max(1e-10,1+d['net_return']))/years-1.5*d['conservative_intrabar_drawdown'];return d

def grid(symbol):
 sources=['rv20','range20','iv1','iv5'] if symbol in ('ETHUSDT','BTCUSDT') else ['rv20','range20'];output=[]
 for src,tf,hour,width,family,st,regime in itertools.product(sources,[5,15],[0,8],[.75,1.25,1.75],['rejection','breakout'],[.25,.5],['all','aligned']):
  for target in (['pivot','2R'] if family=='rejection' else ['2R','4R']):output.append(Spec(src,tf,hour,width,family,st,target,regime))
 return output

def audit(out,m,ts,a,b,cfg,sig):
 eq,eo,el,ledger,_=out;n=b-a;d=np.zeros(n);q=np.zeros(n);eb=np.zeros(n);last=-1
 for row in ledger:
  ei,xi,side=map(int,row[:3]);qty,ent,ex,ef,xf,fp,gross,net,bal,why,pre,lev,upper=row[3:]
  assert a<=ei<=xi<b and ei>last and side==sig[ei-cfg.entry_delay_bars];assert ts[xi]<=upper<=ts[xi]+60
  np.testing.assert_allclose(gross,side*qty*(ex-ent),rtol=1e-10,atol=1e-7);np.testing.assert_allclose(net,gross-ef-xf-fp,rtol=1e-10,atol=1e-7)
  np.testing.assert_allclose(ef,qty*ent*cfg.fee_bps/10000,rtol=1e-10,atol=1e-7);np.testing.assert_allclose(xf,qty*ex*(cfg.liquidation_fee_bps if why==5 else cfg.fee_bps)/10000,rtol=1e-10,atol=1e-7)
  assert qty*ent<=pre*cfg.leverage_cap+1e-6 and qty<=m[ei-1,4]*cfg.participation+1e-8
  fund=side*qty*m[ei:xi+1,5]*m[ei:xi+1,9];fund=fund.copy();fund[0]=max(fund[0],0);np.testing.assert_allclose(fund.sum(),fp,rtol=1e-10,atol=1e-7)
  x,y=ei-a,xi-a;d[x:y+1]-=fund;d[x]-=ef;d[y]+=gross-xf;q[x:y]=side*qty;eb[x:y]=ent;last=xi
 cash=cfg.initial_equity+np.cumsum(d);close=cash+q*(m[a:b,8]-eb);op=np.r_[cfg.initial_equity,cash[:-1]]+np.r_[0.,q[:-1]]*(m[a:b,5]-np.r_[0.,eb[:-1]])
 np.testing.assert_allclose(close,eq,rtol=1e-9,atol=1e-7);np.testing.assert_allclose(op,eo,rtol=1e-9,atol=1e-7)
 return {'passed':True,'trades':len(ledger),'minutes':n,'max_equity_error':float(max(np.max(np.abs(close-eq)),np.max(np.abs(op-eo)))),'gross_price_pnl':float(ledger[:,9].sum()),'fees':float(ledger[:,6:8].sum()),'funding_paid':float(ledger[:,8].sum()),'net_trade_pnl':float(ledger[:,10].sum())}

def export(root,name,symbol,spec,out,m,ts,raw,a,b,cfg,sig,st,targ,full=False,selection='fixed-before-evaluation'):
 folder=root/name;folder.mkdir(parents=True,exist_ok=True);stats=basic(out,ts,a,b,cfg);write(folder/'AUDIT.json',audit(out,m,ts,a,b,cfg,sig))
 utc=lambda t:pd.Timestamp(int(t),unit='s',tz='UTC').isoformat().replace('+00:00','Z')
 d=pd.DataFrame(out[3],columns=TRADE_COLS);d.insert(0,'trade_id',np.arange(1,len(d)+1));ei=d.entry_index.to_numpy(int);xi=d.exit_index.to_numpy(int)
 d['signal_available_utc']=[utc(ts[i-cfg.entry_delay_bars]+60) for i in ei];d['entry_utc']=[utc(ts[i]) for i in ei];d['exit_bar_open_utc']=[utc(ts[i]) for i in xi];d['exit_utc_upper_bound']=d.exit_epoch_upper_bound.map(utc);d['exit_reason']=d.reason_code.astype(int).map(REASONS)
 d['initial_stop_price']=d.entry_price-d.side*d.entry_price*st[ei-cfg.entry_delay_bars];d['absolute_target']=targ[ei-cfg.entry_delay_bars];d['target_R_at_fill']=np.abs(d.absolute_target-d.entry_price)/(d.entry_price*st[ei-cfg.entry_delay_bars]);d['timestamp_precision']='simulated minute open / intraminute exit interval, not exact tick';d.to_csv(folder/'ALL_TRADES_UTC.csv',index=False)
 times=ts[a:b];ix=np.flatnonzero(times%86400==0);dt=list(pd.to_datetime(times[ix],unit='s',utc=True))+[pd.Timestamp(ts[b-1]+60,unit='s',tz='UTC')];daily=pd.Series(list(out[1][ix])+[float(out[0][-1])],index=dt);daily.rename('equity').to_csv(folder/'DAILY_EQUITY.csv',index_label='timestamp')
 week=summary(out,ts,a,b,cfg)[1];pd.DataFrame([{'week_start_utc':utc(x),'net_return':y} for x,y in week]).to_csv(folder/'WEEKS.csv',index=False);ann=[]
 if utc(ts[a]).startswith('2021-09-01') and utc(ts[b-1]+60).startswith('2026-09-01'):
  for year in range(2021,2026):
   x=pd.Timestamp(f'{year}-09-01',tz='UTC');y=pd.Timestamp(f'{year+1}-09-01',tz='UTC');ann.append({'start':x.isoformat(),'end_exclusive':y.isoformat(),'start_equity':daily.loc[x],'end_equity':daily.loc[y],'net_return':daily.loc[y]/daily.loc[x]-1})
 pd.DataFrame(ann).to_csv(folder/'ANNIVERSARY_YEARS.csv',index=False);monthly=[];edges=sorted(set([daily.index[0],daily.index[-1]]+list(pd.date_range(daily.index[0],daily.index[-1],freq='MS'))))
 for x,y in zip(edges[:-1],edges[1:]):monthly.append({'start':x.isoformat(),'end_exclusive':y.isoformat(),'net_return':daily.loc[y]/daily.loc[x]-1,'complete_month':x.day==1 and y==x+pd.offsets.MonthBegin(1)})
 pd.DataFrame(monthly).to_csv(folder/'MONTHS.csv',index=False);rolling=(daily/daily.shift(365)-1).dropna();rolling.rename('net_return').to_csv(folder/'ROLLING_365D.csv',index_label='window_end_utc')
 stats.update(symbol=symbol,name=name,selection=selection,period_start=utc(ts[a]),period_end_exclusive=utc(ts[b-1]+60),annual_returns=[x['net_return'] for x in ann],average_annual_return=float(np.mean([x['net_return'] for x in ann])) if ann else None,positive_anniversary_years=int(sum(x['net_return']>0 for x in ann)) if ann else None,min_rolling_365d=float(rolling.min()),max_rolling_365d=float(rolling.max()),wins=int((d.net_pnl>0).sum()),losses=int((d.net_pnl<0).sum()),missing_mark_minutes=int((~np.isfinite(raw['mark_open'][a:b])).sum()))
 stats['missing_mark_minutes_held']=int(sum(any(int(row[0])<=i<=int(row[1]) for row in out[3]) for i in np.flatnonzero(~np.isfinite(raw['mark_open'])) if a<=i<b));stats['historical_65pct_cagr_gate']=stats['cagr']>=.65 and stats['trades']>=200;stats['every_anniversary_year_positive']=bool(ann and all(x['net_return']>0 for x in ann))
 write(folder/'METRICS.json',stats);write(folder/'EXECUTION.json',asdict(cfg));write(folder/'STRATEGY.json',asdict(spec) if spec is not None else {'type':'walk_forward_ensemble_selection'})
 if full:pd.DataFrame({'epoch':times,'equity_open':out[1],'equity_close':out[0],'equity_low_estimate':out[2]}).to_csv(folder/'MINUTE_EQUITY.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 return stats

def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',required=True);p.add_argument('--phase',choices=['all','screen','evaluate'],default='all');args=p.parse_args();symbol=args.symbol;root=ROOT/'results'/symbol;root.mkdir(parents=True,exist_ok=True);specs=grid(symbol);t0=time.time()
 if args.phase!='evaluate':write(root/'PROTOCOL.json',{'created_utc':pd.Timestamp.now(tz='UTC').isoformat(),'periods':PERIODS,'grid':[asdict(s) for s in specs],'selection':'Rank development log growth minus1.5drawdown; top32 per source; validate risk0.5/1/2%; primary highest validation score with>=10trades and positive net, else cash. Freeze before evaluation. Adaptive selection uses preceding26weeks among development finalists.','source_identity':EXPECTED[symbol],'target_cagr':.65,'minimum_trades':200,'fee_bps_each':5,'slippage_bps_each':2,'past_calendar_research_exposure':True,'interpretation':'IV expected-move bands, not option-strike dealer walls or proprietary Milk signals.'})
 m,ts,raw,gaps=load(symbol);ctx=make_context(raw,ROOT/'iv_data'/(symbol.replace('USDT','')+'_1D.csv'));bd={k:bounds(ts,v) for k,v in PERIODS.items()};cfg=config(symbol);byid={s.id:s for s in specs}
 if args.phase!='evaluate':
  rows=[]
  for i,s in enumerate(specs):
   sig,st,tar=signals(ctx,s);o=run(m,ts,sig,st,tar,cfg,*bd['development']);d=basic(o,ts,*bd['development'],cfg);rows.append({'id':s.id,'spec':asdict(s),'metrics':d})
   if (i+1)%128==0:print(symbol,'development',i+1,len(specs),round(time.time()-t0,1),flush=True)
  write(root/'DEVELOPMENT.json',rows);shortlist=[]
  for source in sorted(set(s.source for s in specs)):
   eligible=[r for r in rows if r['spec']['source']==source and r['metrics']['trades']>=20 and r['metrics']['liquidations']==0];eligible.sort(key=lambda x:x['metrics']['selection_score'],reverse=True);shortlist.extend(eligible[:32])
  val=[]
  for row in shortlist:
   s=byid[row['id']];sig,st,tar=signals(ctx,s)
   for risk in [.005,.01,.02]:
    c=config(symbol,risk);o=run(m,ts,sig,st,tar,c,*bd['validation']);d=basic(o,ts,*bd['validation'],c);val.append({'id':s.id,'spec':asdict(s),'risk':risk,'metrics':d})
  write(root/'VALIDATION.json',val);eligible=[r for r in val if r['metrics']['trades']>=10 and r['metrics']['liquidations']==0];ranked=sorted(eligible,key=lambda x:x['metrics']['selection_score'],reverse=True);primary=ranked[0] if ranked and ranked[0]['metrics']['net_return']>0 else None;finalists=[]
  for source,family in itertools.product(sorted(set(s.source for s in specs)),['rejection','breakout']):finalists.extend([r for r in ranked if r['spec']['source']==source and r['spec']['family']==family][:3])
  frozen={'frozen_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'primary':primary,'finalists':finalists,'adaptive_universe':[r['id'] for r in shortlist]};write(root/'FROZEN.json',frozen);print(symbol,'FROZEN',None if primary is None else (primary['id'],primary['risk'],primary['metrics']['net_return']),flush=True)
  if args.phase=='screen':return
 frozen=json.loads((root/'FROZEN.json').read_text());output=[];primary=frozen['primary']
 for row in frozen['finalists']:
  s=Spec(**row['spec']);sig,st,tar,levels=signals(ctx,s,True);c=config(symbol,row['risk']);o=run(m,ts,sig,st,tar,c,*bd['five_years'],True);isp=primary is not None and row['id']==primary['id'] and row['risk']==primary['risk'];name=('PRIMARY_' if isp else 'FINALIST_')+s.id+'_risk'+str(row['risk'])
  d=export(root,name,symbol,s,o,m,ts,raw,*bd['five_years'],c,sig,st,tar,full=isp);output.append(d);levels.to_csv(root/name/'ALL_SIGNAL_LEVELS.csv.gz',index=False,compression={'method':'gzip','mtime':0});print(symbol,name,round(d['net_return']*100,2),round(d['cagr']*100,2),d['trades'],flush=True)
  if isp:
   subs=run(m,ts,sig,st,tar,c,*bd['250_weeks'],True);export(root,'PRIMARY_250W',symbol,s,subs,m,ts,raw,*bd['250_weeks'],c,sig,st,tar);stress=[]
   for label,cf in [('zero_fee_slip',replace(c,fee_bps=0,slippage_bps=0)),('fee_only',replace(c,slippage_bps=0)),('double_cost',replace(c,fee_bps=10,slippage_bps=4)),('delay_2min',replace(c,entry_delay_bars=2)),('delay_5min',replace(c,entry_delay_bars=5)),('100k',replace(c,initial_equity=100000))]:
    ou=run(m,ts,sig,st,tar,cf,*bd['five_years'],True);stress.append(export(root,'STRESS_'+label,symbol,s,ou,m,ts,raw,*bd['five_years'],cf,sig,st,tar))
   write(root/'PRIMARY_STRESSES.json',stress)
 write(root/'INDEX.json',output);print(symbol,'DONE',len(output),round(time.time()-t0,1),flush=True)
if __name__=='__main__':main()

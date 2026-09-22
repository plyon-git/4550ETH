"""Daily-OHLC IV-band diagnostics, not an ES5m or live execution replication.
Predetermined entries, adverse stop ordering, target credit only if close confirms it.
"""
from dataclasses import dataclass,asdict
import itertools,json,hashlib
import numpy as np,pandas as pd
from numba import njit
from research import ROOT,write
@dataclass(frozen=True)
class EquitySpec:
 source:str='iv1'
 family:str='fade'
 direction:str='long'
 width:float=.5
 stop_sigma:float=.5
 target:str='pivot'
 risk:float=.01
 @property
 def id(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:16]

def context(symbol):
 p=ROOT/'equity_data';f=pd.read_csv(p/(symbol+'_daily.csv'));idx=pd.to_datetime(f.timestamp,unit='s',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize();f.index=pd.DatetimeIndex(idx);f=f.drop(columns='timestamp')
 if f.index.has_duplicates or not f.index.is_monotonic_increasing or not np.isfinite(f).all().all():raise ValueError('invalid equity history')
 if (f.low>f[['open','close']].min(axis=1)+1e-6).any() or (f.high<f[['open','close']].max(axis=1)-1e-6).any():raise ValueError('invalid equity OHLC')
 vol=pd.read_csv(p/('VIX_History.csv' if symbol=='SPY' else 'VXN_History.csv'));vol.columns=[x.strip().lower() for x in vol.columns];vol['date']=pd.to_datetime(vol['date']);vol=vol.sort_values('date');vol['available']=vol.date+pd.Timedelta(days=1)
 for n in [1,5,20]:vol['iv'+str(n)]=np.sqrt((vol.close/100).pow(2).rolling(n,min_periods=n).mean())/np.sqrt(252)
 joined=pd.merge_asof(pd.DataFrame({'date':f.index}),vol[['available','iv1','iv5','iv20']],left_on='date',right_on='available',direction='backward',tolerance=pd.Timedelta(days=5))
 for n in [1,5,20]:f['iv'+str(n)]=joined['iv'+str(n)].to_numpy()
 f['rv20']=np.log(f.close).diff().rolling(20).std().shift(1);f['trend']=np.sign((f.close-f.close.ewm(span=50,adjust=False).mean()).shift(1));f['prevsign']=np.sign(f.close.diff().shift(1));f['prior_volume']=f.volume.shift(1);f['vol_available']=joined.available.to_numpy();return f

@njit(cache=True)
def simulate(ohlc,sig,sigma,priorvol,days,a,b,width,stopmult,rr,pivot,fade,risk,fee,slip,cap):
 balance=100000.;highwater=balance;dd=0.;weekbase=balance;week=-1;equity=np.empty(b-a);ledger=np.zeros((b-a,12));n=0
 for i in range(a,b):
  w=(days[i]+3)//7
  if w!=week:week=w;weekbase=balance
  op,hi,lo,cl=ohlc[i];v=sigma[i];side=sig[i]
  if not np.isfinite(v) or v<=0 or side==0 or balance<=weekbase*.92:equity[i-a]=balance;continue
  entry=op*np.exp((-side if fade else side)*width*v);hit=(lo<=entry-.01 if side==1 else hi>=entry+.01) if fade else (hi>=entry+.01 if side==1 else lo<=entry-.01)
  if not hit:equity[i-a]=balance;continue
  stop=entry*(1-side*stopmult*v);target=op if pivot else entry*(1+side*stopmult*v*rr)
  if side*(target-entry)<=0 or target<=0:equity[i-a]=balance;continue
  ent=entry*(1+side*slip)
  if side*(target-ent)<=0:equity[i-a]=balance;continue
  per=abs(ent-stop)+ent*(2*fee+2*slip)+.02;budget=min(balance*risk,max(0.,.8*(balance-weekbase*.92)));qty=np.floor(min(budget/per,balance*cap/ent,priorvol[i]*.001))
  if qty<1:equity[i-a]=balance;continue
  stopped=(lo<=stop if side==1 else hi>=stop)
  if stopped:ex=stop*(1-side*slip)
  elif side*(cl-target)>=0:ex=target*(1-side*slip)
  else:ex=cl*(1-side*slip)
  gross=side*qty*(ex-ent);cost=qty*(ent+ex)*fee;net=gross-cost;before=balance;balance+=net;excursion=qty*abs(ent-stop)+qty*ent*fee if stopped else max(0.,-net);dd=max(dd,1-(before-excursion)/highwater);highwater=max(highwater,balance)
  ledger[n]=np.array([i,side,qty,ent,ex,stop,target,gross,cost,net,before,balance]);n+=1;equity[i-a]=balance
 return equity,ledger[:n],dd

def run(f,spec,start,end,fee=1.,slip=1.,cap=4.):
 a=int(f.index.searchsorted(start));b=int(f.index.searchsorted(end));n=len(f)
 if spec.direction=='long':side=np.ones(n)
 elif spec.direction=='short':side=-np.ones(n)
 elif spec.direction=='trend':side=f.trend.to_numpy()
 elif spec.direction=='counter_trend':side=-f.trend.to_numpy()
 else:side=-f.prevsign.to_numpy()
 side=np.nan_to_num(side).astype(np.int8);ohlc=f[['open','high','low','close']].to_numpy();vol=f[spec.source].to_numpy();days=f.index.asi8//86400000000000
 eq,led,dd=simulate(ohlc,side,vol,f.prior_volume.to_numpy(),days,a,b,spec.width,spec.stop_sigma,float(spec.target.rstrip('R')) if spec.target!='pivot' else 1.,spec.target=='pivot',spec.family=='fade',spec.risk,fee/10000,slip/10000,cap)
 years=(pd.Timestamp(end)-pd.Timestamp(start)).days/365.2425;ret=eq[-1]/100000-1;cagr=max(0,1+ret)**(1/years)-1;score=np.log(max(1e-10,1+ret))/years-1.5*dd
 return {'net_return':ret,'cagr':cagr,'max_drawdown_adverse_daily_path':dd,'trades':len(led),'wins':int((led[:,9]>0).sum()),'win_rate':float((led[:,9]>0).mean()) if len(led) else 0.,'score':score,'fee_bps_per_side':fee,'slippage_bps_per_side':slip,'account_exposure_cap':cap},eq,led,a,b

def export(root,name,symbol,spec,f,out,start,end,selection):
 d,eq,led,a,b=out;p=root/name;p.mkdir(parents=True,exist_ok=True);np.testing.assert_allclose(led[:,7]-led[:,8],led[:,9],rtol=1e-10,atol=1e-6);np.testing.assert_allclose(100000+np.cumsum(led[:,9]),led[:,11],rtol=1e-10,atol=1e-6);flows=np.zeros(b-a)
 for row in led:flows[int(row[0])-a]+=row[9]
 np.testing.assert_allclose(100000+np.cumsum(flows),eq,rtol=1e-10,atol=1e-6);balance=pd.Series(eq,index=f.index[a:b]);calendar=pd.date_range(start,pd.Timestamp(end)-pd.Timedelta(days=1),freq='D');daily=balance.reindex(calendar).ffill().fillna(100000);annual=[]
 for y in range(2021,2026):
  x=pd.Timestamp(f'{y}-09-01');z=pd.Timestamp(f'{y+1}-09-01');begin=100000 if x==pd.Timestamp(start) else float(daily.loc[x-pd.Timedelta(days=1)]);finish=float(daily.loc[z-pd.Timedelta(days=1)]);annual.append({'start':str(x.date()),'end_exclusive':str(z.date()),'net_return':finish/begin-1})
 rolling=(daily/daily.shift(365)-1).dropna();d.update(name=name,symbol=symbol,period_start=start,period_end_exclusive=end,selection=selection,annual_returns=[x['net_return'] for x in annual],average_annual_return=float(np.mean([x['net_return'] for x in annual])),positive_anniversary_years=sum(x['net_return']>0 for x in annual),minimum_rolling_365d=float(rolling.min()),maximum_rolling_365d=float(rolling.max()),daily_data_only=True,execution_verified=False);d['historical_65pct_cagr_gate']=d['cagr']>=.65 and d['trades']>=200
 write(p/'METRICS.json',d);write(p/'STRATEGY.json',asdict(spec));write(p/'AUDIT.json',{'passed':True,'trades':len(led),'ending_equity':eq[-1],'net_pnl':float(led[:,9].sum()),'gross_pnl':float(led[:,7].sum()),'fees':float(led[:,8].sum())})
 trades=pd.DataFrame(led,columns=['row_index','side','quantity_shares','entry','exit','stop','target','gross_pnl','fees','net_pnl','equity_before','equity_after']);trades.insert(0,'session_date',[str(f.index[int(i)].date()) for i in led[:,0]]);trades['entry_time_precision']='within session, exact time unavailable from daily OHLC';trades.to_csv(p/'ALL_TRADES.csv',index=False);daily.rename('equity').to_csv(p/'DAILY_EQUITY.csv',index_label='date');pd.DataFrame(annual).to_csv(p/'ANNIVERSARY_YEARS.csv',index=False);rolling.to_csv(p/'ROLLING_365D.csv',index_label='window_end_date');return d

def main():
 for sym in ['SPY','QQQ']:
  root=ROOT/'results'/sym;root.mkdir(parents=True,exist_ok=True);f=context(sym);specs=[]
  for src,fam,direction,width,st in itertools.product(['iv1','iv5','rv20'],['fade','breakout'],['long','short','trend','counter_trend','prior_reversal'],[.25,.5,1.,1.5],[.25,.5,1.]):
   for target in (['pivot','1R'] if fam=='fade' else ['1R','2R']):specs.append(EquitySpec(src,fam,direction,width,st,target))
  write(root/'PROTOCOL.json',{'written_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'scope':'Daily OHLC adverse-sequence diagnostic, not ES5m replication; limit fills/depth/latency unverified','development':['2011-01-03','2020-01-01'],'validation':['2020-01-01','2021-08-25'],'evaluation':['2021-09-01','2026-09-01'],'grid':[asdict(s) for s in specs],'selection':'Top24 development loggrowth-minus1.5DD with>=200trades; validation primary positive net and>=30trades. Freeze before evaluation.','fees_slippage_bps_each':[1,1],'intraday_notional_cap':4,'same_day_flat':True});dev=[]
  for s in specs:d,*_=run(f,s,'2011-01-03','2020-01-01');dev.append({'spec':asdict(s),'id':s.id,'metrics':d})
  write(root/'DEVELOPMENT.json',dev);top=sorted([x for x in dev if x['metrics']['trades']>=200],key=lambda x:x['metrics']['score'],reverse=True)[:24];val=[]
  for row in top:
   for risk in [.005,.01,.02]:s=EquitySpec(**{**row['spec'],'risk':risk});d,*_=run(f,s,'2020-01-01','2021-08-25');val.append({'spec':asdict(s),'id':s.id,'metrics':d})
  write(root/'VALIDATION.json',val);ranked=sorted([r for r in val if r['metrics']['trades']>=30],key=lambda x:x['metrics']['score'],reverse=True);chosen=ranked[0] if ranked[0]['metrics']['net_return']>0 else None;write(root/'FROZEN.json',{'primary':chosen,'finalists':ranked[:6],'frozen_at_utc':pd.Timestamp.now(tz='UTC').isoformat()});output=[]
  for row in ranked[:6]:
   s=EquitySpec(**row['spec']);primary=chosen and row['id']==chosen['id'];name=('PRIMARY_' if primary else 'FINALIST_')+s.id;out=run(f,s,'2021-09-01','2026-09-01');d=export(root,name,sym,s,f,out,'2021-09-01','2026-09-01','validation_selected' if primary else 'fixed_finalist_diagnostic');output.append(d);print(sym,name,d['cagr'],d['trades'],d['annual_returns'],flush=True)
   if primary:
    for label,fee,slip,cap in [('NO_COST',0,0,4),('COST_DOUBLE',2,2,4),('UNVERIFIED_20X_SENSITIVITY',1,1,20)]:out=run(f,s,'2021-09-01','2026-09-01',fee,slip,cap);output.append(export(root,label,sym,s,f,out,'2021-09-01','2026-09-01','sensitivity_not_new_validated_strategy'))
  write(root/'INDEX.json',output)
if __name__=='__main__':main()

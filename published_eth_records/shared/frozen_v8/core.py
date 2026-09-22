"""Parrish Lyon V8: causal daily/weekly IV bands and 72-hour, 5R executions.
IV bands are model range estimates, not dealer-position/open-interest walls.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
from numba import njit
from input_v7 import load_market, verify_iv
DAY=86400000

@dataclass(frozen=True)
class Spec:
    family: str = 'reject'
    horizon: str = 'daily'
    multiplier: float = 1.5
    timeframe: int = 60
    buffer: float = .10
    regime: str = 'all'
    scale: str = 'latest'
    def validate(self):
        if self.family not in ('reject','break','retest'):raise ValueError('invalid family')
        if self.horizon not in ('daily','weekly','confluence'):raise ValueError('invalid horizon')
        if self.timeframe not in (15,60,240):raise ValueError('unsupported timeframe')
        if self.regime not in ('all','trend','long','short','iv_falling','iv_rising'):raise ValueError('invalid regime')
        if self.scale not in ('latest','mean5','historical'):raise ValueError('invalid scale')
        if not 0<self.multiplier<=3 or not 0<=self.buffer<=1:raise ValueError('invalid band/stop')
        return self
    @property
    def id(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:14]

@dataclass(frozen=True)
class Execution:
    risk: float = .02
    cap: float = 5.
    contract_leverage: int = 30
    reward_risk: float = 5.
    max_hold_hours: int = 72
    fee_bps: float = 5.
    slip_bps: float = 2.
    participation: float = .01
    cooldown_minutes: int = 60
    max_entries_day: int = 4
    daily_loss: float = .08
    weekly_loss: float = .15
    maintenance: float = .01
    collateral_buffer: float = .01
    funded_collateral: bool = True
    delay_minutes: int = 0
    initial: float = 10000.
    def validate(self):
        if not 0<self.risk<=.08 or not 0<self.cap<=30:raise ValueError('invalid account risk/exposure')
        if self.contract_leverage!=30 or self.reward_risk!=5.:raise ValueError('this experiment requires 30x contract setting and 5R')
        if not 1<=self.max_hold_hours<=72 or self.delay_minutes<0:raise ValueError('invalid timing')
        if not 0<self.daily_loss<self.weekly_loss<1:raise ValueError('invalid circuits')
        if not 0<self.participation<=1 or min(self.fee_bps,self.slip_bps,self.maintenance,self.collateral_buffer)<0:raise ValueError('invalid costs/collateral')
        if not np.isfinite([v for v in asdict(self).values() if isinstance(v,(int,float))]).all():raise ValueError('nonfinite config')
        return self

LEDGER=('entry_index','exit_index','side','quantity','entry_price','exit_price','initial_stop','initial_target',
        'entry_fee','exit_fee','funding_paid','gross_pnl','net_pnl','equity_before','equity_after',
        'entry_exposure','initial_margin_30x','allocated_collateral','reason','exit_at_open','missing_mark_minutes','signal_row')
REASONS={1:'stop',2:'target',3:'max_hold',4:'modeled_isolated_liquidation',5:'daily_risk',6:'weekly_risk',7:'end_of_test'}

def levels(ts,m,iv):
    n=len(ts)//1440;index=pd.to_datetime(ts[::1440],unit='ms',utc=True)
    d=pd.DataFrame({'close':m[1439::1440,3], 'high':m[:,1].reshape(n,1440).max(axis=1),
                    'low':m[:,2].reshape(n,1440).min(axis=1)},index=index)
    d['reference']=d.close.shift(1)
    src=iv.rename(columns={'close':'iv'})[['timestamp','iv']].copy()
    src['available_ms']=src.timestamp+DAY+60000
    joined=pd.merge_asof(pd.DataFrame({'decision_ms':ts[::1440]+60000}),src,left_on='decision_ms',right_on='available_ms',direction='backward',tolerance=DAY-1)
    d['iv']=joined.iv.to_numpy();d['iv_source_ms']=joined.timestamp.to_numpy();d['iv_available_ms']=joined.available_ms.to_numpy()
    d['sigma']=d.iv/100/np.sqrt(365.);d['mean5']=d.sigma.rolling(5,min_periods=5).mean()
    up=np.log(d.high/d.reference)/d.sigma;down=np.log(d.reference/d.low)/d.sigma
    d['up_calib']=up.clip(lower=0).rolling(200,min_periods=30).quantile(.75).shift(1)
    d['down_calib']=down.clip(lower=0).rolling(200,min_periods=30).quantile(.75).shift(1)
    d['trend']=np.sign((d.close/d.close.ewm(span=40,adjust=False).mean()-1).shift(1))
    d['iv_change']=d.iv.diff(3)
    wk=(np.arange(n)-index.dayofweek.to_numpy()).astype(int)
    safe=np.maximum(wk,0)
    for k in ['reference','sigma','mean5','up_calib','down_calib','iv_available_ms']:
        d['week_'+k]=d[k].to_numpy()[safe]
    d['week_origin_ms']=(ts[::1440]-index.dayofweek.to_numpy()*DAY)
    d.loc[wk<0,[c for c in d if c.startswith('week_')]]=np.nan
    return d

def bars(ts,m,tf):
    n=len(ts);idx=pd.to_datetime(ts[::tf],unit='ms',utc=True)
    b=pd.DataFrame({'open':m[::tf,0],'high':m[:,1].reshape(-1,tf).max(axis=1),'low':m[:,2].reshape(-1,tf).min(axis=1),
                    'close':m[tf-1::tf,3]},index=idx)
    b['swing_low']=b.low.rolling(3,min_periods=3).min();b['swing_high']=b.high.rolling(3,min_periods=3).max()
    b['entry_index']=np.arange(tf,n+1,tf)
    return b

def make_signals(ts,m,d,b,spec):
    spec.validate();tf=spec.timeframe;day=((b.index.asi8//1000000-ts[0])//DAY).astype(int)
    dayref=d.reference.to_numpy()[day];weekref=d.week_reference.to_numpy()[day]
    sig=d['sigma' if spec.scale!='mean5' else 'mean5'].to_numpy()[day]
    wsig=d['week_sigma' if spec.scale!='mean5' else 'week_mean5'].to_numpy()[day]*np.sqrt(7)
    uc=d.up_calib.to_numpy()[day] if spec.scale=='historical' else np.ones(len(b))
    lc=d.down_calib.to_numpy()[day] if spec.scale=='historical' else np.ones(len(b))
    wuc=d.week_up_calib.to_numpy()[day] if spec.scale=='historical' else np.ones(len(b))
    wlc=d.week_down_calib.to_numpy()[day] if spec.scale=='historical' else np.ones(len(b))
    du=dayref*np.exp(spec.multiplier*sig*uc);dl=dayref*np.exp(-spec.multiplier*sig*lc)
    wu=weekref*np.exp(spec.multiplier*wsig*wuc);wl=weekref*np.exp(-spec.multiplier*wsig*wlc)
    upper,lower=(du,dl) if spec.horizon!='weekly' else (wu,wl)
    cl=b.close.to_numpy();op=b.open.to_numpy();hi=b.high.to_numpy();lo=b.low.to_numpy();prev=np.r_[np.nan,cl[:-1]]
    same_day=day==np.r_[-1,day[:-1]]
    same_week=d.week_origin_ms.to_numpy()[day]==np.r_[np.nan,d.week_origin_ms.to_numpy()[day[:-1]]]
    same=same_day if spec.horizon!='weekly' else same_week
    if spec.family=='reject':
        buy=(lo<=lower)&(cl>lower)&(cl>op)
        sell=(hi>=upper)&(cl<upper)&(cl<op)
        sl=b.swing_low.to_numpy()-dayref*sig*spec.buffer
        ss=b.swing_high.to_numpy()+dayref*sig*spec.buffer
    elif spec.family=='break':
        buy=(cl>upper)&(prev<=upper)&(cl>op)&same
        sell=(cl<lower)&(prev>=lower)&(cl<op)&same
        sl=upper-dayref*sig*spec.buffer;ss=lower+dayref*sig*spec.buffer
    else:
        previous_high=pd.Series(hi).shift(1).rolling(8,min_periods=8).max().to_numpy()
        previous_low=pd.Series(lo).shift(1).rolling(8,min_periods=8).min().to_numpy()
        buy=(previous_high>upper+dayref*sig*.15)&(lo<=upper)&(cl>upper)&(cl>op)&same
        sell=(previous_low<lower-dayref*sig*.15)&(hi>=lower)&(cl<lower)&(cl<op)&same
        sl=np.minimum(b.swing_low.to_numpy(),upper)-dayref*sig*spec.buffer
        ss=np.maximum(b.swing_high.to_numpy(),lower)+dayref*sig*spec.buffer
    if spec.horizon=='confluence':
        if spec.family=='reject':buy &= lo<=weekref-.5*weekref*wsig;sell &= hi>=weekref+.5*weekref*wsig
        else:buy &= cl>weekref+.25*weekref*wsig;sell &= cl<weekref-.25*weekref*wsig
    trend=d.trend.to_numpy()[day]
    if spec.regime=='trend':buy &=trend>0;sell &=trend<0
    if spec.regime=='long':sell[:]=False
    if spec.regime=='short':buy[:]=False
    ivchg=d.iv_change.to_numpy()[day]
    if spec.regime=='iv_falling':buy &=ivchg<=0;sell &=ivchg<=0
    if spec.regime=='iv_rising':buy &=ivchg>0;sell &=ivchg>0
    side=np.where(buy&~sell,1,np.where(sell&~buy,-1,0)).astype(np.int8)
    stop=np.where(side>0,sl,ss)
    ei=b.entry_index.to_numpy(dtype=np.int64)
    available=b.index.asi8//1000000+tf*60000
    valid=np.isfinite(stop+sig+upper+lower+weekref)&(sig>0)&(stop>0)&(ei<len(ts))
    valid &= available>=d.iv_available_ms.to_numpy()[day]
    valid &= available>=d.week_iv_available_ms.to_numpy()[day]
    valid &= side*(cl-stop)>cl*.0005
    valid &= side*(cl-stop)<cl*.15
    valid &= side!=0
    return np.column_stack([ei[valid],side[valid],stop[valid],day[valid],upper[valid],lower[valid],d.iv_available_ms.to_numpy()[day][valid],d.week_iv_available_ms.to_numpy()[day][valid]]).astype(float)

@njit(cache=True)
def kernel(m,missing,candidates,a,b,execpars,grid,record):
    initial,risk,cap,lev,rr,hold,fee,slip,participation,cooldown,maxperday,daylim,weeklim,mm,buffer,funded,delay=execpars
    qty_step,tick,minnot=grid
    n=b-a;cash=initial;q=0.;side=0;entry=0.;st=0.;tp=0.;ei=0;ef=0.;fp=0.;margin=0.;coll=0.;before=initial;gap=0
    days=(b+1439)//1440-a//1440;daily=np.full(days+1,initial);daily_open=np.full(days,initial)
    ledger=np.zeros((len(candidates),len(LEDGER))) if record else np.zeros((0,len(LEDGER)))
    count=0;wins=0;sumwin=0.;sumloss=0.;maxexpo=0.;maxmargin=0.;totalfees=0.;totalfund=0.;liqcount=0;overnight=0
    di=a//1440;week=(di+5)//7;daybase=initial;weekbase=initial;daylocked=False;weeklocked=False;entries=0;cool=-1
    week=(di+2)//7
    ptr=0
    while ptr<len(candidates) and candidates[ptr,0]+delay<a:ptr+=1
    peak=initial;maxdd=0.;ddclose=0.;peakclose=initial;worsteq=initial;equity=initial;signalrow=0
    daily[a//1440-a//1440]=initial
    for i in range(a,b):
        open_eq=cash+side*q*(m[i,5]-entry)
        d=i//1440;w=(d+2)//7
        if d!=di:
            di=d;daybase=open_eq;daylocked=False;entries=0
            if q>0:overnight+=1
        if w!=week:week=w;weekbase=open_eq;weeklocked=False
        if i%1440==0:daily_open[d-a//1440]=open_eq
        if q==0:
            while ptr<len(candidates) and candidates[ptr,0]+delay<i:ptr+=1
            if ptr<len(candidates) and candidates[ptr,0]+delay==i:
                row=ptr;ptr+=1
                if not daylocked and not weeklocked and i>cool and entries<maxperday and cash>0:
                    s=int(candidates[row,1]);stop=candidates[row,2]
                    stop=(np.ceil(stop/tick) if s==1 else np.floor(stop/tick))*tick
                    ent=m[i,0]*(1+s*slip);ent=(np.ceil(ent/tick) if s==1 else np.floor(ent/tick))*tick
                    distance=s*(ent-stop)
                    target=ent+s*rr*distance;target=(np.ceil(target/tick) if s==1 else np.floor(target/tick))*tick
                    if distance>0 and target>0 and distance<ent*.20:
                        lossunit=distance+fee*(ent+stop)+slip*stop+tick
                        remaining=min(cash*risk,.8*(cash-daybase*(1-daylim)),.8*(cash-weekbase*(1-weeklim)))
                        collunit=ent/lev
                        if funded>0:collunit=max(collunit,distance+ent*(mm+buffer+.002)+fee*ent)
                        size=min(remaining/lossunit,cash*cap/ent,m[i-1,4]*participation,.9*cash/(collunit+ent*fee))
                        size=np.floor(max(0.,size)/qty_step)*qty_step
                        if size>0 and size*ent>=minnot:
                            q=size;side=s;entry=ent;st=stop;tp=target;ei=i;ef=q*entry*fee;fp=0.;before=cash;cash-=ef
                            coll=q*collunit;margin=q*entry/lev;gap=0;entries+=1;signalrow=row
                            maxexpo=max(maxexpo,q*entry/before);maxmargin=max(maxmargin,coll/before)
        if q>0:
            funding=side*q*m[i,5]*m[i,9]
            if i==ei:funding=max(0.,funding)
            cash-=funding;fp+=funding;gap+=int(missing[i])
            op=m[i,0];hi=m[i,1];lo=m[i,2];markop=m[i,5];markworst=m[i,7] if side==1 else m[i,6]
            beforeexit=cash+side*q*(markop-entry)
            closed=False;reason=0;atopen=0;exitprice=entry
            colopen=coll-fp+side*q*(markop-entry)
            if colopen<=mm*q*markop:closed=True;reason=4;exitprice=op;atopen=1
            elif side*(op-st)<=0:closed=True;reason=1;exitprice=op;atopen=1
            elif side*(op-tp)>=0:closed=True;reason=2;exitprice=op;atopen=1
            elif i-ei>=hold:closed=True;reason=3;exitprice=op;atopen=1
            elif beforeexit<=daybase*(1-daylim):closed=True;reason=5;exitprice=op;atopen=1;daylocked=True
            elif beforeexit<=weekbase*(1-weeklim):closed=True;reason=6;exitprice=op;atopen=1;weeklocked=True
            else:
                bound=cash+side*q*(markworst-entry);maxdd=max(maxdd,1-bound/max(peak,1e-12));worsteq=min(worsteq,bound)
                if coll-fp+side*q*(markworst-entry)<=mm*q*markworst:
                    closed=True;reason=4;exitprice=markworst
                elif (side==1 and lo<=st) or (side==-1 and hi>=st):closed=True;reason=1;exitprice=st
                elif (side==1 and hi>=tp) or (side==-1 and lo<=tp):closed=True;reason=2;exitprice=tp
                elif i==b-1:closed=True;reason=7;exitprice=m[i,3]
            if closed:
                exitprice*=1-side*slip;exitprice=(np.floor(exitprice/tick) if side==1 else np.ceil(exitprice/tick))*tick
                xf=q*exitprice*(.01 if reason==4 else fee)
                gross=side*q*(exitprice-entry);cash+=gross-xf;net=gross-ef-xf-fp
                if record:
                    ledger[count,:]=np.array([ei,i,side,q,entry,exitprice,st,tp,ef,xf,fp,gross,net,before,cash,q*entry/before,margin,coll,reason,atopen,gap,signalrow],dtype=np.float64)
                count+=1;wins+=int(net>0);sumwin+=max(0.,net);sumloss+=max(0.,-net);totalfees+=ef+xf;totalfund+=fp;liqcount+=int(reason==4)
                q=0.;side=0;cool=i+cooldown
            else:
                favorable=cash+side*q*((m[i,6] if side==1 else m[i,7])-entry)
                peak=max(peak,favorable)
        equity=cash+side*q*(m[i,8]-entry)
        peak=max(peak,equity);maxdd=max(maxdd,1-equity/max(peak,1e-12));peakclose=max(peakclose,equity);ddclose=max(ddclose,1-equity/max(peakclose,1e-12))
        if equity<=daybase*(1-daylim):daylocked=True
        if equity<=weekbase*(1-weeklim):weeklocked=True
        if i%1440==1439 or i==b-1:daily[d-a//1440+1]=equity
    stats=np.array([count,wins,sumwin,sumloss,totalfees,totalfund,liqcount,maxexpo,maxmargin,maxdd,ddclose,overnight,cash])
    return daily,ledger[:count] if record else ledger,stats

def run(m,missing,candidates,a,b,cfg,symbol,record=False):
    cfg.validate()
    grid=np.array([.001,.01,20.] if symbol=='ETHUSDT' else [.001,.1,100.])
    vals=np.array([cfg.initial,cfg.risk,cfg.cap,cfg.contract_leverage,cfg.reward_risk,cfg.max_hold_hours*60,cfg.fee_bps/10000,cfg.slip_bps/10000,cfg.participation,cfg.cooldown_minutes,cfg.max_entries_day,cfg.daily_loss,cfg.weekly_loss,cfg.maintenance,cfg.collateral_buffer,int(cfg.funded_collateral),cfg.delay_minutes])
    return kernel(m,missing,candidates,a,b,vals,grid,record)

def stats(out,start_ms,end_ms):
    daily,_,z=out;days=(end_ms-start_ms)/DAY
    dates=pd.date_range(pd.Timestamp(start_ms,unit='ms',tz='UTC'),periods=len(daily),freq='D')
    series=pd.Series(daily,index=dates);annual=[]
    for j in range(5):
        a=dates[0]+pd.DateOffset(years=j);b=dates[0]+pd.DateOffset(years=j+1)
        if a in series.index and b in series.index:annual.append(float(series[b]/series[a]-1))
    mon=series[series.index.weekday==0];weeks=mon.pct_change().dropna();cur=0;longest=0
    for v in weeks:
        cur=cur+1 if v<0 else 0;longest=max(longest,cur)
    roll=(series/series.shift(365)-1).dropna()
    gain=float(daily[-1]/daily[0]-1)
    return dict(net_return=gain,cagr=float(max(0.,1+gain)**(365.2425/days)-1),annual_returns=annual,
        mean_annual=float(np.mean(annual)) if len(annual)==5 else None,positive_years=sum(x>0 for x in annual),
        trades=int(z[0]),win_rate=float(z[1]/z[0]) if z[0] else 0,profit_factor=float(z[2]/z[3]) if z[3] else None,
        fees=float(z[4]),funding=float(z[5]),liquidations=int(z[6]),max_exposure=float(z[7]),max_collateral_equity=float(z[8]),
        conservative_drawdown=float(z[9]),close_drawdown=float(z[10]),overnight_position_day_boundaries=int(z[11]),
        worst_week=float(weeks.min()) if len(weeks) else None,longest_losing_weeks=longest,
        weekly_geometric=float((mon.iloc[-1]/mon.iloc[0])**(1/len(weeks))-1) if len(weeks) else None,
        complete_weeks=len(weeks),worst_rolling_year=float(roll.min()) if len(roll) else None,
        max_rolling_year=float(roll.max()) if len(roll) else None,days=days,initial=float(daily[0]),final=float(daily[-1]))

"""V5 separate engine derived from the preserved V4 simulator. Adds frozen absolute stops, targets and forecast deadlines; see engine_diff.patch. No order submission.

The kernel trades one market and at most one open position, records mark-to-market
account equity, and never replaces a realized loss with a configured loss limit.
OHLC stops are execution assumptions, not guaranteed fills. Historical venue
margin tiers, queue position and a full depth-based impact model are not present.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np
import pandas as pd
from numba import njit

COLS = ['open','high','low','close','volume','mark_open','mark_high','mark_low','mark_close','funding_rate']
REASONS = {1:'stop',2:'target',3:'opposite',4:'timeout',5:'liquidation',6:'weekly_circuit',7:'daily_circuit',8:'end',9:'profit_lock'}

@dataclass(frozen=True)
class Config:
    initial_equity: float = 10_000.
    risk_fraction: float = .005
    leverage_cap: float = 20.
    fee_bps: float = 5.
    slippage_bps: float = 2.
    participation: float = .01
    target_r: float = 2.
    max_hold_seconds: int = 7200
    cooldown_seconds: int = 300
    weekly_stop: float = .04
    daily_stop: float = .015
    maintenance: float = .01
    liquidation_fee_bps: float = 100.
    trail_r: float = 0.
    profit_lock: float = 0.
    exit_on_opposite: bool = True
    entry_delay_bars: int = 1
    max_entries_daily: int = 300
    force_20x: bool = False
    quantity_step: float = .001
    price_tick: float = .01
    minimum_notional: float = 20.

    def validate(self):
        for k,v in asdict(self).items():
            if not np.isfinite(v): raise ValueError(f'{k} must be finite')
        if self.initial_equity <= 0 or not 0 < self.risk_fraction <= 1: raise ValueError('bad equity/risk')
        if not 0 < self.leverage_cap <= 20: raise ValueError('leverage cap exceeds 20x')
        if not 0 < self.participation <= 1: raise ValueError('bad participation')
        if min(self.fee_bps,self.slippage_bps,self.liquidation_fee_bps)<0: raise ValueError('negative costs')
        if self.slippage_bps>=10000 or self.target_r<=0: raise ValueError('bad slippage/target')
        if not 0<self.weekly_stop<1 or not 0<self.daily_stop<1: raise ValueError('bad loss limits')
        if not 0<=self.maintenance<1: raise ValueError('bad maintenance')
        for k in ['max_hold_seconds','cooldown_seconds','entry_delay_bars','max_entries_daily']:
            if int(getattr(self,k))!=getattr(self,k): raise ValueError(f'{k} must be integer')
        if self.entry_delay_bars<1 or not 1<=self.max_entries_daily<=300: raise ValueError('bad entry controls')
        if min(self.max_hold_seconds,self.cooldown_seconds,self.trail_r,self.profit_lock)<0: raise ValueError('negative time/control')
        if self.quantity_step<=0 or self.price_tick<=0 or self.minimum_notional<=0:raise ValueError('nonpositive instrument grid')

@njit(cache=True)
def _run(m,ts,sig,stop,absolute_target,expiry,start,end,p,record):
    # Position value is quantity times trade price; MTM uses the mark, not the last trade.
    n=end-start; eq=np.empty(n); eq_open=np.empty(n); eq_low=np.empty(n)
    ledger=np.empty((min(2*n, int((ts[end-1]-ts[start])//86400+3)*int(p[17])+100) if record else 0, 16)); nt=0
    initial,risk,lev,fee,slip,part,rr,hold,cool,wstop,dstop,mm,liqfee,trail,profitlock,opposite,delay,maxday,force,qstep,ptick,min_notional=p
    deadline=0; bal=initial; q=0.; ent=0.; st=0.; target=0.; efee=0.; funding=0.; eind=0; estop=0.; pre_equity=initial
    weekbase=initial; daybase=initial; weekid=(ts[start]//86400+3)//7; dayid=ts[start]//86400
    weeklock=False; daylock=False; daily_entries=0; last_exit=-10**18
    fees=0.; fundpaid=0.; peak=initial; drawdown=0.; liquidations=0; maxlev=0.; entrysum=0.; wins=0; grosswin=0.; grossloss=0.; entries=0
    for i in range(start,end):
        j=i-start; op,hi,lo,cl,vol,mo,mh,ml,mc,fr=m[i]
        open_eq=bal+q*(mo-ent); eq_open[j]=open_eq
        d=ts[i]//86400; w=(d+3)//7
        # Week/day bases are pre-settlement MTM at the boundary, so settlement P&L belongs to the new period.
        if w!=weekid:
            weekid=w; weekbase=open_eq; weeklock=False
        if d!=dayid:
            dayid=d; daybase=open_eq; daylock=False; daily_entries=0
        if q!=0:
            payment=q*mo*fr; bal-=payment; funding+=payment; fundpaid+=payment
        open_eq=bal+q*(mo-ent)
        peak=max(peak,open_eq); drawdown=max(drawdown,1-open_eq/peak)
        if open_eq<=weekbase*(1-wstop): weeklock=True
        if open_eq<=daybase*(1-dstop): daylock=True
        reason=0; px=0.; exit_at_open=False
        if q!=0:
            side=1 if q>0 else -1
            if open_eq<=abs(q)*mo*mm:
                reason=5;px=op;exit_at_open=True
            elif weeklock: reason=6;px=op;exit_at_open=True
            elif daylock: reason=7;px=op;exit_at_open=True
            elif profitlock>0 and open_eq>=weekbase*(1+profitlock):
                reason=9;px=op;exit_at_open=True;weeklock=True
            elif side*(op-st)<=0:reason=1;px=op;exit_at_open=True
            elif side*(op-target)>=0:reason=2;px=op;exit_at_open=True
            elif i>eind and (ts[i]-ts[eind]>=hold or ts[i]>=deadline):reason=4;px=op;exit_at_open=True
            elif opposite and i>=int(delay) and sig[i-int(delay)]==-side:reason=3;px=op;exit_at_open=True
        # An existing-position exit at the open is processed before the new signal.
        if reason!=0:
            side=1 if q>0 else -1; fill=px*(1-side*slip);fill=(np.floor(fill/ptick+1e-10) if side==1 else np.ceil(fill/ptick-1e-10))*ptick; exfee=abs(q)*fill*(liqfee if reason==5 else fee)
            pnl=q*(fill-ent);bal+=pnl-exfee;fees+=exfee;net=pnl-efee-exfee-funding
            if record:
                ledger[nt]=np.array([eind,i,side,abs(q),ent,fill,efee,exfee,funding,pnl,net,bal,reason,pre_equity,entrysum,ts[i]])
            nt+=1; wins+=int(net>0);grosswin+=max(net,0);grossloss+=max(-net,0);liquidations+=int(reason==5)
            q=0.;last_exit=ts[i]
        # No same-bar re-entry after an exit: even zero cooldown waits for another bar.
        if bal<=0:
            weeklock=True;daylock=True
        if q==0 and not weeklock and not daylock and i>=int(delay) and ts[i]>last_exit and ts[i]-last_exit>=cool and daily_entries<int(maxday):
            s=int(sig[i-int(delay)]);sf=stop[i-int(delay)]
            if s!=0 and np.isfinite(sf) and sf>0 and s*(op-sf)>0 and expiry[i-int(delay)]>ts[i]:
                ent0=op*(1+s*slip)
                ent0=(np.ceil(ent0/ptick-1e-10) if s==1 else np.floor(ent0/ptick+1e-10))*ptick
                dist=s*(ent0-sf)
                # Reserve entry/exit costs and modeled slippage inside the trade-risk budget.
                risk_per_unit=dist+ent0*(2*fee+2*slip)+2*ptick
                remaining_week=max(0.,bal-weekbase*(1-wstop)); remaining_day=max(0.,bal-daybase*(1-dstop))
                budget=min(bal*risk,remaining_week*.8,remaining_day*.8)
                quant=min(budget/risk_per_unit,bal*lev/ent0,m[i-1,4]*part)
                if force: quant=min(bal*lev/ent0,m[i-1,4]*part)
                quant=np.floor(quant/qstep)*qstep
                candidate_target=absolute_target[i-int(delay)]
                if not np.isfinite(candidate_target):candidate_target=ent0+s*dist*rr
                valid_target=candidate_target>0 and s*(candidate_target-ent0)>0
                if quant>0 and budget>1e-10 and ent0>0 and quant*ent0>=min_notional and valid_target:
                    pre_equity=bal;ent=ent0;q=s*quant;efee=quant*ent*fee;bal-=efee;fees+=efee
                    funding=0.;eind=i;estop=dist;st=sf;target=candidate_target;deadline=expiry[i-int(delay)]
                    entrysum=quant*ent/pre_equity;maxlev=max(maxlev,entrysum);entries+=1;daily_entries+=1
                    # Deliberately no favorable credit to a new position in a funding-settlement bar.
                    newpay=max(q*mo*fr,0.);bal-=newpay;fundpaid+=newpay;funding+=newpay
        reason=0;px=0.;loweq=bal
        if q!=0:
            side=1 if q>0 else -1;adverse_mark=ml if side==1 else mh
            adverse_eq=bal+q*(adverse_mark-ent)
            # Fixed-tier conservative approximation, evaluated before ambiguous stop/target order.
            liqprice=(ent-bal/q)/(1-side*mm)
            if adverse_eq<=abs(q)*adverse_mark*mm:
                reason=5;px=max(lo,min(hi,liqprice))
            else:
                # Account-level protective stop on the traded price. A mark/trade dislocation can still breach the account limit.
                weekly_px=ent+(weekbase*(1-wstop)-bal)/q
                daily_px=ent+(daybase*(1-dstop)-bal)/q
                effective=st;why=1
                if side*(weekly_px-effective)>0:effective=weekly_px;why=6
                if side*(daily_px-effective)>0:effective=daily_px;why=7
                hitstop=(lo<=effective) if side==1 else (hi>=effective)
                hittarget=(hi>=target) if side==1 else (lo<=target)
                if hitstop:
                    reason=why;px=op if side*(op-effective)<=0 else effective
                elif hittarget: reason=2;px=target
            if reason!=0:
                fill=px*(1-side*slip);fill=(np.floor(fill/ptick+1e-10) if side==1 else np.ceil(fill/ptick-1e-10))*ptick;exfee=abs(q)*fill*(liqfee if reason==5 else fee)
                pnl=q*(fill-ent);bal+=pnl-exfee;fees+=exfee;net=pnl-efee-exfee-funding
                if record:
                    # Intrabar close timestamp is a bar-end upper bound, not an asserted exact fill time.
                    step=ts[i]-ts[i-1] if i>0 else 60
                    ledger[nt]=np.array([eind,i,side,abs(q),ent,fill,efee,exfee,funding,pnl,net,bal,reason,pre_equity,entrysum,ts[i]+step])
                nt+=1;wins+=int(net>0);grosswin+=max(net,0);grossloss+=max(-net,0);liquidations+=int(reason==5)
                q=0.;last_exit=ts[i];loweq=min(eq_open[j],bal,adverse_eq) if reason==2 else min(eq_open[j],bal)
                if reason==6:weeklock=True
                if reason==7:daylock=True
            else:
                loweq=adverse_eq
                # Trailing updates use only completed bars and take effect on the next bar.
                if trail>0:
                    proposed=(hi-trail*estop) if side==1 else (lo+trail*estop)
                    st=max(st,proposed) if side==1 else min(st,proposed)
        if i==end-1 and q!=0:
            side=1 if q>0 else -1;fill=cl*(1-side*slip);fill=(np.floor(fill/ptick+1e-10) if side==1 else np.ceil(fill/ptick-1e-10))*ptick;exfee=abs(q)*fill*fee
            pnl=q*(fill-ent);bal+=pnl-exfee;fees+=exfee;net=pnl-efee-exfee-funding
            if record:ledger[nt]=np.array([eind,i,side,abs(q),ent,fill,efee,exfee,funding,pnl,net,bal,8,pre_equity,entrysum,ts[i]+(ts[i]-ts[i-1])])
            nt+=1;wins+=int(net>0);grosswin+=max(net,0);grossloss+=max(-net,0);q=0.;loweq=min(loweq,bal)
        value=bal+q*(mc-ent)
        eq[j]=value;eq_low[j]=loweq
        peak=max(peak,value);drawdown=max(drawdown,1-min(loweq,value)/peak)
        if value<=weekbase*(1-wstop):weeklock=True
        if value<=daybase*(1-dstop):daylock=True
    stats=np.array([bal,fees,fundpaid,nt,wins,grosswin,grossloss,liquidations,maxlev,drawdown,entries])
    return eq,eq_open,eq_low,ledger[:nt] if record else ledger,stats

TRADE_COLS=['entry_index','exit_index','side','quantity','entry_price','exit_price','entry_fee','exit_fee','funding_paid','gross_pnl','net_pnl','balance_after','reason_code','equity_before','entry_leverage','exit_epoch_upper_bound']

def run(m,ts,signals,stops,absolute_target,expiry,cfg=Config(),start=0,end=None,record=False):
    cfg.validate();end=len(ts) if end is None else end
    if not 0<=start<end<=len(ts):raise ValueError('bad bounds')
    if len(signals)!=len(ts) or len(stops)!=len(ts) or np.ndim(signals)!=1 or np.ndim(stops)!=1:raise ValueError('unaligned signals')
    if m.shape!=(len(ts),10):raise ValueError('unaligned prices')
    if not np.isin(signals,[-1,0,1]).all():raise ValueError('invalid signal direction')
    p=np.array([cfg.initial_equity,cfg.risk_fraction,cfg.leverage_cap,cfg.fee_bps/1e4,cfg.slippage_bps/1e4,cfg.participation,cfg.target_r,cfg.max_hold_seconds,cfg.cooldown_seconds,cfg.weekly_stop,cfg.daily_stop,cfg.maintenance,cfg.liquidation_fee_bps/1e4,cfg.trail_r,cfg.profit_lock,int(cfg.exit_on_opposite),cfg.entry_delay_bars,cfg.max_entries_daily,int(cfg.force_20x),cfg.quantity_step,cfg.price_tick,cfg.minimum_notional],dtype=float)
    return _run(m,ts,signals,stops,absolute_target,expiry,start,end,p,record)


def validate_data(m,ts):
    if m.ndim!=2 or m.shape!=(len(ts),10) or len(ts)<2:raise ValueError('shape')
    if not np.isfinite(m).all():raise ValueError('nonfinite data')
    if np.any(np.diff(ts)<=0) or not np.all(np.diff(ts)==ts[1]-ts[0]):raise ValueError('missing or duplicate bars')
    for ofs in [0,5]:
        op,hi,lo,cl=(m[:,ofs+k] for k in range(4))
        if np.any(lo<=0) or np.any(hi<np.maximum(op,cl)) or np.any(lo>np.minimum(op,cl)):raise ValueError('OHLC inconsistency')
    if np.any(m[:,4]<0) or np.any(np.abs(m[:,9])>1):raise ValueError('bad volume/funding')


def load_npz(path):
    with np.load(path) as z:
        raw={k:z[k].copy() for k in z.files}
    if 'funding_verified' not in raw or not np.asarray(raw['funding_verified'],dtype=bool).all():raise ValueError('unverified funding coverage')
    if not ((raw['timestamp']>=1_000_000_000_000)&(raw['timestamp']<10_000_000_000_000)).all():raise ValueError('expected millisecond perpetual timestamps')
    ts=(raw['timestamp']//1000).astype(np.int64)
    m=np.ascontiguousarray(np.column_stack([raw[k] for k in COLS]),dtype=float)
    validate_data(m,ts)
    return m,ts,raw


def summary(out,ts,start,end,cfg=Config()):
    eq,eo,elow,ledger,stats=out;t=ts[start:end]; step=int(t[1]-t[0]) if len(t)>1 else 60
    # Weekly return includes every MTM change from one Monday boundary to the next.
    boundaries=np.flatnonzero((t%604800)==345600)
    rows=[]
    for a,b in zip(boundaries[:-1],boundaries[1:]):
        if t[b]-t[a]==604800:
            rows.append((int(t[a]),float(eo[b]/eo[a]-1)))
    # If the data ends at Sunday 23:59, the final close is the next Monday boundary.
    if len(boundaries) and t[-1]+step-t[boundaries[-1]]==604800:
        a=boundaries[-1];rows.append((int(t[a]),float(eq[-1]/eo[a]-1)))
    weeks=np.array([x[1] for x in rows]);streak=0;longest=0;active_streak=0;active_longest=0
    for r in weeks:
        streak=streak+1 if r< -1e-12 else 0;longest=max(longest,streak)
        if r< -1e-12:active_streak+=1
        elif r>1e-12:active_streak=0
        active_longest=max(active_longest,active_streak)
    maxentries=None
    if len(ledger):
        days=ts[ledger[:,0].astype(int)]//86400;maxentries=int(np.unique(days,return_counts=True)[1].max())
    ret=float(eq[-1]/cfg.initial_equity-1)
    geo=float(np.exp(np.log1p(weeks).mean())-1) if len(weeks) and np.all(weeks>-1) else (-1. if len(weeks) else None)
    s={'net_return':ret,'geometric_weekly':geo,'arithmetic_weekly':float(weeks.mean()) if len(weeks) else None,'worst_week':float(weeks.min()) if len(weeks) else None,'best_week':float(weeks.max()) if len(weeks) else None,'complete_weeks':len(weeks),'weeks_at_10pct':int((weeks>=.1-1e-12).sum()),'positive_weeks':int((weeks>1e-12).sum()),'negative_weeks':int((weeks< -1e-12).sum()),'flat_weeks':int((abs(weeks)<=1e-12).sum()),'longest_losing_streak':longest,'active_week_losing_streak':active_longest,'trades':int(stats[3]),'win_rate':float(stats[4]/stats[3]) if stats[3] else None,'profit_factor':float(stats[5]/stats[6]) if stats[6] else None,'fees':float(stats[1]),'funding_paid':float(stats[2]),'liquidations':int(stats[7]),'max_entry_leverage':float(stats[8]),'conservative_intrabar_drawdown':float(stats[9]),'max_daily_entries':maxentries,'initial_equity':cfg.initial_equity,'final_equity':float(eq[-1])}
    s['gates']={'geometric_weekly_at_least_10pct':geo is not None and geo>=.1,'every_week_at_least_10pct':bool(len(weeks) and np.all(weeks>=.1)),'worst_week_at_least_minus_5pct':bool(len(weeks) and weeks.min()>=-.05),'max_3_losing_calendar_weeks':longest<=3,'at_most_300_daily_entries':maxentries is not None and maxentries<=300,'no_liquidation':int(stats[7])==0,'at_least_52_complete_weeks':len(weeks)>=52}
    # Research targets are not live readiness. Explicit completeness and execution verification are separate.
    s['passes_historical_average_target']=all(s['gates'][k] for k in ['geometric_weekly_at_least_10pct','worst_week_at_least_minus_5pct','max_3_losing_calendar_weeks','at_most_300_daily_entries','no_liquidation','at_least_52_complete_weeks'])
    return s,rows

from dataclasses import dataclass,asdict
import hashlib,json
import numpy as np
import pandas as pd
from .engine import Config,_run

@dataclass(frozen=True)
class TradeSpec:
    family:str='fade'
    quantile:float=.75
    stop_buffer:float=.5
    target:str='pivot'
    regime:str='all'
    timeframe:int=5
    @property
    def id(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:12]

def bar_view(raw,timeframe=5):
    n=len(raw['timestamp']);tf=timeframe
    if n%tf:raise ValueError('incomplete execution signal bar')
    return {'timestamp':raw['timestamp'][::tf],'open':raw['open'][::tf],
            'high':raw['high'].reshape(-1,tf).max(axis=1),'low':raw['low'].reshape(-1,tf).min(axis=1),
            'close':raw['close'][tf-1::tf],'ix':np.arange(tf-1,n,tf)}

def signals(raw,daily,surface,bar,spec):
    """Rejection confirmation is completed-bar only; all walls are frozen at origin.
    Entry is the following minute. Absolute stop/target and forecast expiry freeze
    at the signal. Current/late-session extrema never feed that origin's surface.
    """
    ts=raw['timestamp'];di=((bar['timestamp']-ts[0])//86400000).astype(int)
    q=spec.quantile
    upper=surface[f'high_q{q:.6f}'].to_numpy()[di]
    lower=surface[f'low_q{1-q:.6f}'].to_numpy()[di]
    anchor=surface.reference_price.to_numpy()[di]
    sigma=surface.rv_daily_sigma.to_numpy()[di]
    meanlo=surface.mean_low_proxy.to_numpy()[di];meanhi=surface.mean_high_proxy.to_numpy()[di]
    c,op,hi,lo=(bar[k] for k in ('close','open','high','low'))
    trend=np.sign((daily.close/daily.close.ewm(span=50,adjust=False).mean()-1).shift(1)).to_numpy()[di]
    same=di==np.r_[-1,di[:-1]];prev=np.r_[np.nan,c[:-1]]
    if spec.family=='fade':
        buy=(lo<=lower)&(c>lower)&(c>op)&(c<anchor)
        sell=(hi>=upper)&(c<upper)&(c<op)&(c>anchor)
        slong=lower-anchor*sigma*spec.stop_buffer
        sshort=upper+anchor*sigma*spec.stop_buffer
        if spec.target=='pivot':tlong=tshort=anchor
        else:tlong=meanhi;tshort=meanlo
    elif spec.family=='break':
        buy=(c>upper)&(prev<=upper)&(c>op)&same
        sell=(c<lower)&(prev>=lower)&(c<op)&same
        slong=upper-anchor*sigma*spec.stop_buffer
        sshort=lower+anchor*sigma*spec.stop_buffer
        rr=float(spec.target)
        tlong=c+(c-slong)*rr;tshort=c-(sshort-c)*rr
    elif spec.family=='toward_low':
        buy=np.zeros(len(c),bool);sell=(bar['timestamp']%86400000==0)
        slong=lower-anchor*sigma*.5;sshort=surface.high_q0_9.to_numpy()[di] if 'high_q0_9' in surface else surface['high_q0.900000'].to_numpy()[di]
        tlong=anchor;tshort=surface['low_q0.973684'].to_numpy()[di] if spec.target=='near97' else meanlo
    else:raise ValueError('unknown execution hypothesis')
    if spec.regime=='aligned':buy &= trend>0;sell &= trend<0
    elif spec.regime!='all':raise ValueError('unknown regime')
    side=np.where(buy,1,np.where(sell,-1,0)).astype(np.int8)
    stop=np.where(side>0,slong,sshort);target=np.where(side>0,tlong,tshort)
    valid=np.isfinite(stop+target+sigma+anchor)&(surface.sample_count.to_numpy()[di]>=20)
    valid &= (side*(c-stop)>c*.0005)&(side*(target-c)>c*.0002)&(stop>0)&(target>0)
    side[~valid]=0
    expiry=(surface.index.asi8//1000000000+surface.horizon_sessions.to_numpy()*86400)[di]
    size=len(ts);s=np.zeros(size,np.int8);st=np.full(size,np.nan);ta=np.full(size,np.nan);ex=np.zeros(size,np.int64)
    ix=bar['ix'];s[ix]=side;st[ix]=stop;ta[ix]=target;ex[ix]=expiry
    return s,st,ta,ex

def make_config(symbol,risk=.01,fee_bps=5.,slippage_bps=2.):
    grids={'ETHUSDT':(.001,.01,20.),'BTCUSDT':(.001,.1,100.),'XRPUSDT':(1.,.0001,5.)}
    step,tick,minnot=grids[symbol]
    return Config(risk_fraction=risk,leverage_cap=5.,fee_bps=fee_bps,slippage_bps=slippage_bps,
        participation=.01,max_hold_seconds=5*86400,cooldown_seconds=900,weekly_stop=.05,daily_stop=.025,
        exit_on_opposite=False,max_entries_daily=3,quantity_step=step,price_tick=tick,minimum_notional=minnot)

def simulate(m,ts,sg,cfg,a,b,record=True):
    cfg.validate()
    p=np.array([cfg.initial_equity,cfg.risk_fraction,cfg.leverage_cap,cfg.fee_bps/1e4,cfg.slippage_bps/1e4,cfg.participation,
        cfg.target_r,cfg.max_hold_seconds,cfg.cooldown_seconds,cfg.weekly_stop,cfg.daily_stop,cfg.maintenance,
        cfg.liquidation_fee_bps/1e4,cfg.trail_r,cfg.profit_lock,int(cfg.exit_on_opposite),cfg.entry_delay_bars,
        cfg.max_entries_daily,int(cfg.force_20x),cfg.quantity_step,cfg.price_tick,cfg.minimum_notional],float)
    return _run(m,ts,*sg,a,b,p,record)

"""One UTC-day trade using causally frozen, options-IV-derived daily range walls.
Copyright 2026 Parrish Lyon. Not dealer gamma/open-interest walls or a vendor replica.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
from numba import njit

DAY = 86400000
HASHES = {
 'BTCUSDT':'2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3',
 'ETHUSDT':'b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d'}
RULES=('long','short','momentum1','momentum3','momentum7','reversal1','reversal3',
       'iv_rise_short','iv_regime','conditional_mean','opening_momentum','opening_reversal','wall_rejection','wall_continuation')
LEDGER=('day_index','entry_index','exit_index','side','quantity','entry_price','exit_price',
 'initial_stop','initial_target','entry_fee','exit_fee','funding_paid','gross_pnl','net_pnl',
 'equity_before','equity_after','entry_exposure','reason','adverse_equity_bound','max_mark_observed_gap','day_status')
REASONS={1:'stop',2:'target',3:'scheduled_23_59_exit',4:'modeled_liquidation'}
SKIPS={0:'traded',1:'missing_or_stale_IV',2:'price_already_beyond_frozen_wall',3:'quantity_or_notional_below_minimum',4:'nonpositive_equity',5:'no_wall_trigger'}

@dataclass(frozen=True)
class Policy:
    rule: str = 'reversal1'
    entry_minute: int = 2
    wall_model: str = 'history_mean'
    stop_multiple: float = 1.0
    target_multiple: float = 0.5
    risk_fraction: float = 0.01
    exposure_cap: float = 5.0
    trigger_multiple: float = 0.25
    def validate(self):
        if self.rule not in RULES or self.wall_model not in ('latest_iv','mean5_iv','history_mean'):
            raise ValueError('unrecognized daily policy')
        if self.entry_minute not in (2,482):raise ValueError('only predeclared 00:02/08:02 UTC entries')
        if not 0 < self.risk_fraction <= .05 or not 0 < self.exposure_cap <= 5:
            raise ValueError('invalid account risk limits')
        if not 0 < self.stop_multiple <= 4 or not 0 <= self.target_multiple <= 4:
            raise ValueError('invalid wall multiples')
        if not np.isfinite(list(v for v in asdict(self).values() if isinstance(v,(int,float)))).all():raise ValueError('nonfinite policy')
        if not 0 < self.trigger_multiple < self.stop_multiple and self.rule=='wall_rejection':raise ValueError('stop must lie outside rejection wall')
        return self
    @property
    def id(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:16]

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def verify_iv(directory,currency):
    """Rebuild daily IV from the archived API JSON, not a renamed price-vol proxy."""
    p=Path(directory);receipts=json.loads((p/'PROVENANCE.json').read_text());pieces=[]
    selected=[x for x in receipts if x.get('currency')==currency and x.get('resolution')=='1D']
    for rec in selected:
        path=p/f"{currency}_1D_{rec['page']:03d}.json"
        if sha(path)!=rec['sha256']:raise ValueError('IV source receipt mismatch')
        body=json.loads(path.read_text());pieces.extend(body['result']['data'])
    raw=pd.DataFrame(pieces,columns=['timestamp','open','high','low','close']).sort_values('timestamp')
    repeated=raw[raw.timestamp.duplicated(False)]
    for _,g in repeated.groupby('timestamp'):
        if not (g[['open','high','low','close']].nunique()==1).all():raise ValueError('conflicting IV duplicate')
    raw=raw.drop_duplicates('timestamp').reset_index(drop=True)
    # API end bound is inclusive; exclude the 2026-09-01 candle outside the frozen input period.
    raw=raw[raw.timestamp<1788220800000].reset_index(drop=True)
    supplied=pd.read_csv(p/f'{currency}_1D.csv')
    if not np.array_equal(raw.timestamp,supplied.timestamp):raise ValueError('IV source row mismatch')
    np.testing.assert_allclose(raw.iloc[:,1:],supplied.iloc[:,1:],rtol=0,atol=1e-12)
    if not np.isfinite(raw.to_numpy()).all() or (raw.close<=0).any() or not (np.diff(raw.timestamp)==DAY).all():
        raise ValueError('IV data has nonfinite values, invalid prices, or missing days')
    return supplied,{'rows':len(raw),'csv_sha256':sha(p/f'{currency}_1D.csv'),'source_receipts':selected,
       'first_candle_utc':str(pd.Timestamp(raw.timestamp.iloc[0],unit='ms',tz='UTC')),
       'last_candle_utc':str(pd.Timestamp(raw.timestamp.iloc[-1],unit='ms',tz='UTC')),
       'index_tenor':'30-day forward annualized DVOL, observed daily; not a 1D-tenor option chain'}

def load_market(path,symbol):
    if sha(path)!=HASHES[symbol]:raise ValueError('market input hash mismatch')
    with np.load(path,allow_pickle=False) as z:
        ts=z['timestamp'];cols=['open','high','low','close','volume','mark_open','mark_high','mark_low','mark_close','funding_rate']
        m=np.column_stack([z[k] for k in cols]);fund=z['funding_verified']
        missing=~np.isfinite(m[:,5:9]).all(axis=1)
        for i in np.flatnonzero(missing):
            if i==0:raise ValueError('cannot bound missing first mark')
            prev=m[i-1,8];lo=z['missing_mark_15m_low'][i];hi=z['missing_mark_15m_high'][i]
            if not np.isfinite(lo+hi):lo=min(prev,m[i,2])*.95;hi=max(prev,m[i,1])*1.05
            m[i,5]=m[i,8]=prev;m[i,6]=max(hi,prev);m[i,7]=min(lo,prev)
    if ts[0]%DAY or len(ts)%1440 or not (np.diff(ts)==60000).all() or not fund.all():
        raise ValueError('incomplete UTC days or unverified funding')
    if not np.isfinite(m).all() or (m[:,:4]<=0).any() or (m[:,4]<0).any():raise ValueError('bad minute values')
    if (m[:,1]<m[:,[0,2,3]].max(axis=1)).any() or (m[:,2]>m[:,[0,1,3]].min(axis=1)).any():raise ValueError('bad OHLC')
    return ts,np.ascontiguousarray(m),missing

def daily_inputs(ts,m,iv):
    n=len(ts)//1440;index=pd.to_datetime(ts[::1440],unit='ms',utc=True)
    d=pd.DataFrame({'open':m[::1440,0],'high':m[:,1].reshape(n,1440).max(axis=1),
      'low':m[:,2].reshape(n,1440).min(axis=1),'close':m[1439::1440,3]},index=index)
    d['reference']=d.close.shift(1)
    # Day D-1 daily candle ends at D 00:00. One-minute modeled publication allowance.
    src=iv[['timestamp','close']].rename(columns={'close':'iv_close'}).copy()
    src['available_ms']=src.timestamp+DAY+60000
    joined=pd.merge_asof(pd.DataFrame({'decision_ms':ts[::1440]+60000}),src,
      left_on='decision_ms',right_on='available_ms',direction='backward',tolerance=DAY-1)
    d['iv_close']=joined.iv_close.to_numpy();d['iv_candle_ms']=joined.timestamp.to_numpy()
    d['iv_available_ms']=joined.available_ms.to_numpy();d['decision_ms']=ts[::1440]+60000
    d['sigma']=d.iv_close/100/np.sqrt(365.0)
    d['sigma_mean5']=d.sigma.rolling(5,min_periods=5).mean()
    r=np.log(d.close/d.reference)
    d['return1']=r.shift(1);d['return3']=np.log(d.close/d.close.shift(3)).shift(1)
    d['return7']=np.log(d.close/d.close.shift(7)).shift(1)
    d['iv_rise']=d.iv_close.diff()
    # Each historical day's excursion is scaled by its OWN then-available IV.
    up=np.log(d.high/d.reference)/d.sigma;down=np.log(d.reference/d.low)/d.sigma
    d['history_up_mean']=up.clip(lower=0).rolling(200,min_periods=30).mean().shift(1)
    d['history_down_mean']=down.clip(lower=0).rolling(200,min_periods=30).mean().shift(1)
    d['history_count']=up.rolling(200,min_periods=1).count().shift(1)
    # Historical conditional daily returns have matured before the decision day.
    prior_sign=np.sign(r.shift(1));target=r
    conditional=np.full(n,np.nan)
    for i in range(61,n):
        j=np.arange(max(1,i-200),i)
        used=j[prior_sign.iloc[j].to_numpy()==np.sign(d.return1.iloc[i])]
        conditional[i]=target.iloc[used].mean() if len(used)>=15 else d.return7.iloc[i]
    d['conditional_mean']=conditional
    d['opening_return_2']=np.log(m[1::1440,3]/d.reference)
    d['opening_return_482']=np.log(m[481::1440,3]/d.reference)
    return d

def decision_arrays(d,policy):
    policy.validate();rule=policy.rule
    if rule=='long':v=np.ones(len(d))
    elif rule=='short':v=-np.ones(len(d))
    elif rule in ('momentum1','momentum3','momentum7'):v=d['return'+rule[-1]].to_numpy()
    elif rule in ('reversal1','reversal3'):v=-d['return'+rule[-1]].to_numpy()
    elif rule=='iv_rise_short':v=-d.iv_rise.to_numpy()
    elif rule=='iv_regime':v=np.where(d.iv_rise>0,d.return3,-d.return1)
    elif rule=='conditional_mean':v=d.conditional_mean.to_numpy()
    elif rule=='opening_momentum':v=d[f'opening_return_{policy.entry_minute}'].to_numpy()
    elif rule=='opening_reversal':v=-d[f'opening_return_{policy.entry_minute}'].to_numpy()
    else:raise ValueError('conditional walls require minute path')
    side=np.where(v>=0,1,-1).astype(np.int8)
    sigma=d.sigma_mean5.to_numpy() if policy.wall_model=='mean5_iv' else d.sigma.to_numpy()
    u=sigma.copy();l=sigma.copy()
    if policy.wall_model=='history_mean':u=u*d.history_up_mean;l=l*d.history_down_mean
    u=np.asarray(u);l=np.asarray(l)
    ref=d.reference.to_numpy();sl=np.where(side>0,ref*np.exp(-policy.stop_multiple*l),ref*np.exp(policy.stop_multiple*u))
    tp=np.where(side>0,ref*np.exp(policy.target_multiple*u),ref*np.exp(-policy.target_multiple*l))
    valid=np.isfinite(np.asarray(v)+ref+u+l+d.iv_available_ms.to_numpy()) & (u>0)&(l>0)
    side[~valid]=0
    return side,np.asarray(sl),np.asarray(tp),np.full(len(d),policy.entry_minute,dtype=np.int64)

@njit(cache=True)
def evaluate(m,missing,side,stop,target,entries,start_day,end_day,risk,cap,fee,slip,step,tick,minnot,
             initial=10000.,record=True,participation=.01,entry_delay=0):
    """One entry attempt per day; flat at 23:59 UTC, no pyramids/reentries/carry.
    Trade triggers use actual OHLC; marks support approximate collateral/drawdown.
    The intrabar drawdown is a conservative bound, not tick-order precision.
    """
    n=end_day-start_day;ledger=np.zeros((n,len(LEDGER)));daily=np.empty(n+1);daily[0]=initial
    cash=initial;peak=initial;maxdd=0.;count=0;skips=np.zeros(n,np.int64)
    for d in range(start_day,end_day):
        k=d-start_day;ei=d*1440+entries[d]+entry_delay;last=d*1440+1439;s=int(side[d]);before=cash
        if entries[d]<0:skips[k]=5;daily[k+1]=cash;continue
        if s==0:skips[k]=1;daily[k+1]=cash;continue
        if cash<=0:skips[k]=4;daily[k+1]=cash;continue
        op=m[ei,0];sl=stop[d];tp=target[d]
        entry=op*(1+s*slip);entry=np.ceil(entry/tick)*tick if s==1 else np.floor(entry/tick)*tick
        if s*(entry-sl)<=0 or s*(tp-entry)<=0:skips[k]=2;daily[k+1]=cash;continue
        lossper=s*(entry-sl)+entry*fee+sl*fee+sl*slip+tick
        q=min(cash*risk/lossper,cash*cap/entry,m[ei-1,4]*participation)
        q=np.floor(q/step)*step
        if q<=0 or q*entry<minnot:skips[k]=3;daily[k+1]=cash;continue
        ef=q*entry*fee;cash-=ef;funding=0.;daylow=cash;gap=0;ex=entry;xf=0.;reason=3;xi=last
        for i in range(ei,last+1):
            fund=s*q*m[i,5]*m[i,9]
            if i==ei:fund=max(0.,fund)
            funding+=fund;cash-=fund
            gap=max(gap,int(missing[i]));equityopen=cash+s*q*(m[i,5]-entry)
            peak=max(peak,equityopen);maxdd=max(maxdd,1-equityopen/max(peak,1e-12));daylow=min(daylow,equityopen)
            op=m[i,0];lo=m[i,2];hi=m[i,1];closed=False;atopen=False
            if s*(op-sl)<=0:ex=op;reason=1;closed=True;atopen=True
            elif s*(op-tp)>=0:ex=op;reason=2;closed=True;atopen=True
            elif i==last:ex=op;reason=3;closed=True;atopen=True
            else:
                worst=m[i,7] if s==1 else m[i,6]
                bad=cash+s*q*(worst-entry);daylow=min(daylow,bad)
                maxdd=max(maxdd,1-bad/max(peak,1e-12))
                if bad<=abs(q*worst)*.01:
                    ex=worst;reason=4;closed=True
                elif (s==1 and lo<=sl) or (s==-1 and hi>=sl):ex=sl;reason=1;closed=True
                elif (s==1 and hi>=tp) or (s==-1 and lo<=tp):ex=tp;reason=2;closed=True
            if closed:
                ex*=1-s*slip;ex=np.floor(ex/tick)*tick if s==1 else np.ceil(ex/tick)*tick
                xf=abs(q*ex)*(.01 if reason==4 else fee);gross=s*q*(ex-entry);cash+=gross-xf;xi=i
                daylow=min(daylow,cash);peak=max(peak,cash);maxdd=max(maxdd,1-cash/max(peak,1e-12));break
            favorable=cash+s*q*((m[i,6] if s==1 else m[i,7])-entry)
            peak=max(peak,favorable)
            equityclose=cash+s*q*(m[i,8]-entry)
            maxdd=max(maxdd,1-equityclose/max(peak,1e-12))
        net=cash-before
        ledger[count,:]=np.array([d,ei,xi,s,q,entry,ex,sl,tp,ef,xf,funding,s*q*(ex-entry),net,before,cash,q*entry/before,reason,daylow,gap,0.])
        count+=1;daily[k+1]=cash
    return daily,ledger[:count],skips,maxdd

def run_policy(m,missing,d,policy,start_day,end_day,fee_bps=5.,slippage_bps=2.,initial=10000.,entry_delay=0):
    args=wall_decisions(d,m,policy) if policy.rule.startswith('wall_') else decision_arrays(d,policy);grid=d.attrs['grid']
    return evaluate(m,missing,*args,start_day,end_day,policy.risk_fraction,policy.exposure_cap,
      fee_bps/1e4,slippage_bps/1e4,*grid,initial,True,.01,entry_delay)

@njit(cache=True)
def _wall_trigger(bars,ref,up,down,trigger,stop_mult,target_mult,rejection):
    n=len(ref);side=np.zeros(n,np.int8);st=np.full(n,np.nan);tp=np.full(n,np.nan);entries=np.full(n,-1,np.int64)
    for d in range(n):
        if not np.isfinite(up[d]+down[d]+ref[d]) or min(up[d],down[d],ref[d])<=0:continue
        hiwall=ref[d]*np.exp(trigger*up[d]);lowall=ref[d]*np.exp(-trigger*down[d])
        for j in range(276):
            op,hi,lo,cl=bars[d,j]
            s=0
            if rejection:
                buy=lo<=lowall and cl>lowall and cl>op and cl<ref[d]
                sell=hi>=hiwall and cl<hiwall and cl<op and cl>ref[d]
                if buy and not sell:s=1
                elif sell and not buy:s=-1
            else:
                if cl>hiwall and cl>op:s=1
                elif cl<lowall and cl<op:s=-1
            if s:
                side[d]=s;entries[d]=(j+1)*5
                st[d]=ref[d]*np.exp(-stop_mult*down[d]) if s==1 else ref[d]*np.exp(stop_mult*up[d])
                tp[d]=ref[d]*np.exp(target_mult*up[d]) if s==1 else ref[d]*np.exp(-target_mult*down[d])
                break
    return side,st,tp,entries

def wall_decisions(d,m,policy):
    policy.validate();ref=d.reference.to_numpy()
    sigma=d.sigma_mean5.to_numpy() if policy.wall_model=='mean5_iv' else d.sigma.to_numpy()
    up=sigma.copy();down=sigma.copy()
    if policy.wall_model=='history_mean':up=up*d.history_up_mean.to_numpy();down=down*d.history_down_mean.to_numpy()
    bars=d.attrs.get('bars5')
    if bars is None:
        n=len(d);bars=np.stack([m[::5,0],m[:,1].reshape(-1,5).max(axis=1),m[:,2].reshape(-1,5).min(axis=1),m[4::5,3]],axis=1).reshape(n,288,4)
        d.attrs['bars5']=bars
    return _wall_trigger(bars,ref,up,down,policy.trigger_multiple,policy.stop_multiple,policy.target_multiple,policy.rule=='wall_rejection')

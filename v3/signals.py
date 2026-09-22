"""Outcome-independent, prefix-invariant hypotheses on completed market bars.
No centered windows or future rates; funding signals use earlier settlements.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

def aggregate(raw,tf):
    n=len(raw['close']); idx=pd.to_datetime(raw['timestamp'],unit='ms',utc=True)
    df=pd.DataFrame({k:raw[k] for k in ['open','high','low','close','volume','quote_volume','taker_buy_volume','mark_close','funding_rate']},index=idx)
    if tf==1: return df, np.arange(n,dtype=int)
    agg=df.resample(f'{tf}min',closed='left',label='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum','quote_volume':'sum','taker_buy_volume':'sum','mark_close':'last','funding_rate':'sum'})
    counts=df.close.resample(f'{tf}min').count();agg=agg.loc[counts==tf]
    ends=np.searchsorted(raw['timestamp'],(agg.index.as_unit('ms').asi8+tf*60_000))-1
    return agg,ends

def hypotheses(raw):
    n=len(raw['close'])
    for tf in [1,5,15,60]:
        d,ends=aggregate(raw,tf);c=d.close;hi=d.high;lo=d.low
        tr=pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
        atr=tr.ewm(span=32,min_periods=32,adjust=False).mean()
        af=(atr/c).clip(lower=.0015,upper=.15)
        volratio=d.volume/d.volume.rolling(64,min_periods=64).median().replace(0,np.nan)
        candleloc=(c-lo)/(hi-lo).replace(0,np.nan)
        sd=c.pct_change().rolling(96,min_periods=96).std()
        premium=(c-d.mark_close)/d.mark_close
        def pack(family,params,small,stopmult=2.,holdbars=24):
            small=np.nan_to_num(np.asarray(small),nan=0.).astype(np.int8)
            sig=np.zeros(n,dtype=np.int8);sig[ends]=small
            stop=np.full(n,np.nan);stop[ends]=(af*stopmult).clip(upper=.8).to_numpy()
            key=family+f'|tf={tf}|'+','.join(f'{k}={v}' for k,v in params.items())
            spec={'id':key,'family':family,'tf_minutes':tf,'params':params,'stop_atr':stopmult,'max_hold_seconds':max(300,int(tf*holdbars*60))}
            return spec,sig,stop
        for window in [16,64,192]:
            fast=c.ewm(span=max(3,window//4),min_periods=window,adjust=False).mean()
            slow=c.ewm(span=window,min_periods=window,adjust=False).mean()
            score=(fast-slow)/atr
            for thresh in [.5,1.5]:
                s=np.where(score>thresh,1,np.where(score< -thresh,-1,0))
                yield pack('trend',{'window':window,'threshold':thresh},s,2.5,max(24,window))
            z=(c-c.rolling(window,min_periods=window).mean())/c.rolling(window,min_periods=window).std()
            for thresh in [1.5,2.5]:
                s=np.where((z< -thresh)&(candleloc>.4),1,np.where((z>thresh)&(candleloc<.6),-1,0))
                yield pack('mean_reversion',{'window':window,'z':thresh},s,2.,window)
            upper=hi.rolling(window,min_periods=window).max().shift(1); lower=lo.rolling(window,min_periods=window).min().shift(1)
            for volume_filter in [1.,2.]:
                s=np.where((c>upper)&(volratio>volume_filter),1,np.where((c<lower)&(volratio>volume_filter),-1,0))
                yield pack('breakout',{'window':window,'volume':volume_filter},s,2.5,window)
            for reject in [.55,.75]:
                s=np.where((lo<lower)&(c>lower)&(candleloc>reject),1,np.where((hi>upper)&(c<upper)&(candleloc<1-reject),-1,0))
                yield pack('sweep',{'window':window,'rejection':reject},s,2.,window)
        for window in [1,4,16]:
            fl=(2*d.taker_buy_volume.rolling(window).sum()-d.volume.rolling(window).sum())/d.volume.rolling(window).sum()
            momentum=c.pct_change(window)
            for threshold in [.15,.35]:
                s=np.where((fl>threshold)&(momentum>0)&(volratio>1),1,np.where((fl< -threshold)&(momentum<0)&(volratio>1),-1,0))
                yield pack('flow_momentum',{'window':window,'imbalance':threshold},s,2.,max(12,window*4))
                s=np.where((fl< -threshold)&(candleloc>.65)&(volratio>1.5),1,np.where((fl>threshold)&(candleloc<.35)&(volratio>1.5),-1,0))
                yield pack('flow_absorption',{'window':window,'imbalance':threshold},s,1.5,max(12,window*4))
        for threshold in [.0002,.0005,.001,.002]:
            for usefilter in [False,True]:
                filt=volratio>1.5 if usefilter else np.ones(len(c),dtype=bool)
                s=np.where((premium< -threshold)&filt,1,np.where((premium>threshold)&filt,-1,0))
                yield pack('mark_dislocation',{'premium':threshold,'volume_filter':usefilter},s,1.5,12)
        for window in [1,4,16]:
            move=c.pct_change(window)/(sd*np.sqrt(window))
            for threshold in [2.,3.5]:
                s=np.where((move< -threshold)&(volratio>2)&(candleloc>.65),1,np.where((move>threshold)&(volratio>2)&(candleloc<.35),-1,0))
                yield pack('shock_reversal',{'window':window,'sigma':threshold},s,2.,max(12,window*4))
                s=np.where((move>threshold)&(volratio>2)&(candleloc>.8),1,np.where((move< -threshold)&(volratio>2)&(candleloc<.2),-1,0))
                yield pack('shock_continuation',{'window':window,'sigma':threshold},s,2.5,max(12,window*4))
        last=d.funding_rate.replace(0,np.nan).ffill().shift(1)
        for threshold in [.00005,.0001,.0003]:
            for filtered in [False,True]:
                trend=c/c.ewm(span=64,min_periods=64,adjust=False).mean()-1
                longs=(last< -threshold)&((trend>0) if filtered else True)
                shorts=(last>threshold)&((trend<0) if filtered else True)
                s=np.where(longs,1,np.where(shorts,-1,0))
                yield pack('lagged_funding',{'threshold':threshold,'trend_filter':filtered},s,3.,max(24,480//tf))

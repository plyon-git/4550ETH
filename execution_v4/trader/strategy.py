"""Shared causal closed-bar signals. No future shifts or backdated pivots."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json
import numpy as np
import pandas as pd
@dataclass(frozen=True)
class StrategySpec:
    family: str = 'breakout'
    timeframe_minutes: int = 15
    lookback: int = 192
    volume_multiple: float = 1.0
    trend_span: int = 0
    direction: str = 'both'
    stop_atr: float = 2.5
    target_r: float = 4.0
    trail_r: float = 0.0
    max_hold_hours: int = 48
    minimum_price: float = 1000.0
    risk_fraction: float = .01
    exposure_cap: float = 3.0
    daily_loss: float = .04
    weekly_loss: float = .10
    cooldown_minutes: int = 5
    atr_span: int = 32
    atr_min: float = .0005
    atr_max: float = .10
    def validate(self):
        if self.family not in ('breakout','momentum','pullback','reversal','trend_state','counter_breakout','counter_trend_state','rsi2','ml_directional'): raise ValueError('unsupported family')
        if self.timeframe_minutes not in (5,15,30,60,240): raise ValueError('unsupported timeframe')
        if not 4 <= self.lookback <= 1000: raise ValueError('lookback out of range')
        if self.direction not in ('both','long','short'): raise ValueError('bad direction')
        for k,v in asdict(self).items():
            if isinstance(v,(int,float)) and not np.isfinite(v): raise ValueError(f'nonfinite {k}')
        if not 0 < self.risk_fraction <= .10: raise ValueError('risk_fraction must be in (0,.10]')
        if not 0 < self.exposure_cap <= 20: raise ValueError('account exposure cap must be <=20')
        if not 0 < self.daily_loss < self.weekly_loss < 1: raise ValueError('invalid loss limits')
        if self.stop_atr <= 0 or self.target_r <= 0 or self.max_hold_hours <= 0: raise ValueError('invalid exits')
        if self.trail_r < 0 or self.minimum_price < 0 or self.volume_multiple < 0: raise ValueError('invalid strategy')
        if self.atr_span < 2 or not 0<self.atr_min<self.atr_max<1: raise ValueError('invalid ATR')
        return self
    @property
    def identity(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:16]

def aggregate_minutes(raw: dict, minutes: int) -> pd.DataFrame:
    ts=np.asarray(raw['timestamp'],dtype=np.int64)
    if ts.ndim!=1 or len(ts)<2 or np.any(np.diff(ts)!=60_000): raise ValueError('minute input not continuous')
    f=pd.DataFrame({k:raw[k] for k in ['open','high','low','close','volume']},index=pd.to_datetime(ts,unit='ms',utc=True))
    g=f.resample(f'{minutes}min',label='left',closed='left',origin='epoch')
    out=g.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    out['count']=g.close.count()
    return out.loc[out['count']==minutes].drop(columns='count')

def closed_bar_features(bars: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    spec.validate()
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates: raise ValueError('unordered bars')
    c,h,l,v=(bars[k].astype(float) for k in ['close','high','low','volume'])
    if not np.isfinite(bars[['open','high','low','close','volume']]).all().all(): raise ValueError('nonfinite OHLCV')
    if (c<=0).any() or (v<0).any(): raise ValueError('invalid prices/volume')
    prev=c.shift(1)
    tr=pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr=(tr.ewm(span=spec.atr_span,adjust=False).mean()/c).clip(spec.atr_min,spec.atr_max)
    high=h.shift(1).rolling(spec.lookback,min_periods=spec.lookback).max()
    low=l.shift(1).rolling(spec.lookback,min_periods=spec.lookback).min()
    vm=v/v.rolling(64,min_periods=64).median().replace(0,np.nan)
    ema=c.ewm(span=max(2,spec.lookback),adjust=False).mean()
    slow=c.ewm(span=max(2,spec.trend_span or 200),adjust=False).mean()
    ret=c.pct_change();delta=c.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/7,adjust=False).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/7,adjust=False).mean()
    rsi=100-100/(1+gain/(loss+1e-12));z=(c-ema)/(tr.ewm(span=spec.atr_span,adjust=False).mean()+1e-12)
    if spec.family=='ml_directional':buy=pd.Series(False,index=c.index);sell=pd.Series(False,index=c.index)
    elif spec.family=='breakout':buy=(c>high);sell=(c<low)
    elif spec.family=='counter_breakout':buy=(c<low);sell=(c>high)
    elif spec.family=='counter_trend_state':buy=(c<ema)&(ema<slow)&(ema<ema.shift(4));sell=(c>ema)&(ema>slow)&(ema>ema.shift(4))
    elif spec.family=='rsi2':
        g2=delta.clip(lower=0).ewm(alpha=.5,adjust=False).mean();l2=(-delta.clip(upper=0)).ewm(alpha=.5,adjust=False).mean()
        r2=100-100/(1+g2/(l2+1e-12));buy=r2<5;sell=r2>95
    elif spec.family=='momentum':buy=(c>ema)&(prev<=ema.shift(1));sell=(c<ema)&(prev>=ema.shift(1))
    elif spec.family=='trend_state':buy=(c>ema)&(ema>slow)&(ema>ema.shift(4));sell=(c<ema)&(ema<slow)&(ema<ema.shift(4))
    elif spec.family=='pullback':buy=(c>slow)&(rsi<35)&(ret>0);sell=(c<slow)&(rsi>65)&(ret<0)
    else:buy=(z<-2)&(ret>0);sell=(z>2)&(ret<0)
    eligible=(vm>=spec.volume_multiple)&(c>=spec.minimum_price)
    if spec.trend_span and spec.family!='counter_trend_state':buy &= c>slow;sell &= c<slow
    if spec.direction=='long':sell=pd.Series(False,index=c.index)
    if spec.direction=='short':buy=pd.Series(False,index=c.index)
    warm=max(spec.lookback+1,64,spec.trend_span*3 if spec.trend_span else 0,spec.atr_span*5)
    eligible.iloc[:warm]=False
    signal=np.where(buy&eligible,1,np.where(sell&eligible,-1,0)).astype(np.int8)
    return pd.DataFrame({'signal':signal,'stop_fraction':atr*spec.stop_atr,'atr_fraction':atr,'volume_ratio':vm,'rsi7':rsi,'ema_distance_atr':z,'return_1':ret,'return_4':c.pct_change(4),'return_16':c.pct_change(16)},index=bars.index)

def minute_signals(raw:dict,spec:StrategySpec,bars:pd.DataFrame|None=None):
    bars=aggregate_minutes(raw,spec.timeframe_minutes) if bars is None else bars
    feat=closed_bar_features(bars,spec)
    close_minute=bars.index.asi8//1_000_000+(spec.timeframe_minutes-1)*60_000
    ix=np.searchsorted(raw['timestamp'],close_minute);valid=ix<len(raw['timestamp']);ix=ix[valid]
    s=np.zeros(len(raw['timestamp']),dtype=np.int8);st=np.zeros(len(s),dtype=float)
    s[ix]=feat.signal.to_numpy()[valid];st[ix]=feat.stop_fraction.to_numpy()[valid]
    return s,st,feat

"""Forward-only empirical high/low surface inspired by the supplied QQQWave view.
Not the vendor's formula. Every sample's complete forecast horizon must mature.
Copyright 2026 Parrish Lyon; third-party rights remain with their owners.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class SurfaceSpec:
    lookback: int = 200
    horizon: int = 5
    matching: str = 'weekday'
    scale: str = 'realized'
    min_samples: int = 20
    def validate(self):
        if not 40 <= self.lookback <= 2000 or not 1 <= self.horizon <= 30:
            raise ValueError('invalid lookback/horizon')
        if self.matching not in ('all', 'weekday') or self.scale not in ('percent','realized','iv_scaled'):
            raise ValueError('unknown matching or scaling method')
        if self.min_samples < 10: raise ValueError('minimum sample count too small')
        return self
    @property
    def id(self): return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:12]

def build_surface(daily: pd.DataFrame, spec=SurfaceSpec()):
    """Input is a complete daily/session series, indexed by forecast origin UTC.

    At origin t: reference = close[t-1]. Samples start at j in [t-200,t-H],
    so their H-session outcomes are already known. Normalization is by RV20
    available at historical j. Current IV is only a scale in iv_scaled mode.
    Forward labels are computed for evaluation but never used as current input.
    """
    spec.validate()
    if daily.index.tz is None or not daily.index.is_monotonic_increasing or daily.index.has_duplicates:
        raise ValueError('timezone-aware ordered unique session index required')
    required=['open','high','low','close']
    if not np.isfinite(daily[required]).all().all() or (daily[required]<=0).any().any():
        raise ValueError('invalid daily prices')
    if len(daily)<spec.lookback+1:raise ValueError('insufficient input history')
    if (daily.high<daily[['open','close','low']].max(axis=1)).any() or (daily.low>daily[['open','close','high']].min(axis=1)).any():
        raise ValueError('invalid OHLC envelope')
    n=len(daily);h=spec.horizon
    c=daily.close.to_numpy(float);ref=np.r_[np.nan,c[:-1]]
    rv=np.asarray(np.log(daily.close).diff().rolling(20,min_periods=20).std().shift(1))
    hist_scale=np.ones(n) if spec.scale=='percent' else rv*np.sqrt(h)
    now_scale=hist_scale.copy()
    if spec.scale=='iv_scaled':
        if 'iv_daily_sigma' not in daily: raise ValueError('actual IV source required; no fallback')
        now_scale=daily.iv_daily_sigma.to_numpy(float)*np.sqrt(h)
    hi=np.full(n,np.nan);lo=np.full(n,np.nan);cl=np.full(n,np.nan)
    from numpy.lib.stride_tricks import sliding_window_view
    hi[:n-h+1]=np.log(sliding_window_view(daily.high.to_numpy(),h).max(axis=1)/ref[:n-h+1])
    lo[:n-h+1]=np.log(sliding_window_view(daily.low.to_numpy(),h).min(axis=1)/ref[:n-h+1])
    cl[:n-h+1]=np.log(c[h-1:]/ref[:n-h+1])
    weekday=daily.index.dayofweek.to_numpy();rows=[]
    for t in range(n):
        row={'origin_utc':daily.index[t], 'reference_price':ref[t], 'horizon_sessions':h,
             'sample_count':0,'rv_daily_sigma':rv[t], 'projection_sigma':now_scale[t],
             'latest_sample_origin_utc':None,'latest_matured_session_utc':None}
        if t < spec.lookback or not np.isfinite(now_scale[t]) or now_scale[t]<=0:
            rows.append(row);continue
        js=np.arange(t-spec.lookback,t-h+1)
        ok=(js>0)&np.isfinite(hist_scale[js])&(hist_scale[js]>0)&np.isfinite(hi[js]+lo[js]+cl[js])
        if spec.matching=='weekday':ok &= weekday[js]==weekday[t]
        js=js[ok]
        if len(js)<spec.min_samples: rows.append(row);continue
        assert (js+h<=t).all()
        upper=hi[js]/hist_scale[js]*now_scale[t]
        lower=lo[js]/hist_scale[js]*now_scale[t]
        terminal=cl[js]/hist_scale[js]*now_scale[t]
        row.update(sample_count=len(js),latest_sample_origin_utc=daily.index[js[-1]],
                   latest_matured_session_utc=daily.index[js[-1]+h-1])
        qs=(.05,.10,.25,.50,.75,.90,.95,.9736842105263158,.02631578947368418)
        lqs=np.quantile(lower,qs);uqs=np.quantile(upper,qs)
        for q,lq,uq in zip(qs,lqs,uqs):
            tag=f'{q:.6f}'
            row['low_q'+tag]=ref[t]*np.exp(lq)
            row['high_q'+tag]=ref[t]*np.exp(uq)
        row.update(mean_low_proxy=ref[t]*np.exp(lower).mean(),mean_high_proxy=ref[t]*np.exp(upper).mean(),
                   terminal_median=ref[t]*np.exp(np.median(terminal)),historical_terminal_up_rate=float((terminal>0).mean()),
                   train_mean_low_hit=float((lower<=np.log(np.exp(lower).mean())).mean()),
                   train_mean_high_hit=float((upper>=np.log(np.exp(upper).mean())).mean()))
        row['training_near_low_hit']=float((lower<=lqs[-2]).mean())
        row['training_near_high_hit']=float((upper>=uqs[-1]).mean())
        rows.append(row)
    out=pd.DataFrame(rows).set_index('origin_utc')
    for q in (.05,.10,.25,.50,.75,.90,.95,.9736842105263158,.02631578947368418):
        for name in ('low_q','high_q'):
            if name+f'{q:.6f}' not in out:out[name+f'{q:.6f}']=np.nan
    for name in ('mean_low_proxy','mean_high_proxy','terminal_median','historical_terminal_up_rate','train_mean_low_hit','train_mean_high_hit','training_near_low_hit','training_near_high_hit'):
        if name not in out:out[name]=np.nan
    return out

def event_evidence(daily,surface,start,end):
    """Separate terminal, horizon-touch and late-stop events. No trade-WR claim."""
    h=int(surface.horizon_sessions.iloc[0]);out=[]
    for i in np.flatnonzero((surface.index>=start)&(surface.index<end)&(surface.sample_count>0)):
        if i+h>len(daily):continue
        future=daily.iloc[i:i+h]
        if future.index[-1]>=end:continue
        row={'origin_utc':surface.index[i], 'sample_count':int(surface.sample_count.iloc[i]),
             'last_outcome_session_utc':future.index[-1], 'reference_price':surface.reference_price.iloc[i]}
        for key,col,direction in [('mean_low','mean_low_proxy',-1),('near97_low','low_q0.973684',-1),('mean_high','mean_high_proxy',1),('near97_high','high_q0.026316',1)]:
            level=float(surface[col].iloc[i]);value=float(future.low.min() if direction<0 else future.high.max())
            row[key+'_level']=level;row[key+'_touch']=bool(value<=level if direction<0 else value>=level)
            row[key+'_terminal']=bool(float(future.close.iloc[-1])<=level if direction<0 else float(future.close.iloc[-1])>=level)
            row[key+'_already_beyond_at_origin_open']=bool(float(future.open.iloc[0])<=level if direction<0 else float(future.open.iloc[0])>=level)
            row[key+'_distance_pct']=direction*(level/float(future.open.iloc[0])-1)*100
        level=surface.reference_price.iloc[i]*(715.69/721.45001)
        row['screenshot_offset_low_touch']=bool(future.low.min()<=level)
        out.append(row)
    return pd.DataFrame(out)

def event_summary(records):
    output={'forecast_origins':len(records),'overlapping_horizons':True,'not_trade_win_rate':True}
    for key in ('mean_low','near97_low','mean_high','near97_high'):
        good=~records[key+'_already_beyond_at_origin_open']
        output[key]={'all_origin_touch_rate':float(records[key+'_touch'].mean()),
                     'terminal_rate':float(records[key+'_terminal'].mean()),
                     'already_beyond_at_origin_open':int((~good).sum()),
                     'valid_direction_origins':int(good.sum()),
                     'valid_direction_touch_rate':float(records.loc[good,key+'_touch'].mean()) if good.any() else None,
                     'median_valid_distance_percent':float(records.loc[good,key+'_distance_pct'].median()) if good.any() else None}
    output['constant_screenshot_offset_touch_rate']=float(records.screenshot_offset_low_touch.mean())
    sub=records.iloc[::5]
    output['every_fifth_origin_count']=len(sub)
    output['every_fifth_origin_near97_low_touch_rate']=float(sub.near97_low_touch.mean())
    return output

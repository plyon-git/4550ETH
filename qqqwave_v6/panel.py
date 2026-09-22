"""Export a frozen empirical price/odds panel from daily OHLC inputs.
This is a research snapshot, not a trading command or the vendor's formula.
"""
from pathlib import Path
from dataclasses import asdict
import argparse,json
import numpy as np,pandas as pd
from source.surface import SurfaceSpec,build_surface

def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def snapshot(daily,spec,origin=None):
    levels=build_surface(daily,spec)
    at=levels.index[-1] if origin is None else pd.Timestamp(origin)
    if at.tzinfo is None or at not in levels.index:raise ValueError('origin must exactly match a timezone-aware input session')
    t=int(levels.index.get_loc(at));row=levels.iloc[t]
    if row.sample_count<spec.min_samples:raise ValueError('no eligible, fully matured history for this origin')
    h=spec.horizon;js=np.arange(t-spec.lookback,t-h+1)
    ref=daily.close.shift(1).to_numpy(float)
    rv=np.log(daily.close).diff().rolling(20,min_periods=20).std().shift(1).to_numpy()
    scale=np.ones(len(daily)) if spec.scale=='percent' else rv*np.sqrt(h)
    good=(js>0)&np.isfinite(scale[js])&(scale[js]>0)
    if spec.matching=='weekday':good &= daily.index.dayofweek.to_numpy()[js]==at.dayofweek
    js=js[good];trials=[]
    for j in js:
        assert j+h<=t
        historical=daily.iloc[j:j+h]
        factor=float(row.projection_sigma)/scale[j]
        def project(value):return float(row.reference_price*np.exp(np.log(value/ref[j])*factor))
        trials.append({'historical_origin_utc':str(daily.index[j]),'last_matured_session_utc':str(daily.index[j+h-1]),
                       'projected_low':project(historical.low.min()),'projected_high':project(historical.high.max()),
                       'projected_terminal':project(historical.close.iloc[-1])})
    trials=pd.DataFrame(trials)
    if len(trials)!=int(row.sample_count):raise AssertionError('panel sample count differs from forecast engine')
    np.testing.assert_allclose(trials.projected_low.mean(),row.mean_low_proxy,rtol=1e-12)
    np.testing.assert_allclose(trials.projected_high.mean(),row.mean_high_proxy,rtol=1e-12)
    prices=np.linspace(min(trials.projected_low.min(),row.reference_price),max(trials.projected_high.max(),row.reference_price),101)
    table=[]
    for price in prices:
        low=int((trials.projected_low<=price).sum());high=int((trials.projected_high>=price).sum())
        table.append({'price':float(price),'low_at_or_below_count':low,'high_at_or_above_count':high,
                      'sample_count':len(trials),'low_touch_empirical_frequency':low/len(trials),
                      'high_touch_empirical_frequency':high/len(trials)})
    metadata={'origin_utc':str(at),'spec':asdict(spec),'reference_price':float(row.reference_price),
              'sample_count':len(trials),'mean_low_proxy_not_vendor_MinAvg':float(row.mean_low_proxy),
              'mean_high_proxy':float(row.mean_high_proxy),'near_97_37_low_quantile':float(row['low_q0.973684']),
              'latest_matured_session_utc':str(row.latest_matured_session_utc),
              'no_orders':True,'probability_kind':'empirical in-window horizon-excursion frequency, not trade win rate or calibrated future probability',
              'vendor_rank_adjustment_applied':False,'proprietary_replication':False}
    return metadata,pd.DataFrame(table),trials

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--daily-input',type=Path,required=True)
    p.add_argument('--origin');p.add_argument('--lookback',type=int,default=200);p.add_argument('--horizon',type=int,default=5)
    p.add_argument('--matching',choices=['all','weekday'],default='weekday');p.add_argument('--scale',choices=['percent','realized','iv_scaled'],default='realized')
    p.add_argument('--out',type=Path,default=Path('snapshot'));args=p.parse_args()
    daily=pd.read_csv(args.daily_input,index_col=0);daily.index=pd.to_datetime(daily.index,utc=True)
    spec=SurfaceSpec(args.lookback,args.horizon,args.matching,args.scale)
    doc,table,trials=snapshot(daily,spec,args.origin);args.out.mkdir(parents=True,exist_ok=True)
    dump(args.out/'PANEL.json',doc);table.to_csv(args.out/'price_odds.csv',index=False);trials.to_csv(args.out/'matured_samples.csv',index=False)
    print(json.dumps(doc,indent=2,allow_nan=False))
if __name__=='__main__':main()

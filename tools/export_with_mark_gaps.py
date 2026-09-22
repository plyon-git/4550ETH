"""Export observed history with explicit null mark prices and independent 15m bounds.
This is not a fully observed mark-price dataset. No missing price is invented.
"""
from pathlib import Path
import concurrent.futures,hashlib,io,json,shutil,sys,urllib.request,zipfile
import numpy as np
import pandas as pd
import acquire_history as h
from acquire_with_repairs import repaired_read

def bounds_for_day(day):
    url=f'https://data.binance.vision/data/futures/um/daily/markPriceKlines/ETHUSDT/15m/ETHUSDT-15m-{day}.zip'
    record={'day':day,'url':url}
    try:
        with urllib.request.urlopen(url,timeout=30) as f:payload=f.read(4000001)
        with urllib.request.urlopen(url+'.CHECKSUM',timeout=30) as f:receipt=f.read(4096).decode()
        digest=hashlib.sha256(payload).hexdigest()
        if len(payload)>4000000 or digest!=receipt.split()[0].lower():raise ValueError('Bounds archive checksum/size failure')
        path=h.CACHE/f'bounds15m_{day}.zip';path.write_bytes(payload)
        frame=h.read_archive({'path':str(path)},'klines')
        record.update(success=True,sha256=digest,checksum=receipt.strip(),rows=len(frame))
        return record,frame
    except Exception as exc:
        record.update(success=False,error=repr(exc));return record,None

def main():
    months=[x.strftime('%Y-%m') for x in pd.date_range(h.START,h.END,freq='MS',inclusive='left')]
    requests=[(kind,month) for month in months for kind in ['klines','markPriceKlines','fundingRate']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:receipts=list(pool.map(lambda pair:h.retrieve(*pair),requests))
    (h.OUT/'archive_provenance.json').write_text(json.dumps(receipts,indent=2))
    if not all(r['success'] for r in receipts):raise ValueError('Missing source archives')
    frames={kind:pd.concat([repaired_read(r,kind) for r in receipts if r['kind']==kind],ignore_index=True).sort_values('timestamp') for kind in ['klines','markPriceKlines','fundingRate']}
    lo=int(pd.Timestamp(h.START,tz='UTC').timestamp()*1000);hi=int(pd.Timestamp(h.END,tz='UTC').timestamp()*1000)
    trade=frames['klines'];trade=trade[(trade.timestamp>=lo)&(trade.timestamp<hi)].reset_index(drop=True)
    mark=frames['markPriceKlines'];mark=mark[(mark.timestamp>=lo)&(mark.timestamp<hi)].reset_index(drop=True)
    fund=frames['fundingRate'];fund=fund[(fund.timestamp>=lo)&(fund.timestamp<hi)].reset_index(drop=True)
    t=trade.timestamp.to_numpy(dtype=np.int64);expected=np.arange(lo,hi,60000,dtype=np.int64)
    if not np.array_equal(t,expected) or mark.timestamp.duplicated().any():raise ValueError('Trade gaps or duplicate mark data')
    for name,frame in [('trade',trade),('observed_mark',mark)]:
        bad=(frame.low<=0)|(frame.high<frame[['open','close']].max(axis=1))|(frame.low>frame[['open','close']].min(axis=1))
        if bad.any():raise ValueError(f'Invalid {name} OHLC')
    ft=fund.timestamp.to_numpy(dtype=np.int64);interval=fund.interval_hours.to_numpy(dtype=float);rounded=((ft+30000)//60000)*60000
    if not len(ft) or np.any(interval<=0) or np.any(np.abs(fund.rate)>1):raise ValueError('Invalid funding values')
    if np.any(np.abs(ft-rounded)>1000) or np.any(np.diff(rounded)<=0):raise ValueError('Funding timing/duplicate failure')
    differences=np.diff(rounded)/3600000
    if not np.all(np.isclose(differences,interval[:-1])|np.isclose(differences,interval[1:])):raise ValueError('Funding event gap')
    if rounded[0]-lo>interval[0]*3600000 or hi-rounded[-1]>interval[-1]*3600000:raise ValueError('Funding boundary gap')
    pos=np.searchsorted(t,rounded)
    if np.any(pos>=len(t)) or not np.array_equal(t[pos],rounded):raise ValueError('Funding outside price grid')
    rates=np.zeros(len(t));rates[pos]=fund.rate.to_numpy(dtype=float)
    aligned=mark.set_index('timestamp').reindex(t);observed=aligned.close.notna().to_numpy()
    missing=t[~observed];missing_days=sorted(set(pd.to_datetime(missing,unit='ms',utc=True).strftime('%Y-%m-%d')))
    bounds_results=[bounds_for_day(day) for day in missing_days]
    (h.OUT/'mark_15m_bounds_provenance.json').write_text(json.dumps([v[0] for v in bounds_results],indent=2))
    bound_frames=[v[1] for v in bounds_results if v[1] is not None]
    boundlo=np.full(len(t),np.nan);boundhi=np.full(len(t),np.nan)
    if bound_frames:
        bound=pd.concat(bound_frames,ignore_index=True).drop_duplicates('timestamp').set_index('timestamp')
        bound.reset_index().to_csv(h.OUT/'mark_15m_gap_bounds.csv',index=False)
        for i in np.flatnonzero(~observed):
            key=(int(t[i])//900000)*900000
            if key in bound.index:boundlo[i]=float(bound.loc[key,'low']);boundhi[i]=float(bound.loc[key,'high'])
    raw={c:trade[c].to_numpy(dtype=np.int64 if c in ['timestamp','trades'] else float) for c in ['timestamp','open','high','low','close','volume','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume']}
    raw.update({'mark_'+c:aligned[c].to_numpy(dtype=float) for c in ['open','high','low','close']})
    raw.update(funding_rate=rates,funding_verified=np.ones(len(t),dtype=bool),mark_observed=observed,missing_mark_15m_low=boundlo,missing_mark_15m_high=boundhi)
    np.savez_compressed(h.OUT/'aligned_extended_WITH_MARK_GAPS.npz',**raw)
    fund.to_csv(h.OUT/'funding_events.csv',index=False)
    pd.DataFrame({'timestamp':missing,'utc':pd.to_datetime(missing,unit='ms',utc=True)}).to_csv(h.OUT/'missing_mark_minutes.csv',index=False)
    first=int(np.flatnonzero(raw['close']>1000)[0])
    q={'status':'OBSERVED_DATA_WITH_EXPLICIT_MARK_GAPS','fully_observed_mark_history':bool(observed.all()),'trade_candles_complete':True,'funding_rate_events_complete':True,'requested_start':h.START,'end_exclusive':h.END,'trade_rows':len(t),'observed_mark_rows':int(observed.sum()),'missing_mark_minutes':int((~observed).sum()),'missing_mark_minutes_on_or_after_first_above_1000':int(np.sum((~observed)&(np.arange(len(t))>=first))),'missing_marks_with_15m_bounds':int(np.sum((~observed)&np.isfinite(boundlo)&np.isfinite(boundhi))),'first_close_above_1000_utc':str(pd.Timestamp(t[first],unit='ms',tz='UTC')),'first_above_index':first,'funding_events':len(fund),'funding_snap_max_milliseconds':int(np.max(np.abs(ft-rounded))),'null_policy':'Missing mark prices remain NaN in all four raw mark columns. Published 15m bounds are separate fields, not replacements.','numpy_version':np.__version__,'pandas_version':pd.__version__,'canonical_sha256':hashlib.sha256((h.OUT/'aligned_extended_WITH_MARK_GAPS.npz').read_bytes()).hexdigest()}
    # Probe the next month's daily funding source without assuming it exists.
    probe='https://data.binance.vision/data/futures/um/daily/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2026-09-20.zip'
    try:
        with urllib.request.urlopen(probe,timeout=15) as f:q['september_daily_funding_probe']={'url':probe,'http_status':f.status,'bytes_sampled':len(f.read(4096))}
    except Exception as exc:q['september_daily_funding_probe']={'url':probe,'error':repr(exc)}
    (h.OUT/'DATA_QUALITY.json').write_text(json.dumps(q,indent=2));print('DATA_QUALITY='+json.dumps(q,sort_keys=True),flush=True)
    for filename in ['acquire_history.py','acquire_with_repairs.py','export_with_mark_gaps.py']:shutil.copy2(Path(__file__).parent/filename,h.OUT/filename)
    if sum(p.stat().st_size for p in h.OUT.iterdir() if p.is_file())>300000000:raise ValueError('Artifact exceeds bounded size')
if __name__=='__main__':main()

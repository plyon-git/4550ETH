"""Read-only public ETHUSDT archive acquisition. Copyright 2026 Parrish Lyon.
Exchange data remain the exchange's data. No orders, keys or accounts are used.
"""
from __future__ import annotations
import concurrent.futures, hashlib, io, json, os, shutil, sys, time, urllib.request, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
BASE='https://data.binance.vision/data/futures/um/monthly/'
START='2020-01-01'
END='2026-09-01'
OUT=Path('history_output');CACHE=Path('archive_cache')
OUT.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True)
COLUMNS=['timestamp','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume','ignore']

def retrieve(kind,month):
    name=f'ETHUSDT-fundingRate-{month}.zip' if kind=='fundingRate' else f'ETHUSDT-1m-{month}.zip'
    rel=f'{kind}/ETHUSDT/{name}' if kind=='fundingRate' else f'{kind}/ETHUSDT/1m/{name}'
    url=BASE+rel;path=CACHE/(kind+'_'+name);result={'kind':kind,'month':month,'url':url,'checksum_url':url+'.CHECKSUM'}
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url,timeout=30) as response:payload=response.read(32000001)
            if len(payload)>32000000:raise ValueError('Archive exceeded bounded download size')
            with urllib.request.urlopen(url+'.CHECKSUM',timeout=30) as response:receipt=response.read(4096).decode()
            expected=receipt.split()[0].lower();actual=hashlib.sha256(payload).hexdigest()
            if len(expected)!=64 or actual!=expected:raise ValueError('Archive checksum mismatch')
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if len(archive.namelist())!=1:raise ValueError('Expected one CSV per archive')
                if archive.testzip() is not None:raise ValueError('Corrupt ZIP member')
            path.write_bytes(payload)
            result.update(success=True,bytes=len(payload),sha256=actual,checksum=receipt.strip(),path=str(path))
            return result
        except Exception as exc:
            result.update(success=False,error=repr(exc))
            if isinstance(exc,urllib.error.HTTPError) and exc.code in (400,401,403,404,451):break
            if attempt==0:time.sleep(1)
    return result

def read_archive(record,kind):
    with zipfile.ZipFile(record['path']) as z:
        with z.open(z.namelist()[0]) as f:payload=f.read()
    first=payload.split(b'\n',1)[0].split(b',',1)[0].strip()
    header=not first.isdigit()
    if kind=='fundingRate':
        names=['timestamp','interval_hours','rate']
    else:names=COLUMNS
    df=pd.read_csv(io.BytesIO(payload),header=0 if header else None,names=names)
    for c in df.columns:df[c]=pd.to_numeric(df[c],errors='raise')
    if not np.isfinite(df.to_numpy()).all():raise ValueError(f'Nonfinite input: {record["path"]}')
    return df

def main():
    months=[x.strftime('%Y-%m') for x in pd.date_range(START,END,freq='MS',inclusive='left')]
    requests=[(kind,month) for month in months for kind in ['klines','markPriceKlines','fundingRate']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        receipts=list(pool.map(lambda pair:retrieve(*pair),requests))
    (OUT/'archive_provenance.json').write_text(json.dumps(receipts,indent=2))
    failures=[r for r in receipts if not r['success']]
    print('ACQUISITION_COUNTS='+json.dumps({'requested':len(receipts),'verified':len(receipts)-len(failures),'failed':len(failures)}),flush=True)
    if failures:
        print('FAILED_ARCHIVES='+json.dumps(failures),flush=True)
        raise RuntimeError('Incomplete archives; canonical data will not be fabricated')
    allframes={}
    for kind in ['klines','markPriceKlines','fundingRate']:
        allframes[kind]=pd.concat([read_archive(r,kind) for r in receipts if r['kind']==kind],ignore_index=True)
    trade=allframes['klines'].sort_values('timestamp');mark=allframes['markPriceKlines'].sort_values('timestamp');fund=allframes['fundingRate'].sort_values('timestamp')
    lo=int(pd.Timestamp(START,tz='UTC').timestamp()*1000);hi=int(pd.Timestamp(END,tz='UTC').timestamp()*1000)
    trade=trade[(trade.timestamp>=lo)&(trade.timestamp<hi)].reset_index(drop=True)
    mark=mark[(mark.timestamp>=lo)&(mark.timestamp<hi)].reset_index(drop=True)
    fund=fund[(fund.timestamp>=lo)&(fund.timestamp<hi)].reset_index(drop=True)
    t=trade.timestamp.to_numpy(dtype=np.int64);mt=mark.timestamp.to_numpy(dtype=np.int64)
    expected=np.arange(lo,hi,60000,dtype=np.int64)
    quality={'requested_start':START,'end_exclusive':END,'trade_rows':len(t),'mark_rows':len(mt),'funding_events':len(fund),'expected_minutes':len(expected),'duplicate_trade_timestamps':int(pd.Series(t).duplicated().sum()),'duplicate_mark_timestamps':int(pd.Series(mt).duplicated().sum()),'missing_trade_minutes':int(len(np.setdiff1d(expected,t))),'missing_mark_minutes':int(len(np.setdiff1d(expected,mt))),'trade_mark_timestamps_equal':bool(np.array_equal(t,mt))}
    (OUT/'DATA_QUALITY.json').write_text(json.dumps(quality,indent=2))
    if not np.array_equal(t,expected) or not np.array_equal(mt,expected):
        pd.DataFrame({'missing_trade_timestamp':np.setdiff1d(expected,t)}).to_csv(OUT/'missing_trade_minutes.csv',index=False)
        pd.DataFrame({'missing_mark_timestamp':np.setdiff1d(expected,mt)}).to_csv(OUT/'missing_mark_minutes.csv',index=False)
        raise ValueError('Gapped or duplicate market data; no implicit forward filling')
    for label,frame in [('trade',trade),('mark',mark)]:
        invalid=(frame.low<=0)|(frame.high<frame[['open','close']].max(axis=1))|(frame.low>frame[['open','close']].min(axis=1))
        if invalid.any():raise ValueError(f'Invalid {label} OHLC')
    if (trade.volume<0).any():raise ValueError('Negative volume')
    ft=fund.timestamp.to_numpy(dtype=np.int64);interval=fund.interval_hours.to_numpy(dtype=float)
    rounded=((ft+30000)//60000)*60000
    if not len(ft) or np.any(interval<=0) or np.any(np.abs(fund.rate.to_numpy())>1):raise ValueError('Bad funding values')
    if np.any(np.abs(ft-rounded)>1000):raise ValueError('Funding event too far from minute boundary')
    if np.any(np.diff(rounded)<=0):raise ValueError('Duplicate/unordered funding events')
    gaps=np.diff(rounded)/3600000
    if not np.all(np.isclose(gaps,interval[1:])|np.isclose(gaps,interval[:-1])):raise ValueError('Funding interval coverage gap')
    if rounded[0]-lo>interval[0]*3600000 or hi-rounded[-1]>interval[-1]*3600000:raise ValueError('Funding boundary coverage gap')
    rate=np.zeros(len(t),dtype=float);loc=np.searchsorted(t,rounded)
    if np.any(loc>=len(t)) or not np.array_equal(t[loc],rounded):raise ValueError('Funding does not align to market grid')
    rate[loc]=fund.rate.to_numpy(dtype=float)
    raw={c:trade[c].to_numpy(dtype=np.int64 if c in ['timestamp','trades'] else float) for c in ['timestamp','open','high','low','close','volume','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume']}
    raw.update({'mark_'+c:mark[c].to_numpy(dtype=float) for c in ['open','high','low','close']})
    raw.update(funding_rate=rate,funding_verified=np.ones(len(t),dtype=bool))
    above=np.flatnonzero(raw['close']>1000)
    quality.update(ready=True,first_close_above_1000_utc=str(pd.Timestamp(t[above[0]],unit='ms',tz='UTC')) if len(above) else None,minimum_trade_low=float(raw['low'].min()),minutes_close_at_or_below_1000=int(np.sum(raw['close']<=1000)),funding_snap_max_milliseconds=int(np.max(np.abs(ft-rounded))),funding_timestamp_convention='Nearest minute, maximum permitted offset 1000ms; exact source timestamps preserved in funding_events.csv')
    np.savez_compressed(OUT/'aligned_extended.npz',**raw)
    fund.to_csv(OUT/'funding_events.csv',index=False)
    quality['canonical_sha256']=hashlib.sha256((OUT/'aligned_extended.npz').read_bytes()).hexdigest()
    quality.update(python_version=sys.version,numpy_version=np.__version__,pandas_version=pd.__version__,github_run_id=os.environ.get('GITHUB_RUN_ID'))
    (OUT/'DATA_QUALITY.json').write_text(json.dumps(quality,indent=2))
    shutil.copy2(__file__,OUT/'acquire_history.py')
    if sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())>300000000:raise ValueError('Artifact exceeds 300MB safety bound')
    print('DATA_QUALITY='+json.dumps(quality,sort_keys=True),flush=True)
if __name__=='__main__':main()

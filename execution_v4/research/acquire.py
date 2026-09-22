"""Read-only checksum-verifying public perpetual archive acquisition.
Project-specific code: Copyright 2026 Parrish Lyon. Data rights remain with venue.
"""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,io,json,time,urllib.request,urllib.error,zipfile
from pathlib import Path
import numpy as np,pandas as pd
COLS=['timestamp','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume','ignore']

def get(kind,symbol,date,cache,daily=False):
 freq='daily' if daily else 'monthly'
 name=f'{symbol}-fundingRate-{date}.zip' if kind=='fundingRate' else f'{symbol}-1m-{date}.zip'
 rel=f'{kind}/{symbol}/{name}' if kind=='fundingRate' else f'{kind}/{symbol}/1m/{name}'
 url='https://data.binance.vision/data/futures/um/'+freq+'/'+rel
 r={'kind':kind,'symbol':symbol,'date':date,'url':url,'checksum_url':url+'.CHECKSUM'}
 path=cache/(kind+'_'+name)
 for attempt in range(3):
  try:
   with urllib.request.urlopen(url,timeout=40) as f:b=f.read(40_000_001)
   with urllib.request.urlopen(url+'.CHECKSUM',timeout=20) as f:receipt=f.read(4096).decode()
   digest=hashlib.sha256(b).hexdigest()
   if len(b)>40_000_000 or digest!=receipt.split()[0].lower():raise ValueError('checksum or size mismatch')
   with zipfile.ZipFile(io.BytesIO(b)) as z:
    if len(z.infolist())!=1 or z.infolist()[0].file_size>100_000_000:raise ValueError('unexpected archive layout')
    if z.testzip():raise ValueError('corrupt ZIP')
   path.write_bytes(b);r.update(success=True,sha256=digest,bytes=len(b),checksum=receipt.strip(),path=str(path));return r
  except Exception as e:
   r.update(success=False,error=repr(e))
   if isinstance(e,urllib.error.HTTPError) and e.code in (400,401,403,404,451):break
   time.sleep(.5*(attempt+1))
 return r

def read(r):
 with zipfile.ZipFile(r['path']) as z:b=z.read(z.namelist()[0])
 header=not b.split(b',',1)[0].strip().isdigit()
 names=['timestamp','interval_hours','rate'] if r['kind']=='fundingRate' else COLS
 d=pd.read_csv(io.BytesIO(b),header=0 if header else None,names=names)
 for c in d:d[c]=pd.to_numeric(d[c],errors='raise')
 if not np.isfinite(d.to_numpy()).all():raise ValueError('nonfinite archive')
 return d

def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',choices=['ETHUSDT','BTCUSDT','XRPUSDT'],required=True);p.add_argument('--start',default='2020-01-01');p.add_argument('--end',default='2026-09-01');p.add_argument('--out',default='market_data');a=p.parse_args()
 root=Path(a.out)/a.symbol;root.mkdir(parents=True,exist_ok=True);cache=root/'cache';cache.mkdir(exist_ok=True)
 start=int(pd.Timestamp(a.start,tz='UTC').timestamp()*1000);end=int(pd.Timestamp(a.end,tz='UTC').timestamp()*1000)
 months=[x.strftime('%Y-%m') for x in pd.date_range(a.start,a.end,freq='MS',inclusive='left')]
 jobs=[(k,a.symbol,m,cache) for m in months for k in ['klines','markPriceKlines','fundingRate']]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(lambda t:get(*t),jobs))
 (root/'provenance.json').write_text(json.dumps(receipts,indent=2))
 if not all(r['success'] for r in receipts):raise RuntimeError('Incomplete required monthly archives; not a completed backtest')
 frames={k:pd.concat([read(r) for r in receipts if r['kind']==k],ignore_index=True).sort_values('timestamp') for k in ['klines','markPriceKlines','fundingRate']}
 expected=np.arange(start,end,60000,dtype=np.int64)
 repair=[]
 for k in ['klines','markPriceKlines']:
  f=frames[k];f=f[(f.timestamp>=start)&(f.timestamp<end)]
  if f.timestamp.duplicated().any():raise ValueError('duplicate timestamps')
  missing=np.setdiff1d(expected,f.timestamp.to_numpy(dtype=np.int64))
  for day in sorted(set(pd.to_datetime(missing,unit='ms',utc=True).strftime('%Y-%m-%d'))):
   r=get(k,a.symbol,day,cache,True);repair.append(r)
   if r['success']:
    d=read(r);d=d[d.timestamp.isin(missing)];f=pd.concat([f,d],ignore_index=True).sort_values('timestamp')
  if f.timestamp.duplicated().any():raise ValueError('duplicate repairs')
  bad=(f.low<=0)|(f.high<f[['open','close']].max(axis=1))|(f.low>f[['open','close']].min(axis=1))
  if bad.any():raise ValueError('invalid OHLC')
  frames[k]=f
 (root/'repair_provenance.json').write_text(json.dumps(repair,indent=2))
 trade=frames['klines'];mark=frames['markPriceKlines'];fund=frames['fundingRate'];fund=fund[(fund.timestamp>=start)&(fund.timestamp<end)]
 t=trade.timestamp.to_numpy(dtype=np.int64)
 if not np.array_equal(t,expected):raise ValueError('trade-minute gap remains')
 rounded=((fund.timestamp.to_numpy(dtype=np.int64)+30000)//60000)*60000;interval=fund.interval_hours.to_numpy(float)
 if not len(fund) or np.any(np.diff(rounded)<=0) or np.any(interval<=0):raise ValueError('invalid funding')
 offsets=np.abs(rounded-fund.timestamp.to_numpy(dtype=np.int64))
 if offsets.max()>1000 or not np.all(np.isclose(np.diff(rounded)/3600000,interval[:-1])|np.isclose(np.diff(rounded)/3600000,interval[1:])):raise ValueError('funding gaps or timing')
 if rounded[0]-start>interval[0]*3600000 or end-rounded[-1]>interval[-1]*3600000:raise ValueError('funding boundary coverage')
 if np.any(np.abs(fund.rate)>1):raise ValueError('invalid funding rate')
 ix=np.searchsorted(t,rounded)
 if np.any(ix>=len(t)) or not np.array_equal(t[ix],rounded):raise ValueError('funding timestamp mismatch')
 rates=np.zeros(len(t));rates[ix]=fund.rate.to_numpy(float)
 mark=mark.set_index('timestamp').reindex(t);observed=mark.close.notna().to_numpy()
 raw={k:trade[k].to_numpy(dtype=np.int64 if k in ['timestamp','trades'] else float) for k in ['timestamp','open','high','low','close','volume','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume']}
 raw.update({'mark_'+k:mark[k].to_numpy(float) for k in ['open','high','low','close']})
 raw.update(funding_rate=rates,funding_verified=np.ones(len(t),bool),mark_observed=observed,missing_mark_15m_low=np.full(len(t),np.nan),missing_mark_15m_high=np.full(len(t),np.nan))
 np.savez_compressed(root/'aligned.npz',**raw);fund.to_csv(root/'funding_events.csv',index=False)
 pd.DataFrame({'timestamp':t[~observed]}).to_csv(root/'missing_marks.csv',index=False)
 quality={'symbol':a.symbol,'start':a.start,'end_exclusive':a.end,'rows':len(t),'trade_minutes_complete':True,'missing_mark_minutes':int((~observed).sum()),'funding_events':len(fund),'funding_snap_max_ms':int(offsets.max()),'raw_marks_preserve_nulls':True,'sha256':hashlib.sha256((root/'aligned.npz').read_bytes()).hexdigest()}
 (root/'QUALITY.json').write_text(json.dumps(quality,indent=2));print(json.dumps(quality),flush=True)
if __name__=='__main__':main()

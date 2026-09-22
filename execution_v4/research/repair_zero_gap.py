"""Reconstruct a specifically observed zero-volume archive gap from actual aggTrades.
Never replace an observed nonzero-volume candle or invent a trade in an empty minute.
"""
from __future__ import annotations
import argparse,hashlib,json,urllib.request,zipfile
from pathlib import Path
import numpy as np,pandas as pd

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--symbol',required=True);p.add_argument('--out',default='repaired');a=p.parse_args();root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
 with np.load(a.input,allow_pickle=False) as z:raw={k:z[k] for k in z.files}
 gaps=np.flatnonzero((raw['volume']==0)&(raw['trades']==0));days=sorted(set(pd.to_datetime(raw['timestamp'][gaps],unit='ms',utc=True).strftime('%Y-%m-%d')))
 # Only the observed shared anomaly is in scope; other zero minutes are reported, not generalized into data rewrites.
 days=[d for d in days if d=='2024-10-28'];receipts=[];patches=[]
 for day in days:
  name=f'{a.symbol}-aggTrades-{day}.zip';url='https://data.binance.vision/data/futures/um/daily/aggTrades/'+a.symbol+'/'+name;dest=root/name
  with urllib.request.urlopen(url,timeout=60) as src,dest.open('wb') as out:
   total=0
   while b:=src.read(1024*1024):
    total+=len(b)
    if total>400_000_000:raise ValueError('archive exceeds safe compressed size bound')
    out.write(b)
  with urllib.request.urlopen(url+'.CHECKSUM',timeout=30) as f:receipt=f.read(4096).decode()
  if sha(dest)!=receipt.split()[0].lower():raise ValueError('trade archive SHA mismatch')
  receipts.append({'url':url,'checksum_url':url+'.CHECKSUM','sha256':sha(dest),'bytes':dest.stat().st_size,'receipt':receipt.strip()})
  chunks=[];columns=['id','price','quantity','first_id','last_id','time','maker']
  start=int(pd.Timestamp(day,tz='UTC').timestamp()*1000);end=start+86400000
  gap_ts=set(int(x) for x in raw['timestamp'][gaps] if start<=x<end)
  with zipfile.ZipFile(dest) as z:
   if len(z.infolist())!=1 or z.infolist()[0].file_size>3_000_000_000:raise ValueError('unexpected archive structure')
   with z.open(z.namelist()[0]) as f:line=f.readline()
   header=not line.split(b',')[0].isdigit()
   with z.open(z.namelist()[0]) as f:
    for chunk in pd.read_csv(f,header=0 if header else None,names=columns,chunksize=500000):
     chunk['minute']=(chunk.time//60000)*60000;part=chunk[chunk.minute.isin(gap_ts)]
     if len(part):chunks.append(part)
  if not chunks:raise ValueError('No observed trades support a repair; raw data must remain unmodified')
  records=pd.concat(chunks,ignore_index=True).sort_values(['time','id'])
  if records.id.duplicated().any():raise ValueError('duplicate aggTrade IDs')
  for minute,g in records.groupby('minute',sort=True):
   i=int(np.searchsorted(raw['timestamp'],minute))
   if raw['timestamp'][i]!=minute or raw['volume'][i]!=0 or raw['trades'][i]!=0:raise ValueError('attempt to alter non-gap record')
   price=g.price.to_numpy(float);qty=g.quantity.to_numpy(float)
   if not np.isfinite(price+qty).all() or (price<=0).any() or (qty<=0).any():raise ValueError('invalid observed trade')
   maker=g.maker.astype(str).str.lower().eq('true').to_numpy();buy=~maker
   patch={'timestamp':int(minute),'open':float(price[0]),'high':float(price.max()),'low':float(price.min()),'close':float(price[-1]),'volume':float(qty.sum()),'quote_volume':float((price*qty).sum()),'trades':int((g.last_id-g.first_id+1).sum()),'taker_buy_volume':float(qty[buy].sum()),'taker_buy_quote_volume':float((price[buy]*qty[buy]).sum())}
   patch['original_open']=float(raw['open'][i]);patch['original_close']=float(raw['close'][i]);patch['aggregate_records']=len(g)
   for k in ['open','high','low','close','volume','quote_volume','trades','taker_buy_volume','taker_buy_quote_volume']:raw[k][i]=patch[k]
   patches.append(patch)
  dest.unlink()  # Source identity is preserved; reproducible tape download need not inflate the derived artifact.
 if not patches:raise ValueError('no sourced gap repairs completed')
 np.savez_compressed(root/'aligned_repaired.npz',**raw);pd.DataFrame(patches).to_csv(root/'OBSERVED_TRADE_REPAIRS.csv',index=False)
 summary={'symbol':a.symbol,'original_input_sha256':sha(a.input),'repaired_sha256':sha(root/'aligned_repaired.npz'),'repaired_zero_minutes':len(patches),'repair_source':'actual checksum-matching exchange aggregate trades','source_receipts':receipts,'raw_mark_gaps_preserved':True,'no_unobserved_trades_invented':True}
 (root/'REPAIR_PROVENANCE.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':main()

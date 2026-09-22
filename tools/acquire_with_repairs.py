"""Repair monthly mark-archive omissions using checksum-verified daily archives only.
No prices are interpolated, carried forward, or substituted from trade candles.
"""
from pathlib import Path
import hashlib,io,json,urllib.request,zipfile
import numpy as np
import pandas as pd
import acquire_history as h
original=h.read_archive
repairs=[]

def repaired_read(record,kind):
    df=original(record,kind)
    if kind!='markPriceKlines':return df
    start=pd.Timestamp(record['month']+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
    expected=np.arange(int(start.timestamp()*1000),int(end.timestamp()*1000),60000,dtype=np.int64)
    missing=np.setdiff1d(expected,df.timestamp.to_numpy(dtype=np.int64))
    days=sorted(set(pd.to_datetime(missing,unit='ms',utc=True).strftime('%Y-%m-%d')))
    for day in days:
        url=f'https://data.binance.vision/data/futures/um/daily/markPriceKlines/ETHUSDT/1m/ETHUSDT-1m-{day}.zip'
        r={'day':day,'url':url,'initial_missing_in_month':int(len(missing))}
        try:
            with urllib.request.urlopen(url,timeout=30) as f:payload=f.read(4000001)
            with urllib.request.urlopen(url+'.CHECKSUM',timeout=30) as f:receipt=f.read(4096).decode()
            digest=hashlib.sha256(payload).hexdigest()
            if len(payload)>4000000 or digest!=receipt.split()[0].lower():raise ValueError('Daily archive identity/size failure')
            path=h.CACHE/f'daily_mark_{day}.zip';path.write_bytes(payload)
            daily=original({'path':str(path)},kind)
            overlap=df.merge(daily,on='timestamp',suffixes=('_monthly','_daily'))
            for col in h.COLUMNS[1:]:
                if not np.allclose(overlap[col+'_monthly'],overlap[col+'_daily'],rtol=1e-12,atol=1e-8):raise ValueError(f'Daily/monthly conflict: {col}')
            add=daily[daily.timestamp.isin(missing)]
            df=pd.concat([df,add],ignore_index=True).sort_values('timestamp')
            r.update(success=True,sha256=digest,checksum=receipt.strip(),inserted_observed_minutes=len(add),overlap_rows_compared=len(overlap))
        except Exception as exc:r.update(success=False,error=repr(exc))
        repairs.append(r)
        (h.OUT/'mark_repair_provenance.json').write_text(json.dumps(repairs,indent=2))
        print('MARK_ARCHIVE_REPAIR='+json.dumps(r),flush=True)
    return df
h.read_archive=repaired_read
if __name__=='__main__':h.main()

"""Acquire actual Deribit implied-volatility index history. Read-only, no keys."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen,Request
from datetime import datetime,timezone
import json,hashlib,time,csv
START=1609459200000
END=1788220800000

def get(url):
    with urlopen(Request(url,headers={'User-Agent':'Parrish-Lyon-research/1.0'}),timeout=45) as r:
        data=r.read(20_000_001)
        if len(data)>20_000_000:raise ValueError('response too large')
        return data

def main():
    root=Path('volatility_v5/iv_data');root.mkdir(parents=True,exist_ok=True);receipts=[]
    for currency in ['BTC','ETH']:
        for resolution in ['1D','3600']:
            end=END;rows={};success=True
            for page in range(100):
                url='https://www.deribit.com/api/v2/public/get_volatility_index_data?'+urlencode({'currency':currency,'start_timestamp':START,'end_timestamp':end,'resolution':resolution})
                rec={'url':url,'currency':currency,'resolution':resolution,'page':page,'downloaded_at_utc':datetime.now(timezone.utc).isoformat()}
                try:
                    data=get(url);rec['sha256']=hashlib.sha256(data).hexdigest();rec['bytes']=len(data)
                    doc=json.loads(data)
                    if 'error' in doc:raise ValueError(str(doc['error']))
                    result=doc['result'];batch=result['data']
                    for row in batch:
                        key=int(row[0]);values=row[1:]
                        if len(row)!=5 or any(not isinstance(v,(int,float)) or v<=0 for v in values):raise ValueError('invalid IV candle')
                        if key in rows and rows[key]!=row:raise ValueError('inconsistent duplicate candle')
                        rows[key]=row
                    (root/f'{currency}_{resolution}_{page:03d}.json').write_bytes(data)
                    rec.update(success=True,rows=len(batch),continuation=result.get('continuation'));receipts.append(rec)
                    continuation=result.get('continuation')
                    if continuation is None:break
                    if int(continuation)>=end:raise ValueError('pagination failed to advance')
                    end=int(continuation);time.sleep(.2)
                except Exception as error:
                    rec.update(success=False,error=repr(error));receipts.append(rec);success=False;break
            else:success=False
            selected=[rows[k] for k in sorted(rows) if START<=k<END]
            if selected:
                with (root/f'{currency}_{resolution}.csv').open('w',newline='') as f:
                    w=csv.writer(f);w.writerow(['timestamp','open','high','low','close']);w.writerows(selected)
            print(currency,resolution,'success',success,'rows',len(selected),flush=True)
    try:
        url='https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv';data=get(url);(root/'VIX_History.csv').write_bytes(data)
        receipts.append({'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'success':True})
    except Exception as error:receipts.append({'source':'CBOE_VIX','success':False,'error':repr(error)})
    (root/'PROVENANCE.json').write_text(json.dumps(receipts,indent=2)+'\n')
if __name__=='__main__':main()

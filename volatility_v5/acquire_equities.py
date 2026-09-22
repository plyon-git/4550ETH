"""Read-only daily equity/volatility acquisition; not ES intraday data."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
import csv,hashlib,json,time

def main():
 root=Path('volatility_v5/equity_data');root.mkdir(parents=True,exist_ok=True);receipts=[]
 for symbol in ['SPY','QQQ']:
  url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?'+urlencode({'period1':1262304000,'period2':1788220800,'interval':'1d','events':'div,splits'})
  r={'symbol':symbol,'url':url}
  try:
   with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as f:data=f.read(5000000)
   r.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data));doc=json.loads(data)
   if doc['chart']['error']:raise ValueError(str(doc['chart']['error']))
   result=doc['chart']['result'][0];q=result['indicators']['quote'][0]
   (root/(symbol+'_raw.json')).write_bytes(data)
   with (root/(symbol+'_daily.csv')).open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['timestamp','open','high','low','close','volume'])
    for i,t in enumerate(result['timestamp']):w.writerow([t,*[q[k][i] for k in ['open','high','low','close','volume']]])
   r.update(success=True,rows=len(result['timestamp']))
  except Exception as error:r.update(success=False,error=repr(error))
  receipts.append(r)
 for symbol in ['VIX','VXN']:
  url=f'https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv';r={'symbol':symbol,'url':url}
  try:
   with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as f:data=f.read(5000000)
   (root/(symbol+'_History.csv')).write_bytes(data);r.update(success=True,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
  except Exception as error:r.update(success=False,error=repr(error))
  receipts.append(r)
 (root/'PROVENANCE.json').write_text(json.dumps(receipts,indent=2)+'\n');print(json.dumps(receipts,indent=2))
if __name__=='__main__':main()

"""Real Binance USD-M REST adapter, supporting demo and production endpoints.

POST order requests are never blindly retried. Caller must persist the client ID
before submission and reconcile an ambiguous response using that same ID.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import hashlib,hmac,time
from urllib.parse import urlencode
from typing import Any
import requests

class ExchangeError(RuntimeError):
    def __init__(self,code:int,message:str='exchange rejected request',status:int=0):
        self.code,self.status=code,status
        super().__init__(f'{message} (code={code}, http={status})')
class AmbiguousExecution(ExchangeError):pass
class ConnectivityError(ExchangeError):pass

D=Decimal

def decimal_string(value:Decimal|float|str)->str:
    d=D(str(value))
    if not d.is_finite():raise ValueError('nonfinite order value')
    return format(d,'f')

def round_grid(value:float|str,step:float|str,up:bool=False)->Decimal:
    a,b=D(str(value)),D(str(step))
    if not a.is_finite() or not b.is_finite() or b<=0:raise ValueError('invalid grid')
    return (a/b).to_integral_value(rounding=ROUND_UP if up else ROUND_DOWN)*b

@dataclass(frozen=True)
class Instrument:
    symbol:str
    tick:str
    step:str
    min_qty:str
    max_qty:str
    min_notional:str
    def quantity(self,value:float)->Decimal:
        q=round_grid(value,self.step)
        if q<D(self.min_qty) or q>D(self.max_qty):raise ValueError('quantity outside instrument limits')
        return q
    def price(self,value:float,up:bool=False)->Decimal:
        p=round_grid(value,self.tick,up)
        if p<=0:raise ValueError('nonpositive price')
        return p

class Binance:
    HOSTS={'live':'https://fapi.binance.com','testnet':'https://demo-fapi.binance.com'}
    def __init__(self,mode:str,key:str='',secret:str='',session:requests.Session|None=None,timeout:float=10):
        if mode not in self.HOSTS:raise ValueError('mode must be live or testnet')
        self.mode,self.host=mode,self.HOSTS[mode]
        self._key,self._secret=key,secret
        self.session=session or requests.Session()
        self.session.trust_env=False
        self.timeout=timeout;self.offset_ms=0;self._last_request=0.;self._backoff_until=0.
    def __repr__(self):return f'Binance(mode={self.mode!r}, credentials_redacted=True)'
    @property
    def account_fingerprint(self):return hashlib.sha256((self.mode+':'+self._key).encode()).hexdigest()[:16]
    def close(self):self.session.close()
    def _pace(self):
        wait=max(self._last_request+.16,self._backoff_until)-time.monotonic()
        if wait>0:time.sleep(min(wait,120))
        self._last_request=time.monotonic()
    def request(self,method:str,path:str,params:dict|None=None,signed:bool=False):
        if not path.startswith('/fapi/'):raise ValueError('unsupported API path')
        method=method.upper();original=dict(params or {})
        for attempt in range(3 if method=='GET' else 1):
            data={k:(str(v).lower() if isinstance(v,bool) else str(v)) for k,v in original.items() if v is not None}
            headers={'Accept':'application/json'}
            if signed:
                if not self._key or not self._secret:raise ValueError('credentials missing from environment')
                data.update(timestamp=str(int(time.time()*1000)+self.offset_ms),recvWindow='5000')
                query=urlencode(data)
                signature=hmac.new(self._secret.encode(),query.encode(),hashlib.sha256).hexdigest()
                payload=query+'&signature='+signature;headers['X-MBX-APIKEY']=self._key
            else:payload=urlencode(data)
            self._pace()
            try:
                if method=='GET':resp=self.session.request(method,self.host+path,params=payload,headers=headers,timeout=self.timeout,allow_redirects=False)
                else:
                    headers['Content-Type']='application/x-www-form-urlencoded'
                    resp=self.session.request(method,self.host+path,data=payload,headers=headers,timeout=self.timeout,allow_redirects=False)
            except requests.RequestException:
                if method!='GET':raise AmbiguousExecution(-1,'mutation response unknown; reconcile before retry') from None
                if attempt<2:time.sleep(.3*(2**attempt));continue
                raise ConnectivityError(-1,'read request unavailable') from None
            status=resp.status_code
            try:
                used=int(resp.headers.get('X-MBX-USED-WEIGHT-1M','0'))
                if used>=1800:self._backoff_until=max(self._backoff_until,time.monotonic()+60-time.time()%60+1)
            except (ValueError,TypeError):pass
            if status in (418,429):
                retry=min(120,max(1,float(resp.headers.get('Retry-After','10'))))
                self._backoff_until=time.monotonic()+retry
            if 300<=status<400:raise ConnectivityError(-1,'API redirect refused',status)
            if method!='GET' and (status>=500 or status in (408,429)):
                raise AmbiguousExecution(-1,'mutation execution status unknown',status)
            if method=='GET' and (status>=500 or status in (408,429)) and attempt<2:
                time.sleep(.3*(2**attempt));continue
            try:result=resp.json()
            except ValueError:
                if method!='GET':raise AmbiguousExecution(-1,'non-JSON mutation response',status) from None
                raise ConnectivityError(-1,'non-JSON read response',status) from None
            code=int(result.get('code',0)) if isinstance(result,dict) else 0
            if method!='GET' and code in (-1006,-1007):raise AmbiguousExecution(code,'mutation execution status unknown',status)
            if status>=400 or code<0:
                raise ExchangeError(code,'exchange request rejected',status)
            return result
        raise ConnectivityError(-1,'read retries exhausted')
    def sync_time(self):
        a=time.time()*1000;r=self.request('GET','/fapi/v1/time');b=time.time()*1000
        self.offset_ms=int(r['serverTime']-(a+b)/2)
        if b-a>3000:raise ConnectivityError(-1,'server-time roundtrip too slow')
        return int(r['serverTime'])
    def now_ms(self):return int(time.time()*1000)+self.offset_ms
    def instrument(self,symbol):
        r=self.request('GET','/fapi/v1/exchangeInfo')
        item=next((s for s in r['symbols'] if s['symbol']==symbol),None)
        if not item or item.get('status')!='TRADING' or item.get('contractType')!='PERPETUAL' or item.get('quoteAsset')!='USDT':
            raise ValueError('not an active USDT perpetual')
        fs={f['filterType']:f for f in item['filters']};lot=fs['LOT_SIZE'];market=fs.get('MARKET_LOT_SIZE',lot)
        step=max(D(lot['stepSize']),D(market.get('stepSize','0')))
        return Instrument(symbol,fs['PRICE_FILTER']['tickSize'],str(step),str(max(D(lot['minQty']),D(market.get('minQty','0')))),str(min(D(lot['maxQty']),D(market.get('maxQty',lot['maxQty'])))),str(fs['MIN_NOTIONAL'].get('notional',fs['MIN_NOTIONAL'].get('minNotional'))))
    def klines(self,symbol,interval,start=None,end=None,limit=1500):
        return self.request('GET','/fapi/v1/klines',{'symbol':symbol,'interval':interval,'startTime':start,'endTime':end,'limit':limit})
    def depth(self,symbol):return self.request('GET','/fapi/v1/depth',{'symbol':symbol,'limit':100})
    def mark(self,symbol):return self.request('GET','/fapi/v1/premiumIndex',{'symbol':symbol})
    def account(self):return self.request('GET','/fapi/v3/account',signed=True)
    def positions(self):return self.request('GET','/fapi/v3/positionRisk',signed=True)
    def position(self,symbol):
        rows=self.positions();rows=[r for r in rows if r['symbol']==symbol]
        nonzero=[r for r in rows if abs(float(r['positionAmt']))>0]
        if len(nonzero)>1 or any(r.get('positionSide','BOTH')!='BOTH' for r in nonzero):raise ValueError('one-way position mode required')
        return nonzero[0] if nonzero else {'symbol':symbol,'positionAmt':'0','entryPrice':'0','liquidationPrice':'0'}
    def mode_info(self):return self.request('GET','/fapi/v1/positionSide/dual',signed=True)
    def multi_assets(self):return self.request('GET','/fapi/v1/multiAssetsMargin',signed=True)
    def fee_rate(self,symbol):return self.request('GET','/fapi/v1/commissionRate',{'symbol':symbol},True)
    def brackets(self,symbol):
        rows=self.request('GET','/fapi/v1/leverageBracket',{'symbol':symbol},True)
        return rows[0]['brackets'] if isinstance(rows,list) else rows['brackets']
    def configure_margin(self,symbol,leverage):
        try:self.request('POST','/fapi/v1/marginType',{'symbol':symbol,'marginType':'ISOLATED'},True)
        except ExchangeError as e:
            if e.code!=-4046:raise
        return self.request('POST','/fapi/v1/leverage',{'symbol':symbol,'leverage':int(leverage)},True)
    def market(self,symbol,side,quantity,client_id,reduce=False):
        return self.request('POST','/fapi/v1/order',{'symbol':symbol,'side':side,'positionSide':'BOTH','type':'MARKET','quantity':decimal_string(quantity),'newClientOrderId':client_id,'newOrderRespType':'RESULT','reduceOnly':reduce},True)
    def query_order(self,symbol,client_id):
        return self.request('GET','/fapi/v1/order',{'symbol':symbol,'origClientOrderId':client_id},True)
    def cancel_order(self,symbol,client_id):
        return self.request('DELETE','/fapi/v1/order',{'symbol':symbol,'origClientOrderId':client_id},True)
    def open_orders(self,symbol):return self.request('GET','/fapi/v1/openOrders',{'symbol':symbol},True)
    def protective(self,symbol,side,trigger,client_id,take_profit=False):
        return self.request('POST','/fapi/v1/algoOrder',{'algoType':'CONDITIONAL','symbol':symbol,'side':side,'positionSide':'BOTH','type':'TAKE_PROFIT_MARKET' if take_profit else 'STOP_MARKET','triggerPrice':decimal_string(trigger),'workingType':'CONTRACT_PRICE','closePosition':'true','priceProtect':'false','clientAlgoId':client_id},True)
    def query_algo(self,client_id):return self.request('GET','/fapi/v1/algoOrder',{'clientAlgoId':client_id},True)
    def cancel_algo(self,client_id):return self.request('DELETE','/fapi/v1/algoOrder',{'clientAlgoId':client_id},True)
    def open_algos(self,symbol):return self.request('GET','/fapi/v1/openAlgoOrders',{'symbol':symbol},True)
    def fills(self,symbol,start=None,end=None,from_id=None):
        return self.request('GET','/fapi/v1/userTrades',{'symbol':symbol,'startTime':start if from_id is None else None,'endTime':end if from_id is None else None,'fromId':from_id,'limit':1000},True)
    def income(self,start,kind=None,end=None,page=1):return self.request('GET','/fapi/v1/income',{'startTime':start,'endTime':end,'incomeType':kind,'page':page,'limit':1000},True)

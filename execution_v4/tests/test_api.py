import hashlib,hmac
from urllib.parse import parse_qs
from unittest.mock import Mock
import pytest,requests
from trader.exchange import Binance,Instrument,round_grid,AmbiguousExecution,ExchangeError
class Response:
    def __init__(self,payload,status=200):self.payload=payload;self.status_code=status;self.headers={}
    def json(self):return self.payload
class Session:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def request(self,*a,**k):
        self.calls.append((a,k));r=self.responses.pop(0)
        if isinstance(r,Exception):raise r
        return r
    def close(self):pass

def client(responses):
    session=Session(responses);c=Binance('testnet','FAKE_TEST_KEY','FAKE_TEST_SECRET',session);c._pace=lambda:None;return c,session

def test_signed_market_request():
    c,s=client([Response({'status':'FILLED'})]);c.market('ETHUSDT','BUY',.123,'pl4_example')
    (method,url),kw=s.calls[0];q,signature=kw['data'].rsplit('&signature=',1)
    assert method=='POST' and url=='https://demo-fapi.binance.com/fapi/v1/order'
    assert hmac.new(b'FAKE_TEST_SECRET',q.encode(),hashlib.sha256).hexdigest()==signature
    d=parse_qs(q);assert d['quantity']==['0.123'] and d['positionSide']==['BOTH']
    assert kw['allow_redirects'] is False and 'FAKE_TEST_SECRET' not in str(kw)

def test_live_host_really_supported_with_mock_transport():
    s=Session([Response({'status':'FILLED'})]);c=Binance('live','fake','fake',s);c._pace=lambda:None
    c.market('ETHUSDT','SELL',1,'pl4_mock',True)
    assert s.calls[0][0][1]=='https://fapi.binance.com/fapi/v1/order'
    assert parse_qs(s.calls[0][1]['data'])['reduceOnly']==['true']

def test_exchange_held_close_all_protection():
    c,s=client([Response({'algoStatus':'NEW'})]);c.protective('ETHUSDT','SELL',1900,'pl4_stop')
    d=parse_qs(s.calls[0][1]['data']);assert d['type']==['STOP_MARKET']
    assert d['closePosition']==['true'] and d['workingType']==['CONTRACT_PRICE']
    assert 'quantity' not in d and 'reduceOnly' not in d
    assert s.calls[0][0][1].endswith('/fapi/v1/algoOrder')

@pytest.mark.parametrize('response',[requests.Timeout(),Response({},503),Response({'code':-1007},400),Response({},429)])
def test_ambiguous_order_is_not_retried(response):
    c,s=client([response])
    with pytest.raises(AmbiguousExecution):c.market('ETHUSDT','BUY',1,'pl4_unknown')
    assert len(s.calls)==1

def test_auth_error_does_not_echo_credentials():
    c,s=client([Response({'code':-2015,'msg':'untrusted key echo FAKE_TEST_SECRET'},401)])
    with pytest.raises(ExchangeError) as e:c.account()
    assert 'FAKE_TEST_SECRET' not in str(e.value)

def test_get_retries_are_read_only(monkeypatch):
    monkeypatch.setattr('time.sleep',lambda x:None)
    c,s=client([requests.Timeout(),Response({'serverTime':1})]);assert c.request('GET','/fapi/v1/time')['serverTime']==1
    assert len(s.calls)==2

def test_testnet_and_live_fingerprints_differ():
    assert Binance('testnet','a','b').account_fingerprint!=Binance('live','a','b').account_fingerprint

@pytest.mark.parametrize('bad',['paper','https://evil.invalid',None])
def test_unlisted_hosts_refused(bad):
    with pytest.raises(ValueError):Binance(bad)

def test_fills_time_and_id_parameters_not_combined():
    c,s=client([Response([])]);c.fills('ETHUSDT',start=1,end=5,from_id=10)
    d=parse_qs(s.calls[0][1]['params']);assert 'startTime' not in d and 'endTime' not in d and d['fromId']==['10']

def test_decimal_grids():
    assert str(round_grid('1.239','.01'))=='1.23';assert str(round_grid('1.231','.01',True))=='1.24'
    ins=Instrument('ETHUSDT','.01','.001','.001','1000','20')
    assert str(ins.quantity(.1239999))=='0.123'
    with pytest.raises(ValueError):ins.quantity(.0001)
    with pytest.raises(ValueError):ins.price(float('nan'))

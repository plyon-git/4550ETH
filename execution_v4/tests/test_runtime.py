from copy import deepcopy
from dataclasses import asdict
import json
from unittest.mock import Mock
import pytest
from trader.runtime import Runtime,Halt
from trader.store import Store
from trader.config import Settings
from trader.strategy import StrategySpec
from trader.exchange import Instrument,AmbiguousExecution,ExchangeError
from trader.risk import RiskState

class FakeVenue:
    account_fingerprint='fake_account'
    def __init__(self):
        self.now=1780000000000;self.q=0.;self.entry=2000.;self.wallet=10000.;self.orders={};self.algos={};self.calls=[];self.unknown_after_accept=False;self.reject_stop=False;self.partial=False;self.trade_rows=[]
    def now_ms(self):return self.now
    def sync_time(self):return self.now
    def mode_info(self):return {'dualSidePosition':False}
    def multi_assets(self):return {'multiAssetsMargin':False}
    def account(self):return {'canTrade':True,'totalWalletBalance':str(self.wallet),'totalMarginBalance':str(self.wallet),'availableBalance':str(self.wallet)}
    def position(self,symbol):return {'symbol':symbol,'positionAmt':str(self.q),'entryPrice':str(self.entry),'liquidationPrice':('500' if self.q>0 else '8000') if self.q else '0','positionSide':'BOTH'}
    def positions(self):return [self.position('ETHUSDT')]
    def open_orders(self,symbol):return [o for o in self.orders.values() if o['status'] not in ('FILLED','CANCELED')]
    def instrument(self,symbol):return Instrument(symbol,'.01','.001','.001','1000','20')
    def brackets(self,symbol):return [{'notionalFloor':0,'notionalCap':1e9,'initialLeverage':125,'maintMarginRatio':.004}]
    def fee_rate(self,symbol):return {'takerCommissionRate':'.0005'}
    def market(self,symbol,side,quantity,cid,reduce=False):
        self.calls.append(('market',cid,reduce));qty=quantity*(.4 if self.partial and not reduce else 1)
        if cid in self.orders:raise AssertionError('Duplicate submitted intent')
        sign=1 if side=='BUY' else -1
        if reduce:assert sign*self.q<0;qty=min(qty,abs(self.q))
        self.q+=sign*qty;self.wallet-=qty*self.entry*.0005
        r={'clientOrderId':cid,'status':'PARTIALLY_FILLED' if self.partial and not reduce else 'FILLED','executedQty':str(qty),'avgPrice':str(self.entry)};self.orders[cid]=r
        if self.unknown_after_accept:self.unknown_after_accept=False;raise AmbiguousExecution(-1007)
        return deepcopy(r)
    def query_order(self,symbol,cid):
        if cid not in self.orders:raise ExchangeError(-2013)
        return deepcopy(self.orders[cid])
    def cancel_order(self,symbol,cid):self.orders[cid]['status']='CANCELED';return deepcopy(self.orders[cid])
    def protective(self,symbol,side,trigger,cid,take_profit=False):
        self.calls.append(('protect',cid,take_profit))
        if self.reject_stop and not take_profit:raise ExchangeError(-2021)
        self.algos[cid]={'clientAlgoId':cid,'algoStatus':'NEW','triggerPrice':str(trigger)};return deepcopy(self.algos[cid])
    def query_algo(self,cid):
        if cid not in self.algos:raise ExchangeError(-2013)
        return deepcopy(self.algos[cid])
    def open_algos(self,symbol):return list(self.algos.values())
    def cancel_algo(self,cid):self.algos.pop(cid,None);return {'code':200}
    def fills(self,*a,**k):return self.trade_rows
    def income(self,*a,**k):return []

@pytest.fixture
def rt(tmp_path,monkeypatch):
    monkeypatch.setattr('time.sleep',lambda s:None)
    v=FakeVenue();store=Store(tmp_path/'state.sqlite');r=Runtime(v,store,StrategySpec(),Settings(),'testnet');r.initialize();yield r;store.close()

def plan(rt,cid='pl4_entry'):
    p={'id':cid,'side':1,'stop_fraction':.02,'entry_ms':rt.v.now_ms(),'equity_before':10000,'quantity':1.}
    rt.s.set('entry_plan',p);return p

def open_position(rt):
    p=plan(rt);response=rt.submit(p['id'],'ENTRY',{'quantity':1},lambda:rt.v.market('ETHUSDT','BUY',1,p['id']))
    rt.adopt_filled(p,rt.v.position('ETHUSDT'));rt.ensure_protection();return p

def test_accepted_but_timed_out_order_queries_not_retries(rt):
    rt.v.unknown_after_accept=True;p=open_position(rt)
    assert len([c for c in rt.v.calls if c[0]=='market'])==1
    assert rt.v.q==1 and len(rt.v.algos)==2
    assert rt.s.get_intent(p['id'])['state']=='FILLED'

def test_permanently_unknown_order_never_resubmitted(rt):
    p=plan(rt);rt.s.intent(p['id'],'ENTRY','ETHUSDT',{'quantity':1});rt.s.update_intent(p['id'],'UNKNOWN')
    with pytest.raises(Halt):rt.recover_pending()
    assert not [c for c in rt.v.calls if c[0]=='market']

def test_crash_after_filled_response_recovers_protection(rt):
    p=plan(rt);rt.submit(p['id'],'ENTRY',{},lambda:rt.v.market('ETHUSDT','BUY',1,p['id']))
    assert rt.s.get('position') is None
    rt.recover_pending();assert rt.s.get('position')['quantity']==1 and len(rt.v.algos)==2

def test_crash_after_http_acceptance_recovers_unknown(rt):
    p=plan(rt);rt.s.intent(p['id'],'ENTRY','ETHUSDT',{});rt.s.update_intent(p['id'],'SUBMITTED');rt.v.market('ETHUSDT','BUY',1,p['id'])
    rt.recover_pending();assert rt.s.get('position') and len(rt.v.algos)==2

def test_partial_fill_is_protected_then_cancelled(rt):
    rt.v.partial=True;p=plan(rt);rt.s.intent(p['id'],'ENTRY','ETHUSDT',{});rt.s.update_intent(p['id'],'SUBMITTED');rt.v.market('ETHUSDT','BUY',1,p['id'])
    rt.recover_pending();assert rt.v.q==.4 and rt.v.orders[p['id']]['status']=='CANCELED'
    assert rt.s.get('position')['quantity']==.4 and len(rt.v.algos)==2

def test_failed_stop_triggers_reduce_only_flatten(rt):
    p=plan(rt);rt.submit(p['id'],'ENTRY',{},lambda:rt.v.market('ETHUSDT','BUY',1,p['id']));rt.adopt_filled(p,rt.v.position('ETHUSDT'))
    rt.v.reject_stop=True
    with pytest.raises(ExchangeError):rt.ensure_protection()
    assert rt.v.q==0 and rt.s.get('halt')
    assert any(c[0]=='market' and c[2] for c in rt.v.calls)

def test_operator_flatten_closes_owned_position_only(rt):
    open_position(rt);rt.flatten('OPERATOR');assert rt.v.q==0;assert rt.s.get('position') is None;assert not rt.v.algos

def test_unowned_position_not_adopted_or_liquidated(rt):
    rt.v.q=1
    with pytest.raises(Halt):rt.reconcile()
    assert rt.v.q==1 and not rt.v.calls

def test_enlarged_external_position_halts(rt):
    open_position(rt);rt.v.q=2
    with pytest.raises(Halt):rt.ensure_protection()
    assert rt.v.q==2

def test_existing_protection_not_reposted_each_cycle(rt):
    open_position(rt);n=len(rt.v.calls);rt.ensure_protection();assert len(rt.v.calls)==n

def test_stop_filled_then_orphan_target_cancelled(rt):
    open_position(rt);rt.v.q=0;rt.reconcile();assert not rt.v.algos and rt.s.get('position') is None

def test_persistent_daily_count_not_doubled_by_recovery(rt):
    open_position(rt);assert rt.s.get('risk')['entries_today']==1
    rt.recover_pending();assert rt.s.get('risk')['entries_today']==1

def test_additional_fill_of_same_entry_is_not_foreign_position(rt):
    rt.v.partial=True;p=plan(rt);rt.submit(p['id'],'ENTRY',{},lambda:rt.v.market('ETHUSDT','BUY',1,p['id']))
    rt.adopt_filled(p,rt.v.position('ETHUSDT'));rt.ensure_protection()
    rt.v.q=1;rt.v.entry=2001;rt.v.orders[p['id']].update(status='FILLED',executedQty='1',avgPrice='2001')
    rt.ensure_protection()
    assert rt.s.get('position')['quantity']==1 and rt.s.get('position')['entry']==2001
    assert rt.s.get('risk')['entries_today']==1 and len(rt.v.algos)==2

def test_late_reported_fill_in_overlap_is_recovered_once(rt):
    rt.v.now+=10000;rt.sync_fills();rt.v.trade_rows=[{'symbol':'ETHUSDT','id':99,'time':rt.v.now-5000,'qty':'1'}]
    rt.sync_fills();rt.sync_fills();assert rt.s.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0]==1

def test_income_overlap_does_not_repeat_transfer_event(rt):
    row={'incomeType':'TRANSFER','tranId':77,'income':'10','time':rt.v.now}
    rt.v.income=lambda *a,**k:[row]
    with pytest.raises(Halt):rt.sync_income()
    rt.s.set('halt',None);rt.sync_income()
    assert rt.s.get('halt') is None

import json
from dataclasses import replace
import pytest
from trader.store import Store,SingleProcess
from trader.risk import RiskState,size_plan,protection_prices
from trader.exchange import Instrument
from trader.strategy import StrategySpec
from trader.__main__ import parser,authorize_mutation

@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'state.sqlite');yield s;s.close()

def test_intent_persisted_before_submission(store):
    assert store.intent('a','ENTRY','ETHUSDT',{'q':1});assert store.get_intent('a')['state']=='PLANNED'
    assert not store.intent('a','ENTRY','ETHUSDT',{'q':1})
    with pytest.raises(ValueError):store.intent('a','ENTRY','ETHUSDT',{'q':2})

def test_unknown_and_new_remain_pending(store):
    for k,state in [('a','UNKNOWN'),('b','NEW')]:store.intent(k,'ENTRY','ETHUSDT',{});store.update_intent(k,state)
    assert len(store.pending())==2

def test_binding_mismatch_refused(store):
    store.bind({'account':'a','mode':'testnet'});store.bind({'account':'a','mode':'testnet'})
    with pytest.raises(ValueError):store.bind({'account':'b','mode':'live'})

def test_signal_and_fills_deduplicate(store):
    assert store.claim_signal('signal','ETHUSDT',123,{})
    assert not store.claim_signal('signal','ETHUSDT',123,{})
    row={'symbol':'ETHUSDT','id':1};store.put_fills([row,row]);assert store.db.execute('SELECT count(*) FROM fills').fetchone()[0]==1

def test_revised_and_open_bars_refused(store):
    bar=[0,100,110,90,105,5,59999];store.put_bars('ETHUSDT','1m',[bar],50000);assert not store.bars('ETHUSDT','1m')
    store.put_bars('ETHUSDT','1m',[bar],60000);bar[4]=106
    with pytest.raises(ValueError):store.put_bars('ETHUSDT','1m',[bar],60000)

def test_invalid_ohlcv_refused(store):
    with pytest.raises(ValueError):store.put_bars('ETHUSDT','1m',[[0,100,90,80,105,5,59999]],60000)

def test_single_process_lock(tmp_path):
    with SingleProcess(tmp_path/'state'):
        with pytest.raises(RuntimeError):
            with SingleProcess(tmp_path/'state'):pass

def test_risk_state_survives_restart(store):
    from dataclasses import asdict
    spec=StrategySpec();risk=RiskState.initial(100000,10000);risk.update(110000,9400,spec)
    assert risk.day_locked;store.set('risk',asdict(risk));risk=RiskState(**store.get('risk'))
    risk.update(120000,10000,spec);assert risk.day_locked and risk.budget(10000,spec)==0

def test_new_day_does_not_reset_weekly_lock():
    spec=StrategySpec();risk=RiskState.initial(0,10000);risk.update(1,8000,spec);risk.update(86400000,8000,spec)
    assert risk.week_locked and risk.budget(8000,spec)==0

def test_500_nominal_does_not_multiply_account_risk():
    spec=StrategySpec();risk=RiskState.initial(0,10000);instrument=Instrument('ETHUSDT','.01','.001','.001','1000','20')
    brackets=[{'notionalFloor':0,'notionalCap':1e8,'initialLeverage':125,'maintMarginRatio':.004}]
    a=size_plan(spec,risk,instrument,1,2000,10000,10000,1000,.02,brackets,20,.0005)
    b=size_plan(spec,risk,instrument,1,2000,10000,10000,1000,.02,brackets,500,.0005)
    assert a.quantity==b.quantity;assert b.contract_leverage<500 and b.planned_loss<=100
    assert b.account_exposure<=spec.exposure_cap

def test_too_small_risk_never_rounded_up():
    spec=StrategySpec(risk_fraction=.00001);risk=RiskState.initial(0,100);instrument=Instrument('ETHUSDT','.01','.001','.001','1000','20')
    with pytest.raises(ValueError):size_plan(spec,risk,instrument,1,2000,100,100,1000,.02,[{'notionalFloor':0,'notionalCap':1e9,'initialLeverage':100,'maintMarginRatio':.004}],20,.0005)

@pytest.mark.parametrize('side',[1,-1])
def test_protection_correct_side(side):
    ins=Instrument('ETHUSDT','.01','.001','.001','1000','20');stop,target,d=protection_prices(side,2000,.01,4,ins)
    assert side*(2000-stop)>0 and side*(target-2000)>0

def test_production_requires_both_acknowledgments():
    p=parser();base=['run','--config','fake.json','--mode','live']
    with pytest.raises(ValueError):authorize_mutation(p.parse_args(base))
    with pytest.raises(ValueError):authorize_mutation(p.parse_args(base+['--live-confirmation','I_ACCEPT_REAL_ORDERS']))
    authorize_mutation(p.parse_args(base+['--live-confirmation','I_ACCEPT_REAL_ORDERS','--confirm-venue-eligibility']))

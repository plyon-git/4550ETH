"""Account loss budgets, quantity grids and collateral-aware sizing."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import math
from .exchange import Instrument
from .strategy import StrategySpec

@dataclass
class RiskState:
    day:int
    week:int
    day_base:float
    week_base:float
    last_equity:float
    day_locked:bool=False
    week_locked:bool=False
    entries_today:int=0
    last_exit_ms:int=0
    @classmethod
    def initial(cls,now_ms,equity):
        day=now_ms//86400000;return cls(day,(day+3)//7,equity,equity,equity)
    def update(self,now_ms,equity,spec):
        if not math.isfinite(equity):raise ValueError('nonfinite account equity')
        d=now_ms//86400000;w=(d+3)//7
        if d<self.day:raise ValueError('clock moved backwards across a risk boundary')
        base=max(equity,self.last_equity)
        if w!=self.week:self.week=w;self.week_base=base;self.week_locked=False
        if d!=self.day:self.day=d;self.day_base=base;self.day_locked=False;self.entries_today=0
        self.last_equity=equity
        if equity<=self.day_base*(1-spec.daily_loss):self.day_locked=True
        if equity<=self.week_base*(1-spec.weekly_loss):self.week_locked=True
    def budget(self,equity,spec):
        if self.day_locked or self.week_locked:return 0.
        return max(0.,min(equity*spec.risk_fraction,.8*(equity-self.day_base*(1-spec.daily_loss)),.8*(equity-self.week_base*(1-spec.weekly_loss))))

@dataclass(frozen=True)
class SizePlan:
    quantity:float
    price:float
    notional:float
    account_exposure:float
    planned_loss:float
    requested_contract_leverage:int
    contract_leverage:int
    approximate_margin:float
    maintenance_rate:float
    stop_fraction:float

def size_plan(spec:StrategySpec,risk:RiskState,instrument:Instrument,side:int,price:float,
              equity:float,available:float,prior_volume:float,stop_fraction:float,brackets:list,
              requested_leverage:int,fee_rate:float,slippage_bps:float=2.,participation:float=.01,
              max_notional:float=1_000_000.,liquidation_buffer:float=.01)->SizePlan:
    spec.validate()
    if side not in (-1,1):raise ValueError('invalid side')
    if not all(math.isfinite(x) for x in [price,equity,available,prior_volume,stop_fraction,fee_rate,max_notional]):raise ValueError('nonfinite sizing input')
    if min(price,equity,available,prior_volume,stop_fraction,max_notional)<=0:raise ValueError('nonpositive sizing input')
    if not 0<participation<=1 or not 1<=requested_leverage<=500:raise ValueError('invalid sizing controls')
    if fee_rate<0 or slippage_bps<0 or liquidation_buffer<=0:raise ValueError('invalid cost/buffer')
    risk_per_unit=price*stop_fraction+price*(2*fee_rate+2*slippage_bps/10000)+2*float(instrument.tick)
    budget=risk.budget(equity,spec)
    qty=min(budget/risk_per_unit,equity*spec.exposure_cap/price,prior_volume*participation,max_notional/price,float(instrument.max_qty))
    if qty<=0:raise ValueError('no risk budget')
    chosen=None
    for _ in range(8):
        tier=next((b for b in brackets if float(b['notionalFloor'])<=qty*price<float(b['notionalCap'])),None)
        if tier is None:raise ValueError('no verified leverage bracket for proposed size')
        mm=float(tier['maintMarginRatio'])
        safe=math.floor(1/(stop_fraction+mm+liquidation_buffer+2*fee_rate))
        lev=min(requested_leverage,int(tier['initialLeverage']),safe)
        if lev<1:raise ValueError('stop/collateral requirement exceeds available leverage geometry')
        nextq=min(qty,available*.9/(price*(1/lev+2*fee_rate)))
        chosen=(lev,mm)
        if abs(nextq-qty)<1e-12:break
        qty=nextq
    q=instrument.quantity(qty);n=float(q)*price
    if n<float(instrument.min_notional):raise ValueError('risk-sized quantity below minimum notional; not rounding up')
    if price*(1+side*stop_fraction*spec.target_r)<=0:raise ValueError('invalid target price')
    return SizePlan(float(q),price,n,n/equity,float(q)*risk_per_unit,requested_leverage,chosen[0],n/chosen[0],chosen[1],stop_fraction)

def protection_prices(side,entry,stop_fraction,target_r,instrument):
    distance=entry*stop_fraction
    stop=float(instrument.price(entry-side*distance,up=side==1))
    target=float(instrument.price(entry+side*distance*target_r,up=side==1))
    if side*(entry-stop)<=0 or side*(target-entry)<=0:raise ValueError('invalid protection levels')
    return stop,target,distance

def effective_stop(side,entry,quantity,original_stop,cash,risk,spec):
    q=side*quantity
    levels=[original_stop,entry+(risk.day_base*(1-spec.daily_loss)-cash)/q,entry+(risk.week_base*(1-spec.weekly_loss)-cash)/q]
    return max(levels) if side==1 else min(levels)

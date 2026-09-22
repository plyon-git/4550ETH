from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib,json,math
from .strategy import StrategySpec

@dataclass(frozen=True)
class Settings:
    symbol:str='ETHUSDT'
    requested_contract_leverage:int=20
    max_notional_usdt:float=1_000_000.
    participation:float=.01
    fee_bps_floor:float=5.
    modeled_slippage_bps:float=2.
    maximum_book_slippage_bps:float=15.
    max_signal_age_seconds:int=30
    polling_seconds:float=2.
    liquidation_buffer_fraction:float=.01
    max_entries_per_day:int=300
    bootstrap_start_utc:str='2020-01-01T00:00:00Z'
    ml_model_path:str|None=None
    ml_model_sha256:str|None=None
    ml_threshold:float=.55
    directional_threshold_r:float=.30
    auto_refit:bool=False
    refit_weeks:int=13
    refit_anchor_utc:str='2023-10-02T00:00:00Z'
    def validate(self):
        if self.symbol not in ('ETHUSDT','BTCUSDT','XRPUSDT'):raise ValueError('unsupported symbol')
        for k,v in asdict(self).items():
            if isinstance(v,(int,float)) and not math.isfinite(v):raise ValueError('nonfinite setting')
        if not 1<=self.requested_contract_leverage<=500:raise ValueError('invalid requested leverage')
        if not 0<self.participation<=.10:raise ValueError('invalid participation')
        if not 1<=self.max_entries_per_day<=1000:raise ValueError('invalid entry limit')
        if self.polling_seconds<1 or self.max_signal_age_seconds<1:raise ValueError('invalid runtime timing')
        if min(self.max_notional_usdt,self.maximum_book_slippage_bps,self.liquidation_buffer_fraction)<=0:raise ValueError('invalid controls')
        if min(self.fee_bps_floor,self.modeled_slippage_bps)<0:raise ValueError('invalid costs')
        if bool(self.ml_model_path)!=bool(self.ml_model_sha256):raise ValueError('model path and immutable SHA-256 must be supplied together')
        if self.ml_model_sha256 and (len(self.ml_model_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.ml_model_sha256)):raise ValueError('invalid model hash')
        if not isinstance(self.auto_refit,bool):raise ValueError('auto_refit must be a JSON boolean')
        if self.auto_refit and not self.ml_model_path:raise ValueError('scheduled refitting requires an initial pinned model')
        if not 1<=self.refit_weeks<=14:raise ValueError('refit interval exceeds bounded model lifetime')
        for date in (self.bootstrap_start_utc,self.refit_anchor_utc):
            from datetime import datetime
            if datetime.fromisoformat(date.replace('Z','+00:00')).tzinfo is None:raise ValueError('data and refit dates must be timezone-aware')
        if not 0<self.ml_threshold<1:raise ValueError('invalid model threshold')
        return self

def load_config(path,training=False):
    obj=json.loads(Path(path).read_text())
    spec=StrategySpec(**obj['strategy']).validate();settings=Settings(**obj.get('execution',{})).validate()
    if spec.family=='ml_directional' and not training and (spec.timeframe_minutes!=60 or not settings.ml_model_path):raise ValueError('directional trading requires a pinned 1-hour model; no fallback rule is allowed')
    if settings.directional_threshold_r<=0:raise ValueError('invalid expected-return threshold')
    return spec,settings,obj

def config_identity(spec,settings):
    return hashlib.sha256(json.dumps({'strategy':asdict(spec),'execution':asdict(settings)},sort_keys=True).encode()).hexdigest()

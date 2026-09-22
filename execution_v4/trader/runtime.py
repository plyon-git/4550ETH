"""Persistent long/short execution service. This module can submit real orders.
Only explicit CLI live acknowledgments construct a production credentialed client.
Research modules never import or invoke this service.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib,json,math,time
import numpy as np,pandas as pd
from .exchange import ExchangeError,AmbiguousExecution,Binance
from .risk import RiskState,size_plan,protection_prices,effective_stop
from .strategy import closed_bar_features
from .config import config_identity

class Halt(RuntimeError):pass
TERMINAL={'FILLED','CANCELED','EXPIRED','REJECTED','EXPIRED_IN_MATCH'}
def client_id(*parts):return 'pl4_'+hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:30]

def book_price(book,side,quantity):
    levels=book['asks' if side==1 else 'bids'];remaining=quantity;cost=0.
    for price,qty,*_ in levels:
        px,q=float(price),float(qty)
        if not math.isfinite(px+q) or px<=0 or q<0:raise ValueError('invalid book level')
        used=min(remaining,q);cost+=used*px;remaining-=used
        if remaining<=1e-12:break
    if remaining>1e-12:raise Halt('visible depth does not support order size')
    return cost/quantity

class Runtime:
    def __init__(self,venue,store,spec,settings,mode):
        self.v,self.s,self.spec,self.cfg,self.mode=venue,store,spec,settings,mode
        self.symbol=settings.symbol;self.interval=f'{spec.timeframe_minutes}m' if spec.timeframe_minutes<60 else ('1h' if spec.timeframe_minutes==60 else '4h')
        self.binding={'account':venue.account_fingerprint,'mode':mode,'symbol':self.symbol,'config':config_identity(spec,settings)}
        self.instrument=None;self.fee_rate=settings.fee_bps_floor/10000;self.brackets=[];self.last_sync=0.;self.last_bars=0;self._bars_cache=None;self._feature_cache=None;self._features_key=None
    def log(self,kind,**payload):
        self.s.event(kind,payload);print(json.dumps({'utc':pd.Timestamp.now(tz='UTC').isoformat(),'event':kind,**payload},allow_nan=False),flush=True)
    def halt(self,reason):
        self.s.set('halt',reason);self.log('HALT',reason=reason)
        raise Halt(reason)
    def initialize(self):
        self.s.bind(self.binding);self.v.sync_time();self.last_sync=time.monotonic()
        seeded=self.s.get('history_seed')
        if seeded and (seeded['symbol']!=self.symbol or seeded['interval']!=self.interval):raise Halt('seeded market cache does not match configured market/timeframe')
        if self.v.mode_info().get('dualSidePosition'):raise Halt('one-way mode required; mode will not be changed automatically')
        if self.v.multi_assets().get('multiAssetsMargin'):raise Halt('single-asset USDT margin required')
        positions=self.v.positions()
        if any(abs(float(p.get('positionAmt',0)))>0 and p['symbol']!=self.symbol for p in positions):raise Halt('dedicated account required; other positions exist')
        if any(o.get('clientOrderId','').startswith('pl4_') is False for o in self.v.open_orders(self.symbol)):raise Halt('foreign open orders on strategy symbol')
        self.instrument=self.v.instrument(self.symbol);self.brackets=self.v.brackets(self.symbol)
        self.fee_rate=max(self.fee_rate,float(self.v.fee_rate(self.symbol)['takerCommissionRate']))
        account=self.v.account();eq=float(account['totalMarginBalance'])
        if not account.get('canTrade',True):raise Halt('account is not trade-enabled')
        self.s.set('started_ms',self.s.get('started_ms',self.v.now_ms()))
        if self.s.get('risk') is None:self.s.set('risk',asdict(RiskState.initial(self.v.now_ms(),eq)))
        self.recover_pending();self.reconcile()
        self.log('INITIALIZED',mode=self.mode,symbol=self.symbol,strategy=self.spec.identity,equity=eq)
    def risk_state(self,account):
        eq=float(account['totalMarginBalance'])
        r=RiskState(**self.s.get('risk'));r.update(self.v.now_ms(),eq,self.spec);self.s.set('risk',asdict(r))
        self.s.db.execute('INSERT OR REPLACE INTO equity VALUES(?,?,?)',(self.v.now_ms(),eq,float(account['availableBalance'])))
        return r
    def _query(self,cid,kind):
        try:return self.v.query_algo(cid) if kind in ('STOP','TARGET') else self.v.query_order(self.symbol,cid)
        except ExchangeError as e:
            if e.code in (-2013,-2011):return None
            raise
    def submit(self,cid,kind,payload,call):
        new=self.s.intent(cid,kind,self.symbol,payload)
        if not new:
            row=self.s.get_intent(cid)
            if row['state']=='REJECTED':raise Halt('persisted rejected intent will not be resubmitted')
            if row['state'] in TERMINAL or row['state']=='ACKNOWLEDGED':return json.loads(row['response'])
            return self.resolve(cid,kind)
        self.s.update_intent(cid,'SUBMITTED')
        try:response=call()
        except AmbiguousExecution:
            self.s.update_intent(cid,'UNKNOWN');self.log('UNKNOWN_RESPONSE',client_id=cid,order_kind=kind)
            return self.resolve(cid,kind)
        except ExchangeError as e:
            self.s.update_intent(cid,'REJECTED',{'code':e.code,'http':e.status});raise
        state=response.get('status','ACKNOWLEDGED')
        self.s.update_intent(cid,state,response);return response
    def resolve(self,cid,kind):
        for attempt in range(5):
            response=self._query(cid,kind)
            if response is not None:
                self.s.update_intent(cid,response.get('status','ACKNOWLEDGED'),response);return response
            time.sleep(.2*(attempt+1))
        self.s.update_intent(cid,'UNKNOWN')
        raise Halt(f'order {cid} remains ambiguous; do not resubmit it or clear the database')
    def recover_pending(self):
        plan=self.s.get('entry_plan')
        if plan and self.s.get('position') is None:
            intent=self.s.get_intent(plan['id'])
            if intent and intent['state'] in TERMINAL and float((json.loads(intent['response']) or {}).get('executedQty',0))>0:
                pos=self.v.position(self.symbol)
                if abs(float(pos['positionAmt']))>0:
                    if int(np.sign(float(pos['positionAmt'])))!=plan['side']:self.halt('filled intent position side mismatch')
                    self.adopt_filled(plan,pos);self.ensure_protection()
        for r in self.s.pending():
            try:response=self.resolve(r['id'],r['kind'])
            except Halt:
                plan=self.s.get('entry_plan');pos=self.v.position(self.symbol)
                if r['kind']=='ENTRY' and plan and abs(float(pos['positionAmt']))>0:
                    if int(np.sign(float(pos['positionAmt'])))!=plan['side']:self.halt('ambiguous entry has unexpected position side')
                    self.adopt_filled(plan,pos);self.ensure_protection()
                self.halt('unresolved order intent; existing protection retained; operator reconciliation required')
            if r['kind']=='ENTRY' and float(response.get('executedQty',0))>0:
                plan=self.s.get('entry_plan')
                if plan is None:self.halt('filled entry without persisted strategy plan')
                pos=self.v.position(self.symbol)
                if abs(float(pos['positionAmt']))>0:self.adopt_filled(plan,pos);self.ensure_protection()
            if response.get('status') in ('NEW','PARTIALLY_FILLED') and r['kind'] in ('ENTRY','EXIT'):
                try:self.v.cancel_order(self.symbol,r['id'])
                except ExchangeError:pass
                response=self.resolve(r['id'],r['kind'])
                if response.get('status') not in TERMINAL:self.halt('entry/exit is not terminal after cancellation')
    def adopt_filled(self,plan,pos):
        quantity=abs(float(pos['positionAmt']));entry=float(pos['entryPrice'])
        if quantity<=0 or entry<=0:raise Halt('cannot adopt empty fill')
        if quantity>plan['quantity']+float(self.instrument.step)/2:raise Halt('position exceeds persisted entry quantity')
        stop,target,distance=protection_prices(plan['side'],entry,plan['stop_fraction'],self.spec.target_r,self.instrument)
        prior=self.s.get('position')
        if prior and prior['id']==plan['id']:
            prior['quantity']=quantity;prior['entry']=entry;prior['initial_distance']=distance
            old_target_id=prior.get('target_id')
            if abs(target-prior['target'])>=float(self.instrument.tick):
                prior['target_revision']+=1;prior['target']=target
                new_id=self._protect(prior,'TARGET',target,prior['target_revision'])
                prior['target_id']=new_id;self.s.set('position',prior)
                if old_target_id:
                    try:self.v.cancel_algo(old_target_id)
                    except ExchangeError as e:
                        if e.code not in (-2011,-2013):raise
            else:self.s.set('position',prior)
            return
        state={'id':plan['id'],'side':plan['side'],'quantity':quantity,'entry':entry,'stop':stop,'target':target,'initial_distance':distance,'entry_ms':plan['entry_ms'],'stop_revision':0,'target_revision':0,'stop_id':None,'target_id':None,'last_trail_minute':0,'equity_before':plan['equity_before']}
        account=self.v.account();risk=RiskState(**self.s.get('risk'))
        state['stop']=float(self.instrument.price(effective_stop(state['side'],entry,quantity,stop,float(account['totalWalletBalance']),risk,self.spec),up=state['side']==1))
        with self.s.transaction():
            self.s.set('position',state)
            if self.s.get('counted_entry_id')!=plan['id']:
                risk.entries_today+=1;self.s.set('risk',asdict(risk));self.s.set('counted_entry_id',plan['id'])
        self.log('POSITION_ADOPTED',position_id=state['id'],side=state['side'],quantity=quantity,entry=entry)
    def _protect(self,position,kind,trigger,revision):
        cid=client_id(position['id'],kind,revision);side='SELL' if position['side']==1 else 'BUY'
        response=self.submit(cid,kind,{'side':side,'trigger':trigger,'closePosition':True},lambda:self.v.protective(self.symbol,side,trigger,cid,kind=='TARGET'))
        state=response.get('algoStatus',response.get('status'))
        if state not in ('NEW','WORKING','PENDING_NEW','ACCEPTED'):raise Halt('protection not confirmed active')
        return cid
    def ensure_protection(self):
        p=self.s.get('position')
        if not p:return
        pos=self.v.position(self.symbol)
        if float(pos['positionAmt'])==0:return
        actual=abs(float(pos['positionAmt']))
        if int(np.sign(float(pos['positionAmt'])))!=p['side']:self.halt('external position-side change detected')
        if actual>p['quantity']+float(self.instrument.step)/2:
            plan=self.s.get('entry_plan');known=self._query(p['id'],'ENTRY')
            if not plan or plan['id']!=p['id'] or not known or actual>plan['quantity']+float(self.instrument.step)/2 or actual>float(known.get('executedQty',0))+float(self.instrument.step)/2:
                self.halt('external position increase detected; review existing protection')
            self.adopt_filled(plan,pos);p=self.s.get('position')
        p['quantity']=actual;self.s.set('position',p)
        liq=float(pos.get('liquidationPrice',0) or 0)
        if liq>0 and p['side']*(p['stop']-liq)<=p['entry']*self.cfg.liquidation_buffer_fraction:
            self.flatten('INSUFFICIENT_LIQUIDATION_BUFFER');self.halt('liquidation boundary too close to intended stop')
        try:
            active=self.v.open_algos(self.symbol)
            if isinstance(active,dict):active=active.get('orders',[])
            activeids={r.get('clientAlgoId') for r in active}
            if any(not str(cid).startswith('pl4_') for cid in activeids):self.halt('foreign conditional order detected during owned position')
            if p['stop_id'] not in activeids:
                if p['stop_id'] is not None:p['stop_revision']+=1
                p['stop_id']=self._protect(p,'STOP',p['stop'],p['stop_revision']);self.s.set('position',p)
            if p['target_id'] not in activeids:
                if p['target_id'] is not None:p['target_revision']+=1
                p['target_id']=self._protect(p,'TARGET',p['target'],p['target_revision']);self.s.set('position',p)
        except (ExchangeError,Halt,ValueError):
            self.log('PROTECTION_FAILURE',position_id=p['id'])
            try:self.flatten('PROTECTION_FAILURE')
            finally:self.s.set('halt','protective order failed; check venue positions before restarting')
            raise
    def sync_fills(self):
        now=self.v.now_ms();cursor=max(self.s.get('started_ms',now),self.s.get('fill_cursor_ms',self.s.get('started_ms',now))-3600000)
        if now-cursor>89*86400000:self.halt('fill journal gap exceeds conservative API history window; recover venue exports first')
        loops=0
        while cursor<=now:
            end=min(now,cursor+6*86400000)
            rows=self.v.fills(self.symbol,start=cursor,end=end)
            self.s.put_fills(rows);loops+=1
            if len(rows)==1000:
                last=max(int(r['id']) for r in rows)
                for _ in range(100):
                    page=self.v.fills(self.symbol,from_id=last+1);self.s.put_fills(page)
                    if not page:break
                    last=max(int(r['id']) for r in page)
                    if len(page)<1000:break
                else:self.halt('fill pagination bound reached; reconciliation incomplete')
            cursor=end+1;self.s.set('fill_cursor_ms',cursor)
            if loops>20:self.halt('fill time pagination bound reached')
    def sync_income(self):
        now=self.v.now_ms();cursor=max(self.s.get('started_ms',now),self.s.get('income_cursor_ms',self.s.get('started_ms',now))-3600000)
        if now-cursor>89*86400000:self.halt('income journal gap requires reconciliation before trading')
        transfers=[]
        while cursor<=now:
            end=min(now,cursor+6*86400000)
            for page in range(1,101):
                rows=self.v.income(cursor,end=end,page=page)
                for row in rows:
                    inserted=self.s.put_income(row)
                    if inserted and row.get('incomeType') in ('TRANSFER','INTERNAL_TRANSFER') and abs(float(row.get('income',0)))>0:transfers.append(row)
                if len(rows)<1000:break
            else:self.halt('income pagination bound reached')
            cursor=end+1;self.s.set('income_cursor_ms',cursor)
        if transfers:self.halt('account transfer detected; reconcile external cash flow and risk bases before resume')
    def reconcile(self):
        p=self.s.get('position');pos=self.v.position(self.symbol);q=float(pos['positionAmt'])
        if p and q==0:
            self.sync_fills()
            for kind in ('stop_id','target_id'):
                if p.get(kind):
                    try:self.v.cancel_algo(p[kind])
                    except ExchangeError as e:
                        if e.code not in (-2011,-2013):raise
            closed={**p,'closed_observed_ms':self.v.now_ms(),'close_time_precision':'observed_position_flat; exact fills are in fills table'}
            self.s.db.execute('INSERT OR IGNORE INTO closed_positions VALUES(?,?)',(p['id'],json.dumps(closed)))
            self.s.set('position',None);self.s.set('entry_plan',None)
            risk=RiskState(**self.s.get('risk'));risk.last_exit_ms=self.v.now_ms();self.s.set('risk',asdict(risk))
            self.log('POSITION_CLOSED',position_id=p['id']);p=None
        elif p:self.ensure_protection()
        elif q!=0:self.halt('unowned exchange position detected; no automatic adoption or liquidation')
        if not p:
            algos=self.v.open_algos(self.symbol);algos=algos.get('orders',[]) if isinstance(algos,dict) else algos
            for r in algos:
                cid=r.get('clientAlgoId','')
                if cid.startswith('pl4_'):
                    try:self.v.cancel_algo(cid)
                    except ExchangeError as e:
                        if e.code not in (-2011,-2013):raise
                else:self.halt('foreign conditional order on strategy symbol')
        return pos
    def flatten(self,reason):
        p=self.s.get('position')
        if not p:raise Halt('no owned position to close')
        self.log('FLATTEN_REQUESTED',reason=reason,position_id=p['id'])
        for attempt in range(5):
            pos=self.v.position(self.symbol);q=float(pos['positionAmt'])
            if q==0:self.reconcile();return
            if int(np.sign(q))!=p['side']:self.halt('refusing to close externally reversed position')
            cid=client_id(p['id'],'EXIT',reason,attempt)
            qty=float(self.instrument.quantity(min(abs(q),float(self.instrument.max_qty))));side='SELL' if q>0 else 'BUY'
            response=self.submit(cid,'EXIT',{'side':side,'quantity':qty,'reduceOnly':True},lambda:self.v.market(self.symbol,side,qty,cid,True))
            if response.get('status') not in TERMINAL:
                try:self.v.cancel_order(self.symbol,cid)
                except ExchangeError:pass
                self.resolve(cid,'EXIT')
            time.sleep(.1)
        self.halt('reduce-only flatten not confirmed; server protection retained')
    def features(self,bars):
        key=(len(bars),int(bars.index[-1].value))
        if key!=self._features_key:
            self._feature_cache=closed_bar_features(bars,self.spec);self._features_key=key
        return self._feature_cache
    def refresh_bars(self,bootstrap=False):
        now=self.v.now_ms();step=self.spec.timeframe_minutes*60_000
        if self._bars_cache is not None and now//step==self.last_bars:return self._bars_cache
        rows=self.s.bars(self.symbol,self.interval);now=self.v.now_ms();step=self.spec.timeframe_minutes*60_000
        start=rows[-2]['open_ms'] if len(rows)>1 else int(pd.Timestamp(self.cfg.bootstrap_start_utc).timestamp()*1000)
        if self.spec.family=='ml_directional':
            gaps=[r['open_ms'] for r in rows if r.get('taker_buy_volume') is None or r.get('trades') is None]
            if gaps:start=min(start,min(gaps))
        requests=0
        while start+step<=now:
            fetched=self.v.klines(self.symbol,self.interval,start=start,end=now-1,limit=1500)
            if not fetched:break
            self.s.put_bars(self.symbol,self.interval,fetched,now)
            next_start=int(fetched[-1][0])+step
            if next_start<=start:raise Halt('market backfill made no progress')
            start=next_start;requests+=1
            if len(fetched)<1500:break
            if requests>1000:raise Halt('market bootstrap exceeded bound')
        rows=self.s.bars(self.symbol,self.interval)
        if not rows:raise Halt('no completed market bars')
        f=pd.DataFrame(rows).set_index('open_ms');f.index=pd.to_datetime(f.index,unit='ms',utc=True)
        if len(f)<max(64,self.spec.lookback+1,self.spec.trend_span*3,self.spec.atr_span*5)+2:raise Halt('insufficient indicator warm-up')
        if not np.all(np.diff(f.index.asi8//1_000_000)==step):raise Halt('historical closed-bar gap; do not trade across it')
        columns=['open','high','low','close','volume']+(['taker_buy_volume','trades'] if self.spec.family=='ml_directional' else [])
        self._bars_cache=f[columns];self.last_bars=now//step
        return self._bars_cache
    def decision_row(self,bars):
        row=self.features(bars).iloc[-1].copy()
        if self.spec.family=='ml_directional':
            from .directional import load_verified,decision
            from .refit import active_model
            artifact=active_model(self.s,self.cfg)
            model=load_verified(artifact['path'],artifact['sha256'],self.v.now_ms())
            side,atr,value=decision(model,bars,self.cfg.directional_threshold_r,2*self.fee_rate+2*self.cfg.modeled_slippage_bps/10000)
            if self.spec.direction=='long' and side<0:side=0
            if self.spec.direction=='short' and side>0:side=0
            row['signal']=side if bars.close.iloc[-1]>=self.spec.minimum_price else 0
            row['stop_fraction']=atr*self.spec.stop_atr
            return row
        if self.cfg.ml_model_path and int(row.signal)!=0:
            from .learning import predict_probability
            from .refit import active_model
            artifact=active_model(self.s,self.cfg)
            probability=predict_probability(artifact['path'],row,self.spec,self.v.now_ms(),artifact['sha256'])
            if probability<self.cfg.ml_threshold:row['signal']=0
        return row
    def consider_entry(self,bars,account,risk):
        row=self.decision_row(bars);side=int(row.signal)
        available=int(bars.index[-1].timestamp()*1000)+self.spec.timeframe_minutes*60_000
        ident=client_id(self.spec.identity,self.symbol,available)
        if not side:return
        age=(self.v.now_ms()-available)/1000
        if age<0 or age>self.cfg.max_signal_age_seconds:
            self.log('SIGNAL_SKIPPED',reason='stale_or_future',age_seconds=age);return
        if self.s.get('position') or self.s.get('halt') or risk.day_locked or risk.week_locked:return
        if risk.entries_today>=self.cfg.max_entries_per_day or self.v.now_ms()-risk.last_exit_ms<self.spec.cooldown_minutes*60000:return
        if not self.s.claim_signal(ident,self.symbol,available,{'side':side,'features':{k:float(v) for k,v in row.items()}}):return
        if any(abs(float(p.get('positionAmt',0)))>0 for p in self.v.positions()):self.halt('unexpected account exposure before entry')
        if self.v.open_orders(self.symbol):self.halt('pending exchange orders before entry')
        previous=self.v.klines(self.symbol,'1m',end=available-1,limit=1)
        if not previous or int(previous[-1][0])+60_000!=available:self.halt('missing prior-minute volume')
        book=self.v.depth(self.symbol);bid,ask=float(book['bids'][0][0]),float(book['asks'][0][0])
        if not 0<bid<=ask:raise Halt('crossed or invalid book')
        price=ask if side==1 else bid;equity=float(account['totalMarginBalance']);availablecash=float(account['availableBalance'])
        try:plan=size_plan(self.spec,risk,self.instrument,side,price,equity,availablecash,float(previous[-1][5]),float(row.stop_fraction),self.brackets,self.cfg.requested_contract_leverage,self.fee_rate,self.cfg.modeled_slippage_bps,self.cfg.participation,self.cfg.max_notional_usdt,self.cfg.liquidation_buffer_fraction)
        except ValueError as error:
            self.s.signal_state(ident,'RISK_REJECTED');self.log('SIGNAL_SKIPPED',reason=str(error));return
        expected=book_price(book,side,plan.quantity);mid=(ask+bid)/2
        if side*(expected/mid-1)*10000>self.cfg.maximum_book_slippage_bps:self.s.signal_state(ident,'BOOK_REJECTED');return
        self.v.configure_margin(self.symbol,plan.contract_leverage)
        eid=client_id(ident,'ENTRY')
        ep={'id':eid,'signal_id':ident,'side':side,'stop_fraction':float(row.stop_fraction),'entry_ms':self.v.now_ms(),'equity_before':equity,'quantity':plan.quantity,'plan':asdict(plan)}
        self.s.set('entry_plan',ep)
        self.log('ENTRY_SIZED',**asdict(plan))
        try:
            response=self.submit(eid,'ENTRY',{'side':'BUY' if side==1 else 'SELL','quantity':plan.quantity},lambda:self.v.market(self.symbol,'BUY' if side==1 else 'SELL',plan.quantity,eid))
            pos=self.v.position(self.symbol)
            if abs(float(pos['positionAmt']))>0:
                self.adopt_filled(ep,pos);self.ensure_protection()
            if response.get('status') not in TERMINAL:
                try:self.v.cancel_order(self.symbol,eid)
                except ExchangeError:pass
                response=self.resolve(eid,'ENTRY')
                if response.get('status') not in TERMINAL:self.halt('entry not terminal; new entries halted')
                pos=self.v.position(self.symbol)
                if abs(float(pos['positionAmt']))>0:self.adopt_filled(ep,pos);self.ensure_protection()
            if self.s.get('position'):
                self.s.signal_state(ident,'EXECUTED')
            else:self.s.signal_state(ident,'NO_FILL');self.s.set('entry_plan',None)
        except Halt:
            self.recover_pending();raise
    def manage_position(self,bars,account,risk):
        p=self.s.get('position')
        if not p:return
        if risk.day_locked or risk.week_locked:self.flatten('ACCOUNT_LOSS_CIRCUIT');return
        if self.v.now_ms()-p['entry_ms']>=self.spec.max_hold_hours*3600000:self.flatten('TIMEOUT');return
        row=self.decision_row(bars)
        available=int(bars.index[-1].timestamp()*1000)+self.spec.timeframe_minutes*60000
        if int(row.signal)==-p['side'] and 0<=self.v.now_ms()-available<=self.cfg.max_signal_age_seconds*1000:self.flatten('OPPOSITE_SIGNAL');return
        new=effective_stop(p['side'],p['entry'],p['quantity'],p['stop'],float(account['totalWalletBalance']),risk,self.spec)
        if self.spec.trail_r>0:
            last=self.v.klines(self.symbol,'1m',end=self.v.now_ms()-1,limit=2)
            for r in last:
                if int(r[6])>=self.v.now_ms() or int(r[0])<=p['last_trail_minute']:continue
                p['last_trail_minute']=int(r[0])
                proposed=float(r[2])-self.spec.trail_r*p['initial_distance'] if p['side']==1 else float(r[3])+self.spec.trail_r*p['initial_distance']
                new=max(new,proposed) if p['side']==1 else min(new,proposed)
        new=float(self.instrument.price(new,up=p['side']==1))
        if p['side']*(new-p['stop'])>=float(self.instrument.tick):
            old=p['stop_id'];p['stop_revision']+=1;p['stop']=new
            try:newid=self._protect(p,'STOP',new,p['stop_revision'])
            except (ExchangeError,Halt,ValueError):self.flatten('STOP_REPLACE_FAILED');raise
            p['stop_id']=newid;self.s.set('position',p)
            if old:
                try:self.v.cancel_algo(old)
                except ExchangeError as e:
                    if e.code not in (-2011,-2013):raise
        else:self.s.set('position',p)
    def step(self):
        if time.monotonic()-self.last_sync>600:
            self.v.sync_time();self.last_sync=time.monotonic()
            self.instrument=self.v.instrument(self.symbol);self.brackets=self.v.brackets(self.symbol)
            self.fee_rate=max(self.cfg.fee_bps_floor/10000,float(self.v.fee_rate(self.symbol)['takerCommissionRate']))
        self.recover_pending();self.reconcile();account=self.v.account();risk=self.risk_state(account)
        if self.v.now_ms()-self.s.get('last_journal_sync',0)>=60000:
            self.sync_fills();self.sync_income();self.s.set('last_journal_sync',self.v.now_ms())
        if self.s.get('position') and (risk.day_locked or risk.week_locked):self.flatten('ACCOUNT_LOSS_CIRCUIT');return
        if self.s.get('halt'):raise Halt(self.s.get('halt'))
        bars=self.refresh_bars()
        if self.cfg.ml_model_path:
            from .refit import maybe_refit
            maybe_refit(self.s,bars,self.spec,self.cfg,self.v.now_ms())
        self.manage_position(bars,account,risk)
        if not self.s.get('position'):self.consider_entry(bars,account,risk)
        self.s.set('heartbeat_ms',self.v.now_ms())
    def run(self):
        self.initialize();self.refresh_bars(bootstrap=True)
        while True:
            try:self.step()
            except KeyboardInterrupt:
                self.s.set('halt','operator stopped service; protection retained')
                self.log('STOPPED',note='exchange positions may remain open; protective orders retained');return
            except Halt:
                raise
            except (ExchangeError,ValueError,KeyError,TypeError,ArithmeticError) as e:
                self.log('CYCLE_FAILED',error_type=type(e).__name__,code=getattr(e,'code',None))
                self.s.set('halt','exchange/data cycle fault; reconcile and use explicit resume')
                raise Halt('runtime fault; existing venue protection remains; inspect status and positions') from e
            time.sleep(self.cfg.polling_seconds)

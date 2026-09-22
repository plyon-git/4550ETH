"""Command-line entry point. Production orders require explicit live arguments."""
from __future__ import annotations
import argparse,json,os,sys
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from .config import load_config
from .exchange import Binance,ExchangeError
from .runtime import Runtime,Halt
from .store import Store,SingleProcess
LIVE_CONFIRMATION='I_ACCEPT_REAL_ORDERS'

def parser():
    p=argparse.ArgumentParser(prog='python -m trader',description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('run','flatten','resume','resolve-intent','check','observe'):
        c=sub.add_parser(name)
        c.add_argument('--config',required=True,type=Path)
        c.add_argument('--state',type=Path,default=Path('state/trading.sqlite'))
        c.add_argument('--mode',choices=['testnet','live'],default='testnet')
        if name in ('run','flatten','resume','resolve-intent'):
            c.add_argument('--live-confirmation',default='')
            c.add_argument('--confirm-venue-eligibility',action='store_true')
        if name=='run':c.add_argument('--once',action='store_true')
        if name=='resume':c.add_argument('--confirm-reconciled',action='store_true')
        if name=='resolve-intent':
            c.add_argument('--client-id',required=True);c.add_argument('--confirm-no-execution',default='')
    for name in ('status','export'):
        c=sub.add_parser(name);c.add_argument('--state',required=True,type=Path)
        if name=='export':c.add_argument('--out',required=True,type=Path)
    c=sub.add_parser('train');c.add_argument('--config',required=True,type=Path);c.add_argument('--data',required=True,type=Path)
    c.add_argument('--out',required=True,type=Path);c.add_argument('--cutoff',required=True);c.add_argument('--horizon-bars',type=int,default=16)
    c=sub.add_parser('seed-history');c.add_argument('--config',required=True,type=Path);c.add_argument('--data',required=True,type=Path);c.add_argument('--sha256',required=True);c.add_argument('--state',required=True,type=Path)
    return p

def authorize_mutation(args):
    if args.mode=='live' and (args.live_confirmation!=LIVE_CONFIRMATION or not args.confirm_venue_eligibility):
        raise ValueError('Production mutations require --live-confirmation I_ACCEPT_REAL_ORDERS and --confirm-venue-eligibility. No order was submitted.')

def credentials(mode):
    prefix='BINANCE_LIVE' if mode=='live' else 'BINANCE_TESTNET'
    key,secret=os.environ.get(prefix+'_API_KEY',''),os.environ.get(prefix+'_API_SECRET','')
    if not key or not secret:raise ValueError(f'Set {prefix}_API_KEY and {prefix}_API_SECRET in the local environment, never in Git or chat.')
    return key,secret

def main(argv=None):
    args=parser().parse_args(argv)
    if args.command in ('status','export'):
        if not args.state.is_file():raise ValueError('state database does not exist')
        store=Store(args.state,readonly=True)
        try:
            if args.command=='export':print(store.export(args.out));return 0
            print(json.dumps({'binding':store.get('binding'),'position':store.get('position'),'risk':store.get('risk'),'halt':store.get('halt'),'heartbeat_ms':store.get('heartbeat_ms'),'pending':store.pending()},indent=2))
            return 0
        finally:store.close()
    spec,cfg,obj=load_config(args.config,training=args.command=='train')
    if args.command=='seed-history':
        from .history import seed
        print(json.dumps(seed(args.data,args.sha256,args.state,spec,cfg),indent=2));return 0
    if args.command=='train':
        import hashlib,numpy as np
        from .learning import fit_model
        from .strategy import aggregate_minutes
        cutoff=pd.Timestamp(args.cutoff)
        if cutoff.tzinfo is None:raise ValueError('cutoff must include a UTC/timezone offset')
        if cutoff>pd.Timestamp.now(tz='UTC'):raise ValueError('training cutoff cannot be future-dated')
        with np.load(args.data,allow_pickle=False) as z:raw={k:z[k] for k in ['timestamp','open','high','low','close','volume']+(['taker_buy_volume','trades'] if spec.family=='ml_directional' else [])}
        if cutoff.timestamp()*1000>int(raw['timestamp'][-1])+60000:raise ValueError('cutoff exceeds supplied data coverage')
        if spec.family=='ml_directional':
            from .directional import aggregate_rich,fit
            model=fit(aggregate_rich(raw),int(cutoff.timestamp()*1000),args.horizon_bars)
        else:model=fit_model(aggregate_minutes(raw,spec.timeframe_minutes),spec,int(cutoff.timestamp()*1000),args.horizon_bars)
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(model,indent=2)+'\n')
        print(json.dumps({'model_path':str(args.out),'sha256':hashlib.sha256(args.out.read_bytes()).hexdigest(),'samples':model['samples'],'trained_at_cutoff_ms':model['trained_at_cutoff_ms'],'not_a_performance_certification':True},indent=2));return 0
    if args.command in ('run','flatten','resume','resolve-intent'):authorize_mutation(args)
    if args.command=='resume' and not args.confirm_reconciled:raise ValueError('resume requires --confirm-reconciled; loss bases are never reset')
    key,secret=('','') if args.command=='observe' else credentials(args.mode)
    venue=Binance(args.mode,key,secret)
    try:
        if args.command=='check':
            venue.sync_time();instrument=venue.instrument(cfg.symbol);account=venue.account()
            result={'mode':args.mode,'symbol':cfg.symbol,'instrument':asdict(instrument),'account_can_trade':account.get('canTrade'),
                    'position_mode':venue.mode_info(),'multi_asset_mode':venue.multi_assets(),'leverage_brackets':venue.brackets(cfg.symbol),
                    'commission':venue.fee_rate(cfg.symbol),'positions':venue.positions(),'regular_orders':venue.open_orders(cfg.symbol),
                    'conditional_orders':venue.open_algos(cfg.symbol),'orders_submitted':False}
            print(json.dumps(result,indent=2));return 0
        with SingleProcess(args.state):
            store=Store(args.state)
            try:
                runtime=Runtime(venue,store,spec,cfg,args.mode)
                if args.command=='observe':
                    venue.sync_time();bars=runtime.refresh_bars(bootstrap=True);feat=runtime.decision_row(bars)
                    print(json.dumps({'symbol':cfg.symbol,'completed_bar_utc':bars.index[-1].isoformat(),'features':{k:float(v) for k,v in feat.items()},'orders_submitted':False},indent=2,allow_nan=False));return 0
                if args.command=='run':
                    if args.once:runtime.initialize();runtime.step()
                    else:runtime.run()
                    return 0
                if args.command=='resolve-intent':
                    if args.confirm_no_execution!='I_VERIFIED_NO_EXECUTION':raise ValueError('explicit venue-history verification required')
                    store.bind(runtime.binding);venue.sync_time()
                    row=store.get_intent(args.client_id)
                    if not row or row['state'] not in ('PLANNED','SUBMITTED','UNKNOWN','NEW'):raise ValueError('intent is not eligible for manual no-execution resolution')
                    if runtime._query(args.client_id,row['kind']) is not None:raise ValueError('venue reports an order; resolve its actual status instead')
                    if any(abs(float(p.get('positionAmt',0)))>0 for p in venue.positions()):raise ValueError('account must be flat for no-execution declaration')
                    if venue.open_orders(cfg.symbol) or venue.open_algos(cfg.symbol):raise ValueError('open regular/conditional orders remain')
                    store.update_intent(args.client_id,'ABORTED_OPERATOR_VERIFIED',{'operator_verified_no_execution':True})
                    store.event('MANUAL_INTENT_RESOLUTION',{'client_id':args.client_id,'not_an_automatic_retry':True})
                    print('Marked no-execution declaration. Intent ID retained; risk bases and entry halt unchanged.');return 0
                runtime.initialize()
                if args.command=='flatten':
                    runtime.flatten('OPERATOR_FLATTEN');runtime.reconcile();store.set('halt','operator flattened; explicit resume required');return 0
                runtime.recover_pending();runtime.reconcile()
                if store.pending():raise Halt('pending intents remain; not resuming')
                store.set('halt',None);store.event('OPERATOR_RESUME',{'risk_bases_preserved':True})
                print('Reconciled and cleared entry halt. Loss bases preserved. Run the program explicitly to continue.');return 0
            finally:store.close()
    finally:venue.close()

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted. Exchange positions and protective orders may remain; inspect the venue and use flatten explicitly.',file=sys.stderr);raise SystemExit(130)
    except (ValueError,Halt,ExchangeError,OSError) as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr);raise SystemExit(2)

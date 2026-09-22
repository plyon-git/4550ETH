"""Walk-forward order-flow/price learning. No equity resets across model refits."""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict,replace
import argparse,json
import numpy as np,pandas as pd
from trader.directional import aggregate_rich,rich_features,fit,predict
from trader.strategy import StrategySpec
from research.data import load,sha256
from research.search import PERIODS,cfg_for,fast,metrics

def forecasts(bars,begin,end,horizon,folder):
    folder.mkdir(parents=True,exist_ok=True);f=rich_features(bars);ts=bars.index.asi8//1000000;values=np.full(len(f),np.nan);receipts=[]
    cut=pd.Timestamp(begin,tz='UTC');enddate=pd.Timestamp(end,tz='UTC')
    while cut<enddate:
        stop=min(cut+pd.Timedelta(weeks=13),enddate);model=fit(bars,int(cut.timestamp()*1000),horizon)
        name=cut.strftime('%Y%m%d')+f'_h{horizon}.json';(folder/name).write_text(json.dumps(model,separators=(',',':')))
        use=(ts>=cut.timestamp()*1000)&(ts<stop.timestamp()*1000)&np.isfinite(f).all(axis=1)
        values[use]=predict(model,f[use]);receipts.append({'file':name,'sha256':sha256(folder/name),'prediction_start':cut.isoformat(),'prediction_end':stop.isoformat(),'label_maturity_ms':model['max_label_maturity_ms'],'samples':model['samples']});cut=stop
    return values,receipts

def signals(raw,bars,forecast,threshold,stop_atr,symbol):
    features=rich_features(bars);atr=features.atr_fraction.to_numpy();ix=np.searchsorted(raw['timestamp'],bars.index.asi8//1000000+59*60000)
    ok=np.isfinite(forecast)&(np.abs(forecast)>=threshold)&(np.abs(forecast)*atr>=.0021)&(bars.close.to_numpy()>=(0 if symbol=='XRPUSDT' else 1000))
    side=np.zeros(len(raw['timestamp']),np.int8);st=np.zeros(len(side));side[ix[ok]]=np.sign(forecast[ok]).astype(np.int8);st[ix]=atr*stop_atr
    return side,st

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',required=True);p.add_argument('--out',required=True);args=p.parse_args();root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    protocol={'created_at':pd.Timestamp.now(tz='UTC').isoformat(),'periods':PERIODS,'data_sha256':sha256(args.data),'horizons':[4,12,24],'threshold_r':[.15,.30,.50,.80],'risk':[.01,.02,.04],'stop_target':[[1.5,2],[2.5,4],[3,6]],'training':'1095-day rolling window; 13-week refit; 100 histogram gradient trees; 128 minimum leaf samples; no early stopping; all forward labels mature before cutoff','selection':'maximum validation CAGR with >=50 trades, no liquidation and drawdown<=50%, frozen before evaluation; reject none silently','prior_calendar_exposure':True}
    (root/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2));m,ts,raw,missing=load(args.data);bars=aggregate_rich(raw);bounds={k:tuple(np.searchsorted(ts,pd.Timestamp(t,tz='UTC').timestamp()) for t in v) for k,v in PERIODS.items()};validation=[]
    for horizon in protocol['horizons']:
        predictions,receipts=forecasts(bars,*PERIODS['validation'],horizon,root/'models')
        (root/f'validation_receipts_h{horizon}.json').write_text(json.dumps(receipts,indent=2))
        for threshold in protocol['threshold_r']:
            for stop,rr in protocol['stop_target']:
                sig,st=signals(raw,bars,predictions,threshold,stop,args.symbol)
                for risk in protocol['risk']:
                    spec=StrategySpec(family='ml_directional',timeframe_minutes=60,lookback=48,volume_multiple=0,trend_span=0,minimum_price=0 if args.symbol=='XRPUSDT' else 1000,stop_atr=stop,target_r=rr,trail_r=0,max_hold_hours=24,risk_fraction=risk,exposure_cap=5,daily_loss=.06,weekly_loss=.15)
                    cfg=cfg_for(spec,args.symbol);out=fast(m,ts,sig,st,cfg,*bounds['validation']);d=metrics(out,ts,*bounds['validation'],cfg)
                    validation.append({'horizon':horizon,'threshold_r':threshold,'spec':asdict(spec),'metrics':d})
        print(args.symbol,'trained validation horizon',horizon,flush=True)
    (root/'VALIDATION.json').write_text(json.dumps(validation,indent=2));eligible=sorted([r for r in validation if r['metrics']['trades']>=50 and r['metrics']['liquidations']==0 and r['metrics']['conservative_intrabar_drawdown']<=.5],key=lambda x:x['metrics']['cagr'],reverse=True)
    if not eligible:(root/'STATUS.json').write_text(json.dumps({'status':'NO_ELIGIBLE_MODEL'}));return
    choice=eligible[0];(root/'FROZEN.json').write_text(json.dumps(choice,indent=2));predictions,receipts=forecasts(bars,*PERIODS['evaluation'],choice['horizon'],root/'models')
    (root/'evaluation_receipts.json').write_text(json.dumps(receipts,indent=2));spec=StrategySpec(**choice['spec']);sig,st=signals(raw,bars,predictions,choice['threshold_r'],spec.stop_atr,args.symbol);cfg=cfg_for(spec,args.symbol);out=fast(m,ts,sig,st,cfg,*bounds['evaluation'],True);d=metrics(out,ts,*bounds['evaluation'],cfg)
    (root/'EVALUATION.json').write_text(json.dumps({'choice':choice,'metrics':d,'spec':asdict(spec),'symbol':args.symbol},indent=2));np.savez_compressed(root/'evaluation_predictions.npz',bar_timestamp=bars.index.asi8//1000000,forecast=predictions,signal=sig,stop=st)
    print(args.symbol,'EVALUATION',d['cagr'],d['net_return'],d['trades'],flush=True)
if __name__=='__main__':main()

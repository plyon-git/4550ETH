"""Walk-forward logistic filter: validation selection and saved causal fold weights."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from dataclasses import asdict
import numpy as np,pandas as pd
from trader.strategy import StrategySpec,aggregate_minutes,minute_signals,closed_bar_features
from trader.learning import fit_model,probabilities
from research.data import load,sha256
from research.search import cfg_for,fast,metrics,PERIODS

def predictions(raw,bars,spec,begin,end,horizon,folder):
    feat=closed_bar_features(bars,spec);bt=bars.index.asi8//1_000_000
    predictions=np.full(len(bars),np.nan);cut=pd.Timestamp(begin,tz='UTC');enddate=pd.Timestamp(end,tz='UTC');records=[]
    while cut<enddate:
        nextcut=min(cut+pd.Timedelta(weeks=13),enddate)
        rec={'cutoff_utc':cut.isoformat(),'prediction_end':nextcut.isoformat()}
        use=(bt>=cut.timestamp()*1000)&(bt<nextcut.timestamp()*1000)
        try:
            model=fit_model(bars,spec,int(cut.timestamp()*1000),horizon,1095)
            name=cut.strftime('%Y%m%d')+f'_h{horizon}.json';text=json.dumps(model,indent=2)
            (folder/name).write_text(text);rec.update(model_file=name,model_sha256=sha256(folder/name),samples=model['samples'],label_maturity=model['max_label_maturity_ms'])
            good=use & np.isfinite(feat.to_numpy()).all(axis=1)
            predictions[good]=probabilities(model,feat.loc[good])
        except ValueError as e:rec['not_trained']=str(e)
        records.append(rec);cut=nextcut
    return predictions,records

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',required=True);p.add_argument('--base-results',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True);models=root/'models';models.mkdir(exist_ok=True)
    frozen=json.loads((Path(a.base_results)/'FROZEN_SELECTION.json').read_text());s=StrategySpec(**frozen['primary']['spec'])
    protocol={'saved_before_ml_evaluation':pd.Timestamp.now(tz='UTC').isoformat(),'base_strategy':asdict(s),'periods':PERIODS,'horizons':[4,16,48],'thresholds':[.45,.50,.55,.60],'train_window_days':1095,'refit_weeks':13,'data_sha256':sha256(a.data),'selection':'Highest validation CAGR, at least 30 validation trades; no evaluation re-selection. If no candidate qualifies, no ML primary. Proxy classification labels do not establish stop/target profitability.'}
    (root/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2));m,ts,raw,missing=load(a.data);bars=aggregate_minutes(raw,s.timeframe_minutes);sig,st,feat=minute_signals(raw,s,bars);cfg=cfg_for(s,a.symbol);bounds={k:tuple(np.searchsorted(ts,pd.Timestamp(t,tz='UTC').timestamp()) for t in v) for k,v in PERIODS.items()}
    idx=np.searchsorted(raw['timestamp'],bars.index.asi8//1_000_000+(s.timeframe_minutes-1)*60000);val=[]
    for horizon in protocol['horizons']:
        probs,recs=predictions(raw,bars,s,*PERIODS['validation'],horizon,models)
        (root/f'validation_fold_receipts_h{horizon}.json').write_text(json.dumps(recs,indent=2))
        for threshold in protocol['thresholds']:
            gated=np.zeros_like(sig);allow=np.isfinite(probs)&(probs>=threshold);gated[idx[allow]]=sig[idx[allow]]
            out=fast(m,ts,gated,st,cfg,*bounds['validation'],True);d=metrics(out,ts,*bounds['validation'],cfg);val.append({'horizon':horizon,'threshold':threshold,'metrics':d})
    (root/'VALIDATION.json').write_text(json.dumps(val,indent=2));eligible=sorted([r for r in val if r['metrics']['trades']>=30],key=lambda x:x['metrics']['cagr'],reverse=True)
    if not eligible:(root/'STATUS.json').write_text(json.dumps({'status':'NO_ML_PRIMARY','reason':'too few eligible validation trades'}));return
    choice=eligible[0];(root/'FROZEN.json').write_text(json.dumps(choice,indent=2));probs,recs=predictions(raw,bars,s,*PERIODS['evaluation'],choice['horizon'],models)
    (root/'evaluation_fold_receipts.json').write_text(json.dumps(recs,indent=2));gated=np.zeros_like(sig);allow=np.isfinite(probs)&(probs>=choice['threshold']);gated[idx[allow]]=sig[idx[allow]]
    out=fast(m,ts,gated,st,cfg,*bounds['evaluation'],True);d=metrics(out,ts,*bounds['evaluation'],cfg)
    (root/'EVALUATION.json').write_text(json.dumps({'choice':choice,'spec':asdict(s),'symbol':a.symbol,'metrics':d},indent=2));np.savez_compressed(root/'evaluation_predictions.npz',timestamp=bars.index.asi8//1_000_000,probability=probs,signal=gated,stop=st)
    print(a.symbol,d['cagr'],d['net_return'],d['trades'],flush=True)
if __name__=='__main__':main()

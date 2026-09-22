"""Post-initial-evaluation execution sensitivity, validation-ranked, not fresh holdout."""
from pathlib import Path
from dataclasses import replace,asdict
import argparse,json,itertools
import numpy as np,pandas as pd
from trader.directional import aggregate_rich,rich_features,predict
from trader.strategy import StrategySpec
from research.data import load,sha256
from research.search import PERIODS,cfg_for,fast,metrics
from research.directional_search import signals

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',required=True);p.add_argument('--models',required=True);p.add_argument('--out',required=True);a=p.parse_args();root=Path(a.out);root.mkdir(parents=True,exist_ok=True);source=Path(a.models)
 choice=json.loads((source/'FROZEN.json').read_text());base=StrategySpec(**choice['spec']);m,ts,raw,_=load(a.data);bars=aggregate_rich(raw);features=rich_features(bars);bt=bars.index.asi8//1000000
 valpred=np.full(len(bars),np.nan)
 receipts=json.loads((source/f"validation_receipts_h{choice['horizon']}.json").read_text())
 for rec in receipts:
  path=source/'models'/rec['file'];assert sha256(path)==rec['sha256'];model=json.loads(path.read_text());use=(bt>=pd.Timestamp(rec['prediction_start']).timestamp()*1000)&(bt<pd.Timestamp(rec['prediction_end']).timestamp()*1000)&np.isfinite(features).all(axis=1)
  valpred[use]=predict(model,features[use])
 with np.load(source/'evaluation_predictions.npz') as z:testpred=z['forecast']
 bounds={k:tuple(np.searchsorted(ts,pd.Timestamp(t,tz='UTC').timestamp()) for t in v) for k,v in PERIODS.items()};specs=[]
 for direction,stop,target,trail,hold in itertools.product(['both','long','short'],[1.5,2.5,4.0],[2.,4.,8.],[0.,2.],[12,48]):
  for risk,day,week,exposure in [(.02,.06,.15,5),(.04,.06,.15,5),(.06,.15,.35,10),(.10,.20,.50,20)]:
   specs.append(replace(base,direction=direction,stop_atr=stop,target_r=target,trail_r=trail,max_hold_hours=hold,risk_fraction=risk,daily_loss=day,weekly_loss=week,exposure_cap=exposure))
 (root/'PROTOCOL.json').write_text(json.dumps({'created_utc':pd.Timestamp.now(tz='UTC').isoformat(),'stage':'post-initial-evaluation sensitivity; not untouched','specs':[asdict(s) for s in specs],'frozen_predictor':choice,'source_sha256':sha256(a.data)},indent=2));rows=[]
 sig,st=signals(raw,bars,valpred,choice['threshold_r'],1.,a.symbol)
 for s in specs:
  ss=sig.copy()
  if s.direction=='long':ss[ss<0]=0
  if s.direction=='short':ss[ss>0]=0
  cfg=cfg_for(s,a.symbol);out=fast(m,ts,ss,st*s.stop_atr,cfg,*bounds['validation']);d=metrics(out,ts,*bounds['validation'],cfg);rows.append({'spec':asdict(s),'id':s.identity,'metrics':d})
 (root/'VALIDATION.json').write_text(json.dumps(rows,indent=2))
 ranked=sorted([x for x in rows if x['metrics']['trades']>=50 and x['metrics']['liquidations']==0 and x['metrics']['conservative_intrabar_drawdown']<=.60],key=lambda x:x['metrics']['cagr'],reverse=True)[:12]
 (root/'FROZEN.json').write_text(json.dumps(ranked,indent=2));sig,st=signals(raw,bars,testpred,choice['threshold_r'],1.,a.symbol);results=[]
 for i,r in enumerate(ranked):
  s=StrategySpec(**r['spec']);ss=sig.copy()
  if s.direction=='long':ss[ss<0]=0
  if s.direction=='short':ss[ss>0]=0
  cfg=cfg_for(s,a.symbol);out=fast(m,ts,ss,st*s.stop_atr,cfg,*bounds['evaluation'],True);d=metrics(out,ts,*bounds['evaluation'],cfg);results.append({'id':s.identity,'primary':i==0,'spec':asdict(s),'metrics':d});print(a.symbol,i,d['cagr'],d['trades'],d['conservative_intrabar_drawdown'],flush=True)
 (root/'EVALUATION.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':main()

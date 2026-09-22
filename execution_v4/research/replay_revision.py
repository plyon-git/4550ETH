"""Recompute frozen decisions after sourced data repair, preserving prior evidence."""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,json
import numpy as np,pandas as pd
from trader.strategy import StrategySpec,aggregate_minutes,minute_signals
from research.data import load,sha256
from research.search import PERIODS,cfg_for,fast,metrics
from research.report import publish_case,audit,save

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--symbol',required=True);p.add_argument('--sources',required=True);p.add_argument('--out',required=True);a=p.parse_args();root=Path(a.out);root.mkdir(parents=True,exist_ok=True);sources=Path(a.sources);m,ts,raw,_=load(a.data);start,end=[int(np.searchsorted(ts,pd.Timestamp(x,tz='UTC').timestamp())) for x in PERIODS['evaluation']];reports=[];deltas=[]
 for name,folder in [('RULE',sources if a.symbol=='ETHUSDT' else sources/a.symbol),('TREND',sources/('TREND_'+a.symbol)),('REVERSION',sources/('REVERSION_'+a.symbol))]:
  path=folder/'EVALUATION_FINALISTS.json'
  if not path.exists():continue
  rows=json.loads(path.read_text());cache={}
  for i,row in enumerate(rows):
   spec=StrategySpec(**row['spec']);tf=spec.timeframe_minutes
   if tf not in cache:cache[tf]=aggregate_minutes(raw,tf)
   sig,st,_=minute_signals(raw,spec,cache[tf]);cfg=cfg_for(spec,a.symbol);out=fast(m,ts,sig,st,cfg,start,end,True)
   case=name+('_PRIMARY_' if i==0 else '_DIAGNOSTIC_')+spec.identity
   r=publish_case(root,case,a.symbol,spec,out,m,ts,raw,st,sig,start,end,cfg,False)
   reports.append(r);deltas.append({'case':case,'before_source_repair_net_return':row['metrics']['net_return'],'after_source_repair_net_return':r['net_return'],'source_configuration_unchanged':True})
  print(a.symbol,name,'frozen cases audited',flush=True)
 for family in ['ML','DIRECTIONAL']:
  folder=sources/(family+'_'+a.symbol);path=folder/'EVALUATION.json'
  if not path.exists():continue
  doc=json.loads(path.read_text());spec=StrategySpec(**doc['spec'])
  with np.load(folder/'evaluation_predictions.npz',allow_pickle=False) as z:sig=z['signal'];st=z['stop']
  cfg=cfg_for(spec,a.symbol);out=fast(m,ts,sig,st,cfg,start,end,True);case=family+'_PRIMARY';r=publish_case(root,case,a.symbol,spec,out,m,ts,raw,st,sig,start,end,cfg,family=='DIRECTIONAL');reports.append(r)
  if family=='DIRECTIONAL':
   from research.directional_search import signals
   from trader.directional import aggregate_rich
   ext=sources/('DIRECTIONAL_EXTENSION_'+a.symbol)/'EVALUATION.json'
   if ext.exists():
    with np.load(folder/'evaluation_predictions.npz',allow_pickle=False) as z:forecast=z['forecast']
    bars=aggregate_rich(raw);base_sig,base_st=signals(raw,bars,forecast,doc['choice']['threshold_r'],1.,a.symbol)
    for i,row in enumerate(json.loads(ext.read_text())):
     sp=StrategySpec(**row['spec']);sg=base_sig.copy()
     if sp.direction=='long':sg[sg<0]=0
     if sp.direction=='short':sg[sg>0]=0
     stp=base_st*sp.stop_atr;c=cfg_for(sp,a.symbol);o=fast(m,ts,sg,stp,c,start,end,True)
     reports.append(publish_case(root,'DIRECTIONAL_EXTENSION_'+str(i)+'_'+sp.identity,a.symbol,sp,o,m,ts,raw,stp,sg,start,end,c,False))
   stresses=[]
   for label,c in [('double_cost',replace(cfg,fee_bps=10,slippage_bps=4)),('two_minute_delay',replace(cfg,entry_delay_bars=2)),('five_minute_delay',replace(cfg,entry_delay_bars=5)),('100k_equity',replace(cfg,initial_equity=100000)),('1m_equity',replace(cfg,initial_equity=1000000))]:
    o=fast(m,ts,sig,st,c,start,end,True);check=audit(o,m,ts,start,end,c,sig);d=metrics(o,ts,start,end,c);d.pop('gates',None);d.pop('passes_historical_average_target',None);stresses.append({'scenario':label,'metrics':d,'audit':check})
   save(root/'DIRECTIONAL_STRESSES.json',stresses)
 save(root/'INDEX.json',reports);save(root/'SOURCE_REPAIR_IMPACT.json',deltas)
 save(root/'DATA_IDENTITY.json',{'sha256':sha256(a.data),'rows':len(ts),'first_ms':int(raw['timestamp'][0]),'end_ms_exclusive':int(raw['timestamp'][-1])+60000,'missing_mark_rows':int((~np.isfinite(raw['mark_open'])).sum()),'mark_gap_model':'previous observed close; separately sourced 15-minute bounds when present; otherwise explicit +/-5% sensitivity envelope; no invented observed mark values'})
 print(a.symbol,'all cases',len(reports),'all requested target passes',sum(r['all_requested_targets_pass'] for r in reports),flush=True)
if __name__=='__main__':main()

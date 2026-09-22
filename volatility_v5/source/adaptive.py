"""Prior26-week band selection; fixed scoring; continuous account across refits."""
from dataclasses import asdict,replace
import json,argparse,time
import numpy as np,pandas as pd
from bands import Spec,make_context,signals
from research import ROOT,PERIODS,load,config,run,bounds,basic,export,write

def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',required=True);sym=p.parse_args().symbol;folder=ROOT/'results'/sym/'ADAPTIVE';folder.mkdir(parents=True,exist_ok=True);frozen=json.loads((folder.parent/'FROZEN.json').read_text());dev=json.loads((folder.parent/'DEVELOPMENT.json').read_text());lookup={r['id']:Spec(**r['spec']) for r in dev};universe=[lookup[k] for k in frozen['adaptive_universe']]
 start,end=[pd.Timestamp(t,tz='UTC') for t in PERIODS['five_years']];folds=[];cut=start
 while cut<end:stop=min(cut+pd.Timedelta(weeks=13),end);folds.append((cut-pd.Timedelta(weeks=26),cut,stop));cut=stop
 write(folder/'PROTOCOL.json',{'written_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'selection':'Fixed development shortlist. Select every13weeks using previous26weeks only; score annualized log growth minus1.5drawdown; >=15past trades,no liquidation,positive net,DD<=35%. Cash if none. No equity reset; existing positions retain exits.','sources':sorted(set(s.source for s in universe)),'candidate_specs':[asdict(s) for s in universe],'training_risk_fraction':.01,'execution_risk_fraction':.01,'known_prior_research_exposure':True})
 m,ts,raw,_=load(sym);ctx=make_context(raw,ROOT/'iv_data'/(sym.replace('USDT','')+'_1D.csv'));cfg=config(sym,.01);a,b=bounds(ts,PERIODS['five_years']);n=len(ts);groups=['ALL_SOURCES','ACTUAL_IV_ONLY'] if sym!='XRPUSDT' else ['RV_PROXY_ONLY']
 wins={g:[None]*len(folds) for g in groups};scores={g:np.full(len(folds),-np.inf) for g in groups};streams={g:(np.zeros(n,np.int8),np.zeros(n),np.full(n,np.nan)) for g in groups};trainrows=[];t0=time.time()
 for j,spec in enumerate(universe):
  sig,st,tar=signals(ctx,spec)
  for k,(train,cut,stop) in enumerate(folds):
   ta,tb=bounds(ts,[train,cut]);testa,testb=bounds(ts,[cut,stop]);out=run(m,ts,sig,st,tar,cfg,ta,tb);d=basic(out,ts,ta,tb,cfg);rec={'candidate':spec.id,'fold':k,'training_start':train.isoformat(),'training_end_exclusive':cut.isoformat(),'cagr':d['cagr'],'score':d['selection_score'],'trades':d['trades'],'net_return':d['net_return'],'drawdown':d['conservative_intrabar_drawdown'],'liquidations':d['liquidations']};trainrows.append(rec)
   if not(d['trades']>=15 and d['liquidations']==0 and d['net_return']>0 and d['conservative_intrabar_drawdown']<=.35):continue
   for g in groups:
    if g=='ACTUAL_IV_ONLY' and not spec.source.startswith('iv'):continue
    if d['selection_score']>scores[g][k]:
     scores[g][k]=d['selection_score'];wins[g][k]={'spec':asdict(spec),'id':spec.id,**rec,'prediction_start':cut.isoformat(),'prediction_end_exclusive':stop.isoformat()}
     # A bar available exactly at cutoff remains assigned to the previous fold.
     for outarr,inarr in zip(streams[g],(sig,st,tar)):outarr[testa:testb]=inarr[testa:testb]
  if (j+1)%32==0:print(sym,'adaptive candidates',j+1,len(universe),round(time.time()-t0,1),flush=True)
 write(folder/'TRAINING_SCORES.json',trainrows);records=[]
 for g in groups:
  receipt=[]
  for k,(train,cut,stop) in enumerate(folds):receipt.append(wins[g][k] or {'fold':k,'training_start':train.isoformat(),'training_end_exclusive':cut.isoformat(),'prediction_start':cut.isoformat(),'prediction_end_exclusive':stop.isoformat(),'selection':'CASH'})
  write(folder/(g+'_FROZEN_FOLDS.json'),receipt);sig,st,tar=streams[g];np.savez_compressed(folder/(g+'_SIGNALS.npz'),signal=sig,stop=st,target=tar)
  out=run(m,ts,sig,st,tar,cfg,a,b,True);d=export(folder,g,sym,None,out,m,ts,raw,a,b,cfg,sig,st,tar,full=True,selection='causal_26week_training_13week_selection; exposed_research_calendar');records.append(d);print(sym,g,d['cagr'],d['trades'],d['annual_returns'],flush=True)
  aa,bb=bounds(ts,PERIODS['250_weeks']);oo=run(m,ts,sig,st,tar,cfg,aa,bb,True);export(folder,g+'_250W',sym,None,oo,m,ts,raw,aa,bb,cfg,sig,st,tar)
  for label,c in [('NO_FEES_NO_SLIP',replace(cfg,fee_bps=0,slippage_bps=0)),('RISK_0.5PCT',replace(cfg,risk_fraction=.005)),('RISK_2PCT',replace(cfg,risk_fraction=.02))]:
   oo=run(m,ts,sig,st,tar,c,a,b,True);records.append(export(folder,g+'_'+label,sym,None,oo,m,ts,raw,a,b,c,sig,st,tar,selection='fixed_sensitivity_not_reselected'))
 write(folder/'INDEX.json',records)
if __name__=='__main__':main()

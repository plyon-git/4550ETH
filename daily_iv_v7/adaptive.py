"""Additional causal weekly selector of daily IV-wall policies, after fixed-run review.
It never reads the current day's outcome when selecting a policy. Not a new holdout.
"""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,json
import numpy as np,pandas as pd
from core import *
from research import grid,save,summarize,publish,PERIODS,ROOT

def choose_policies(bank_daily,days,start,end,train_start,lookback=126,min_history=90):
    choices=np.full(len(days),-1,np.int64);journal=[];prior=-1;next_update=start
    for day in range(start,end):
        if day==start or day>=next_update:
            left=max(train_start,day-lookback);n=day-left
            if n<min_history:raise ValueError('insufficient matured training days')
            past=bank_daily[:,left-train_start:day-train_start]
            if not np.isfinite(past).all():raise ValueError('missing bank daily returns')
            cumulative=np.cumsum(np.log1p(past),axis=1)
            cash=np.exp(np.column_stack([np.zeros(len(past)),cumulative]))
            dd=np.max(1-cash/np.maximum.accumulate(cash,axis=1),axis=1)
            scores=cumulative[:,-1]-.5*dd
            prior=int(np.argmax(scores));next_update=day+7
            journal.append({'decision_day':str(days[day]),'latest_outcome_day':str(days[day-1]),
                            'sample_start_day':str(days[left]),'matured_training_days':n,
                            'selected_index':prior,'selection_score':float(scores[prior])})
        choices[day]=prior
    return choices,journal

def run(symbol,data_root):
    folder=ROOT/'results'/symbol/'adaptive_research';folder.mkdir(exist_ok=True)
    bank=[replace(p,risk_fraction=.01) for p in grid() if p.entry_minute==2 and not p.rule.startswith('wall_')]
    save(folder/'PROTOCOL.json',{'created_at_utc':str(pd.Timestamp.now(tz='UTC')),'status':'extension specified after static test results; same already-researched calendar',
       'bank':[asdict(p) for p in bank],'selection':'every seven UTC days select maximum prior126day log gain minus0.5 maximum daily drawdown; first sample minimum90days; only prior completed daily trades',
       'risk_fraction':.01,'account_exposure_cap':5,'bank_selection_accounts':'separate simulated 10,000-USDT accounts from 2021-05-01; not combined, actual selected account never resets'})
    iv,receipt=verify_iv(ROOT/'context/iv_data',symbol.replace('USDT',''));ts,m,missing=load_market(data_root/symbol/'aligned_repaired.npz',symbol)
    d=daily_inputs(ts,m,iv);d.attrs['grid']=(.001,.1,100.) if symbol=='BTCUSDT' else (.001,.01,20.)
    index=d.index;train=int(index.get_loc('2021-05-01'));start=int(index.get_loc('2021-09-01'));end=len(index)
    perf=np.empty((len(bank),end-train));signals=np.zeros((len(bank),len(index)),np.int8)
    stops=np.empty((len(bank),len(index)));targets=np.empty_like(stops);entries=np.empty((len(bank),len(index)),np.int64)
    for i,p in enumerate(bank):
        sg,sl,tp,en=decision_arrays(d,p);out=run_policy(m,missing,d,p,train,end)
        perf[i]=out[0][1:]/out[0][:-1]-1;signals[i]=sg;stops[i]=sl;targets[i]=tp;entries[i]=en
    selected,journal=choose_policies(perf,index,start,end,train)
    cols=np.arange(start,end);idx=selected[start:end];sg=np.zeros(len(index),np.int8);sl=np.full(len(index),np.nan);tp=sl.copy();en=np.full(len(index),-1,np.int64)
    sg[cols]=signals[idx,cols];sl[cols]=stops[idx,cols];tp[cols]=targets[idx,cols];en[cols]=entries[idx,cols]
    for row in journal:row['policy']=asdict(bank[row['selected_index']]);row['policy_id']=bank[row['selected_index']].id
    save(folder/'SELECTION_JOURNAL.json',journal)
    np.savez_compressed(folder/'SELECTION_INPUTS.npz',bank_daily_returns=perf,selected_policy_index=selected,
        day_timestamp_ms=index.asi8//1000000,side=sg,stop=sl,target=tp,entry_minute=en)
    representative=Policy(risk_fraction=.01);step,tick,minnot=d.attrs['grid']
    out=evaluate(m,missing,sg,sl,tp,en,start,end,.01,5.,.0005,.0002,step,tick,minnot)
    metrics=publish(ROOT/'results'/symbol/'ADAPTIVE_DAILY',out,ts,m,missing,d,representative,start,end,
          'ADAPTIVE_DAILY',symbol,decisions_override=(sg,sl,tp,en))
    save(folder/'METRICS.json',metrics)
    print(symbol,'adaptive',metrics['trades'],metrics['net_return'],metrics['cagr'],flush=True)
    return metrics

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True,type=Path);args=p.parse_args()
    for s in ('BTCUSDT','ETHUSDT'):run(s,args.data_root)

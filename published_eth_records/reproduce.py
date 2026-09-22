"""Reproduce Parrish Lyon's two frozen ETH records. No network or broker calls.

Run from anywhere: python reproduce.py --case both --verify-models --retrain
Derived files go to reproduced/, never over the frozen records or models.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'shared'/'frozen_v8'
sys.path.insert(0,str(SOURCE))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')

def safe(base,name):
    p=(base/name).resolve()
    if not p.is_relative_to(base.resolve()):raise ValueError('Unsafe manifest path')
    return p

def verify_snapshot():
    manifest=json.loads((ROOT/'SOURCE_MAP.json').read_text())
    for rel,rec in manifest['files'].items():
        path=safe(ROOT,rel)
        if not path.is_file() or path.stat().st_size!=rec['bytes'] or sha(path)!=rec['sha256']:
            raise ValueError('Frozen source, model, configuration or record changed: '+rel)
    return len(manifest['files'])

def assemble_data(explicit=None):
    meta=json.loads((ROOT/'shared/data/DATA_MANIFEST.json').read_text())
    if explicit:
        p=Path(explicit)
        if sha(p)!=meta['sha256']:raise ValueError('Historical input identity mismatch')
        return p
    p=ROOT/'shared/data/aligned_repaired.npz'
    if p.exists():
        if sha(p)!=meta['sha256']:raise ValueError('Existing reconstructed input identity mismatch')
        return p
    tmp=p.with_suffix('.npz.partial')
    try:
        with tmp.open('xb') as dest:
            for part in meta['parts']:
                f=safe(ROOT/'shared/data',part['filename'])
                if f.stat().st_size!=part['bytes'] or sha(f)!=part['sha256']:raise ValueError('Data part missing/changed')
                with f.open('rb') as src:
                    for block in iter(lambda:src.read(1<<20),b''):dest.write(block)
            dest.flush();os.fsync(dest.fileno())
        if tmp.stat().st_size!=meta['bytes'] or sha(tmp)!=meta['sha256']:raise ValueError('Assembled data does not match original')
        os.replace(tmp,p)
    except BaseException:
        if tmp.exists():tmp.unlink()
        raise
    return p

def model_check(ts,m,stored,retrain=False):
    from core import levels,bars,verify_iv,DAY
    from learning import predictors,predict,fit,label_outcomes
    learning=SOURCE/'results/ETHUSDT/LEARNING'
    iv,_=verify_iv(SOURCE/'context/iv_data','ETH')
    daily=levels(ts,m,iv)
    candidates,features,policy,definitions=predictors(ts,m,daily,{tf:bars(ts,m,tf) for tf in (15,60)})
    for new,old in [(candidates,stored['candidates']),(features,stored['features'])]:
        np.testing.assert_allclose(new,old,rtol=1e-12,atol=1e-12)
    np.testing.assert_array_equal(policy,stored['policy'])
    from dataclasses import asdict
    if [asdict(x) for x in definitions]!=json.loads((learning/'CANDIDATE_POLICIES.json').read_text()):
        raise ValueError('Candidate policy definitions differ from frozen selection')
    entry_ms=candidates[:,0]*60000+ts[0]
    maturity=entry_ms+72*3600000+60000
    labels=label_outcomes(m,candidates,.01) if retrain else None
    forecast=np.full(len(candidates),np.nan);checks=[]
    for rec in json.loads((learning/'MODEL_RECEIPTS.json').read_text()):
        cutoff=int(pd.Timestamp(rec['cutoff']).timestamp()*1000)
        end=int(pd.Timestamp(rec['end']).timestamp()*1000)
        p=learning/'models'/rec['model_file']
        if sha(p)!=rec['sha256']:raise ValueError('Model SHA mismatch')
        model=json.loads(p.read_text())
        if model['training_cutoff_ms']!=cutoff or model['last_label_maturity_ms']>cutoff:
            raise ValueError('Model training-time causality violation')
        use=(entry_ms>=cutoff)&(entry_ms<end)
        values=predict(model,features[use]);forecast[use]=values
        check={'file':rec['model_file'],'sha256':rec['sha256'],'training_cutoff_ms':cutoff,
               'last_label_maturity_ms':model['last_label_maturity_ms'],'forecast_rows':int(use.sum()),
               'training_rows':model['candidate_samples'],'prediction_parity':True,'retrained':retrain}
        if retrain:
            new=fit(features,labels,cutoff,maturity,entry_ms)
            np.testing.assert_allclose(predict(new,features[use]),values,rtol=1e-10,atol=1e-10)
            if new['candidate_samples']!=model['candidate_samples']:raise ValueError('Training-sample identity mismatch')
            dump(ROOT/'reproduced/models'/rec['model_file'],new)
        checks.append(check)
    np.testing.assert_allclose(forecast,stored['prediction'],rtol=1e-10,atol=1e-10,equal_nan=True)
    if len(checks)!=21:raise ValueError('Expected exactly 21 ETH model folds')
    return {'passed':True,'candidate_rows':len(candidates),'feature_columns':features.shape[1],
            'model_folds':checks,'all_features_and_predictions_match':True,'all_folds_retrained':retrain}

def export_minute_equity(folder,out,m,missing,ts,signals,a,b,cfg):
    # Independent cash-flow reconstruction, retaining all 2,629,440 evaluation minutes.
    n=b-a;delta=np.zeros(n);quantity=np.zeros(n);entry=np.zeros(n)
    for row in out[1]:
        ei,xi,side=map(int,row[:3]);qty,en,ex,sl,tp,ef,xf,fp,gross,net,*_=row[3:]
        left,right=ei-a,xi-a;q=side*qty
        funding=q*m[ei:xi+1,5]*m[ei:xi+1,9];funding=funding.copy();funding[0]=max(0,funding[0])
        delta[left:right+1]-=funding;delta[left]-=ef;delta[right]+=gross-xf
        quantity[left:right]=q;entry[left:right]=en
    cash=cfg.initial+np.cumsum(delta)
    close=cash+quantity*(m[a:b,8]-entry)
    np.testing.assert_allclose(np.r_[cfg.initial,close[1439::1440]],out[0],rtol=1e-10,atol=1e-6)
    opening=np.r_[cfg.initial,cash[:-1]]+np.r_[0.,quantity[:-1]]*(m[a:b,5]-np.r_[0.,entry[:-1]])
    pd.DataFrame({'minute_open_epoch_ms':ts[a:b], 'equity_open_before_funding':opening,
        'equity_close':close,'cash_close':cash,'signed_quantity_close':quantity,
        'mark_missing_in_original':missing[a:b]}).to_csv(folder/'MINUTE_EQUITY.csv.gz',index=False,
        compression={'method':'gzip','mtime':0},chunksize=100000)
    return {'rows':n,'end_of_day_equity_matches':True,'derived_from_frozen_fills_not_new_backtest':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['both','564.37','261.62'],default='both')
    p.add_argument('--data',type=Path,help='Optional exact NPZ instead of auto-assembling committed chunks')
    p.add_argument('--verify-models',action='store_true')
    p.add_argument('--retrain',action='store_true',help='Refit every original fold and check numerical forecasts; no retuning')
    p.add_argument('--minute-equity',action='store_true')
    args=p.parse_args()
    count=verify_snapshot();data=assemble_data(args.data)
    from core import Execution,LEDGER,load_market,run
    from learning import choose
    from research import boundary,PERIODS
    from report import publish
    ts,m,missing=load_market(data,'ETHUSDT')
    with np.load(SOURCE/'results/ETHUSDT/LEARNING/PREDICTIONS.npz',allow_pickle=False) as z:
        stored={k:z[k] for k in z.files}
    evidence={'frozen_files_verified':count,'data_sha256':sha(data),'authenticated_orders_submitted':False,
              'not_a_new_strategy_selection':True,'cases':[]}
    if args.verify_models or args.retrain:
        evidence['models']=model_check(ts,m,stored,args.retrain)
    signals,chosen=choose(stored['candidates'],stored['prediction'],.5)
    a,b=boundary(ts,PERIODS['five_years'])
    if b-a!=1826*1440:raise ValueError('Evaluation interval changed')
    config=json.loads((ROOT/'CATALOG.json').read_text())
    for case in config['cases']:
        if args.case!='both' and case['id']!=args.case:continue
        folder=ROOT/case['folder'];params=json.loads((folder/'PARAMETERS.json').read_text())
        cfg=Execution(**params['actual_execution']);cfg.validate()
        out=run(m,missing,signals,a,b,cfg,'ETHUSDT',True)
        ref=pd.read_csv(folder/'EVERY_TRADE_UTC.csv');eq=pd.read_csv(folder/'DAILY_EQUITY.csv')
        np.testing.assert_allclose(out[1],ref[list(LEDGER)].to_numpy(),rtol=1e-11,atol=1e-7)
        np.testing.assert_allclose(out[0],eq.equity,rtol=1e-11,atol=1e-7)
        destination=ROOT/'reproduced'/case['folder']
        met=publish(destination,out,m,missing,ts,signals,a,b,cfg,'ETHUSDT',{'frozen_record':case['id'],
                    'source_commit':config['source_commit'],'new_parameter_search':False})
        expected=json.loads((folder/'METRICS.json').read_text())
        for key,value in expected.items():
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                np.testing.assert_allclose(met[key],value,rtol=1e-10,atol=1e-8,err_msg=key)
        np.testing.assert_allclose(met['annual_returns'],expected['annual_returns'],rtol=1e-10,atol=1e-10)
        summary={'id':case['id'],'trade_rows_matched':len(ref),'daily_boundaries_matched':len(eq),
                 'all_raw_ledger_columns_matched':True,'all_numeric_metrics_matched':True,
                 'net_return':met['net_return'],'cagr':met['cagr'],'win_rate':met['win_rate'],
                 'audit':json.loads((destination/'INDEPENDENT_AUDIT.json').read_text())}
        if args.minute_equity:summary['minute_equity']=export_minute_equity(destination,out,m,missing,ts,signals,a,b,cfg)
        evidence['cases'].append(summary)
        print(case['id'],'MATCHED',len(ref),'trades;',met['net_return']*100,'percent cumulative',flush=True)
    dump(ROOT/'reproduced/VERIFICATION.json',evidence)
    print(json.dumps({'verified_cases':len(evidence['cases']),'models_checked':'models' in evidence,
                     'trading_orders_submitted':False},indent=2),flush=True)
if __name__=='__main__':main()

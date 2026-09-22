"""Walk-forward entry-quality regression, mature 72h labels, numerical JSON.
Post-fixed-policy research extension, not a globally untouched holdout.
"""
from pathlib import Path
from dataclasses import asdict,replace
import hashlib,itertools,json,argparse
import numpy as np,pandas as pd
from numba import njit
from core import *
from research import save,boundary,PERIODS
from report import publish
ROOT=Path(__file__).resolve().parent
FEATURES=['side','family','horizon','timeframe','wall_multiple','stop_fraction','day_z','week_z','IV_daily_sigma','IV_change3',
 'IV_RV20_ratio','known_trend','body_atr','range_atr','close_location','return1bar','return4bar','return16bar','return48bar','distance_ema48','stop_over_day_sigma','target_over_week_sigma','sin_hour','cos_hour']

def predictors(ts,m,d,caches):
    specs=[Spec(family=f,horizon=h,multiplier=k,timeframe=tf,buffer=.10,regime='all',scale='latest') for f,h,k,tf in
      itertools.product(['reject','break','retest'],['daily','weekly','confluence'],[.75,1.5],[15,60])]
    candidates=[];features=[];policy=[]
    rv=np.log(d.close).diff().rolling(20).std().shift(1).to_numpy()
    for idx,sp in enumerate(specs):
        b=caches[sp.timeframe];s=make_signals(ts,m,d,b,sp)
        rows=(s[:,0].astype(int)//sp.timeframe)-1;di=s[:,3].astype(int);side=s[:,1];cl=b.close.to_numpy()[rows]
        op=b.open.to_numpy()[rows];hi=b.high.to_numpy()[rows];lo=b.low.to_numpy()[rows];sigma=d.sigma.to_numpy()[di]
        dist=side*(cl-s[:,2]);atr=cl*sigma
        ret={n:np.log(b.close/b.close.shift(n)).to_numpy()[rows] for n in [1,4,16,48]}
        hour=(s[:,0]*60%86400)/3600
        x=np.column_stack([side,np.full(len(s),['reject','break','retest'].index(sp.family)),np.full(len(s),['daily','weekly','confluence'].index(sp.horizon)),
             np.full(len(s),sp.timeframe),np.full(len(s),sp.multiplier),dist/cl,
             np.log(cl/d.reference.to_numpy()[di])/sigma,np.log(cl/d.week_reference.to_numpy()[di])/(d.week_sigma.to_numpy()[di]*np.sqrt(7)),
             sigma,d.iv_change.to_numpy()[di],sigma/rv[di],d.trend.to_numpy()[di],(cl-op)/atr,(hi-lo)/atr,(cl-lo)/(hi-lo+1e-12),
             ret[1],ret[4],ret[16],ret[48],(cl/b.close.ewm(span=48,adjust=False).mean().to_numpy()[rows]-1)/sigma,
             dist/atr,5*dist/(cl*d.week_sigma.to_numpy()[di]*np.sqrt(7)),np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)])
        ok=np.isfinite(x).all(axis=1);candidates.append(s[ok]);features.append(x[ok]);policy.append(np.full(ok.sum(),idx))
    s=np.concatenate(candidates);x=np.concatenate(features);pol=np.concatenate(policy);order=np.argsort(s[:,0],kind='stable')
    return s[order],x[order],pol[order],specs

@njit(cache=True)
def label_outcomes(m,candidates,tick):
    y=np.full(len(candidates),np.nan);fee=.0005;slip=.0002
    for j in range(len(candidates)):
        i=int(candidates[j,0]);side=int(candidates[j,1]);end=i+4320
        if end>=len(m):continue
        sl=candidates[j,2];sl=(np.ceil(sl/tick) if side==1 else np.floor(sl/tick))*tick
        en=m[i,0]*(1+side*slip);en=(np.ceil(en/tick) if side==1 else np.floor(en/tick))*tick
        dist=side*(en-sl)
        if dist<=0:continue
        target=en+side*5*dist;target=(np.ceil(target/tick) if side==1 else np.floor(target/tick))*tick
        if target<=0:continue
        fund=0.;ex=en
        for k in range(i,end+1):
            cost=side*m[k,5]*m[k,9];fund+=max(0,cost) if k==i else cost
            op=m[k,0]
            if side*(op-sl)<=0:ex=op;break
            if side*(op-target)>=0:ex=op;break
            if k==end:ex=op;break
            if (side==1 and m[k,2]<=sl) or (side==-1 and m[k,1]>=sl):ex=sl;break
            if (side==1 and m[k,1]>=target) or (side==-1 and m[k,2]<=target):ex=target;break
        ex*=1-side*slip;ex=(np.floor(ex/tick) if side==1 else np.ceil(ex/tick))*tick
        y[j]=(side*(ex-en)-fee*(ex+en)-fund)/dist
    return y

def predict(model,x):
    if model['features']!=FEATURES:raise ValueError('feature identity mismatch')
    if not np.isfinite(x).all():raise ValueError('nonfinite features')
    out=np.full(len(x),model['baseline'])
    for t in model['trees']:
        nodes=np.zeros(len(x),int);active=np.ones(len(x),bool);leaf=np.array(t['is_leaf'],bool);val=np.array(t['value']);ft=np.array(t['feature_idx']);th=np.array(t['num_threshold']);left=np.array(t['left']);right=np.array(t['right'])
        for _ in range(64):
            ids=np.flatnonzero(active)
            if not len(ids):break
            cur=nodes[ids];done=leaf[cur];out[ids[done]]+=val[cur[done]];active[ids[done]]=False;ids=ids[~done];cur=nodes[ids]
            nodes[ids]=np.where(x[ids,ft[cur]]<=th[cur],left[cur],right[cur])
        else:raise ValueError('invalid tree depth')
    return out

def fit(x,y,cutoff,label_maturity,entry_ms):
    from sklearn.ensemble import HistGradientBoostingRegressor
    use=(label_maturity<=cutoff)&(entry_ms>=cutoff-730*DAY)&np.isfinite(y)
    if use.sum()<500:raise ValueError('fewer than 500 mature overlapping candidate labels')
    model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,max_depth=4,min_samples_leaf=100,l2_regularization=30,learning_rate=.05,early_stopping=False,random_state=20260922)
    yy=y[use].clip(-5,5);model.fit(x[use],yy)
    trees=[]
    for stage in model._predictors:
        n=stage[0].nodes
        if n['is_categorical'].any():raise ValueError('categorical export not implemented')
        trees.append({k:n[k].tolist() for k in ['value','feature_idx','num_threshold','left','right','is_leaf']})
    doc=dict(schema=1,features=FEATURES,baseline=float(model._baseline_prediction.ravel()[0]),trees=trees,
         training_cutoff_ms=int(cutoff),last_label_maturity_ms=int(label_maturity[use].max()),candidate_samples=int(use.sum()),
         distinct_entry_timestamps=int(np.unique(entry_ms[use]).size),train_window_days=730,hold_label_hours=72,
         label='net per-unit 5R/stop/72h outcome divided by initial distance, includes 5bps+2bps costs and historical funding; label computation ignores account risk circuits and margin, final account replay does not',
         proxy_label_clipping=[-5,5],regressor_parameters=model.get_params(),overlapping_labels=True)
    np.testing.assert_allclose(predict(doc,x[use][::29]),model.predict(x[use][::29]),rtol=1e-10,atol=1e-10)
    return doc

def choose(s,prob,threshold):
    ix=np.flatnonzero(np.isfinite(prob)&(prob>=threshold))
    order=np.lexsort((ix,-prob[ix],s[ix,0]));ix=ix[order]
    first=np.r_[True,np.diff(s[ix,0])!=0] if len(ix) else np.zeros(0,bool)
    chosen=ix[first];return s[chosen],chosen

def main():
    p=argparse.ArgumentParser();p.add_argument('--symbol',required=True);p.add_argument('--data',required=True);a=p.parse_args();sym=a.symbol
    root=ROOT/'results'/sym/'LEARNING';root.mkdir(parents=True,exist_ok=True);(root/'models').mkdir(exist_ok=True)
    save(root/'PROTOCOL.json',dict(created=str(pd.Timestamp.now(tz='UTC')),predeclared_primary_threshold=.25,primary_risk=.01,
         threshold_diagnostics=[0,.25,.5,1.],risks=[.01,.02,.04],refit_weeks=13,label_horizon_hours=72,
         post_fixed_policy_extension=True,notes='Not globally untouched. All parameters fixed for this extension before its full replay; no in-test threshold selection. 36 overlapping candidate policies pooled; sample count is not independent observations.'))
    ts,m,missing=load_market(a.data,sym);iv,rec=verify_iv(ROOT/'context/iv_data',sym[:3]);d=levels(ts,m,iv);cache={tf:bars(ts,m,tf) for tf in [15,60]}
    s,x,pol,specs=predictors(ts,m,d,cache);entry_ms=s[:,0]*60000+ts[0];maturity=entry_ms+72*3600000+60000
    y=label_outcomes(m,s,.01 if sym=='ETHUSDT' else .1);prob=np.full(len(s),np.nan);receipts=[]
    cut=pd.Timestamp('2021-09-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC')
    while cut<end:
        nxt=min(cut+pd.Timedelta(weeks=13),end);now=int(cut.timestamp()*1000)
        rec=dict(cutoff=str(cut),end=str(nxt))
        try:
            model=fit(x,y,now,maturity,entry_ms);use=(entry_ms>=now)&(entry_ms<int(nxt.timestamp()*1000));prob[use]=predict(model,x[use])
            name=cut.strftime('%Y%m%d')+'.json';save(root/'models'/name,model)
            rec.update(model_file=name,sha256=hashlib.sha256((root/'models'/name).read_bytes()).hexdigest(),max_label_maturity=model['last_label_maturity_ms'],samples=model['candidate_samples'])
        except ValueError as e:rec['not_trained']=str(e)
        receipts.append(rec);cut=nxt
    save(root/'MODEL_RECEIPTS.json',receipts);save(root/'CANDIDATE_POLICIES.json',[asdict(v) for v in specs]);np.savez_compressed(root/'PREDICTIONS.npz',candidates=s,features=x,policy=pol,prediction=prob)
    rows=[];left,right=boundary(ts,PERIODS['five_years'])
    for threshold in [0,.25,.5,1.]:
        sg,chosen=choose(s,prob,threshold)
        for risk in [.01,.02,.04]:
            cfg=replace(Execution(),risk=risk)
            label=f'threshold{threshold}_risk{risk}';primary=threshold==.25 and risk==.01
            if primary:label='PRIMARY'
            out=run(m,missing,sg,left,right,cfg,sym,True)
            met=publish(root/label,out,m,missing,ts,sg,left,right,cfg,sym,dict(model='HGB net-R filter',threshold=threshold,risk=risk,primary=primary))
            rows.append(dict(case=label,primary=primary,**met));print(sym,'ML',label,met['cagr'],met['mean_annual'],met['trades'],flush=True)
            if primary:
                aa,bb=boundary(ts,PERIODS['test']);out2=run(m,missing,sg,aa,bb,cfg,sym,True)
                publish(root/'PRIMARY_3YEAR_TEST',out2,m,missing,ts,sg,aa,bb,cfg,sym,dict(primary=True,separate_account=True))
                for hours in [24,48]:
                    cc=replace(cfg,max_hold_hours=hours);oo=run(m,missing,sg,left,right,cc,sym,True);publish(root/f'PRIMARY_HOLD{hours}',oo,m,missing,ts,sg,left,right,cc,sym,dict(primary=True,hold_sensitivity=True))
    save(root/'SUMMARY.json',rows)
if __name__=='__main__':main()

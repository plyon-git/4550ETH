"""Causal learned rejection filter with matured net-R labels and portable JSON trees."""
from dataclasses import asdict
import argparse,json
import numpy as np,pandas as pd
from numba import njit
from sklearn.ensemble import HistGradientBoostingRegressor
from bands import Spec,make_context,signals,feature_base,source_hash
from research import ROOT,load,config,run,bounds,export,write,PERIODS

@njit(cache=True)
def label_trades(m,idx,side,st,target):
 n=len(idx);y=np.full(n,np.nan);mature=np.full(n,-1,np.int64)
 for k in range(n):
  i=idx[k]+1
  if i+1440>=len(m):continue
  s=side[k];entry=m[i,0]*(1+s*.0002);stop=entry*(1-s*st[k]);tar=target[k]
  if s*(tar-entry)<=0:continue
  fee=entry*.0005;fund=0.;exitprice=0.;last=min(i+1440,len(m)-1)
  for j in range(i,last+1):
   f=s*m[j,5]*m[j,9]
   if j==i:f=max(f,0.)
   fund+=f;hitstop=m[j,2]<=stop if s==1 else m[j,1]>=stop;hittarget=m[j,1]>=tar if s==1 else m[j,2]<=tar
   if hitstop:raw=min(m[j,0],stop) if s==1 else max(m[j,0],stop);exitprice=raw*(1-s*.0002);last=j;break
   if hittarget:exitprice=tar*(1-s*.0002);last=j;break
   if j==last:exitprice=m[j,3]*(1-s*.0002)
  y[k]=(s*(exitprice-entry)-fee-exitprice*.0005-fund)/(entry*st[k]);mature[k]=last+1
 return y,mature

def features(raw,ctx,spec):
 bars=ctx['bars'][spec.timeframe];z=feature_base(ctx,spec);c=bars.close;v=bars.volume;f=pd.DataFrame(index=bars.index);sig,st,tar,levels=signals(ctx,spec,True)
 sums=pd.DataFrame({k:raw[k] for k in ['taker_buy_volume','trades']},index=pd.to_datetime(raw['timestamp'],unit='ms',utc=True)).resample(f'{spec.timeframe}min',origin='epoch').sum().reindex(bars.index)
 for horizon in [1,3,12,48]:f['return_sigma_'+str(horizon)]=np.log(c/c.shift(horizon))/z['sigma']
 f['vol_ratio']=v/v.rolling(48,min_periods=48).mean();f['flow']=2*sums.taker_buy_volume/v.replace(0,np.nan)-1;f['flow_ema12']=f.flow.ewm(span=12,adjust=False).mean();f['flow_ema48']=f.flow.ewm(span=48,adjust=False).mean()
 f['range_sigma']=(bars.high-bars.low)/c/z['sigma'];f['body_sigma']=(c/bars.open-1)/z['sigma'];f['close_location']=(c-bars.low)/(bars.high-bars.low+1e-12);f['session_return_sigma']=np.log(c/z['anchor'])/z['sigma'];f['sigma']=z['sigma'];f['trend']=z['trend'];f['efficiency']=z['eff']
 rv=ctx['sessions'][spec.anchor_hour].reindex(z['sid']).rv20.to_numpy();f['iv_rv_ratio']=z['sigma']/rv;f['session_sin']=np.sin(2*np.pi*(bars.timestamp-z['session_ms'])/86400000);f['session_cos']=np.cos(2*np.pi*(bars.timestamp-z['session_ms'])/86400000);f['weekday']=bars.index.dayofweek;f['side']=sig[z['ix']]
 return f,sig,st,tar,levels,z['ix']

def export_model(model,cols,meta):
 trees=[]
 for stage in model._predictors:
  nodes=stage[0].nodes;assert not nodes['is_categorical'].any();trees.append({k:nodes[k].tolist() for k in ['value','feature_idx','num_threshold','left','right','is_leaf','missing_go_to_left']})
 return {'schema':1,'type':'wall_meta_expected_net_R','features':cols,'baseline':float(model._baseline_prediction.ravel()[0]),'trees':trees,**meta}

def portable_predict(doc,X):
 x=np.asarray(X,float);out=np.full(len(x),doc['baseline'])
 if not np.isfinite(x).all():raise ValueError('finite model inputs required')
 for t in doc['trees']:
  node=np.zeros(len(x),np.int64);active=np.ones(len(x),bool)
  for depth in range(20):
   rows=np.flatnonzero(active)
   if not len(rows):break
   nn=node[rows];leaves=np.array(t['is_leaf'],bool)[nn];out[rows[leaves]]+=np.array(t['value'])[nn[leaves]];active[rows[leaves]]=False;rows=rows[~leaves];nn=node[rows]
   if len(rows):node[rows]=np.where(x[rows,np.array(t['feature_idx'],int)[nn]]<=np.array(t['num_threshold'])[nn],np.array(t['left'],int)[nn],np.array(t['right'],int)[nn])
  else:raise ValueError('unexpected tree depth')
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',required=True,choices=['ETHUSDT','BTCUSDT']);sym=p.parse_args().symbol;root=ROOT/'results'/sym/'META';root.mkdir(parents=True,exist_ok=True);(root/'models').mkdir(exist_ok=True);spec=Spec('iv5',5,8,.75,'rejection',.5,'pivot','all')
 write(root/'PROTOCOL.json',{'created_utc':pd.Timestamp.now(tz='UTC').isoformat(),'spec':asdict(spec),'training_days':730,'refit_weeks':13,'embargo_hours':24,'minimum_training_labels':100,'thresholds_expected_net_R':[0.,.15,.35],'training':'100 histogram boosting trees,depth3,minleaf30,l2=20,learning_rate.04,no early stopping,seed20260922; modeled net-R labels include fees/slippage/funding','selection':'Three fixed diagnostics, no performance-selected primary. Prior research calendar exposed.','prior_calendar_exposure':True})
 m,ts,raw,_=load(sym);ctx=make_context(raw,ROOT/'iv_data'/(sym.replace('USDT','')+'_1D.csv'));f,sig,st,tar,levels,barix=features(raw,ctx,spec);eligible=(f.side!=0)&np.isfinite(f).all(axis=1);X=f[eligible];idx=barix[eligible.to_numpy()];side=sig[idx];labels,mature=label_trades(m,idx,side,st[idx],tar[idx]);times=ts[idx]+60
 cut=pd.Timestamp('2021-09-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC');forecasts=np.full(len(idx),np.nan);receipts=[]
 while cut<end:
  stop=min(cut+pd.Timedelta(weeks=13),end);epoch=int(cut.timestamp());maturity_sec=np.where(mature>=0,ts[np.maximum(mature,0)],np.iinfo(np.int64).max);use=(times>=epoch-730*86400)&(maturity_sec<=epoch-86400)&np.isfinite(labels);test=(times>epoch)&(times<=stop.timestamp());rec={'cutoff_utc':cut.isoformat(),'prediction_end_utc':stop.isoformat(),'training_labels':int(use.sum()),'training_end_exclusive':cut.isoformat()}
  if use.sum()>=100:
   model=HistGradientBoostingRegressor(max_iter=100,max_depth=3,max_leaf_nodes=8,min_samples_leaf=30,l2_regularization=20,learning_rate=.04,early_stopping=False,random_state=20260922);model.fit(X.to_numpy()[use],np.clip(labels[use],-3,6));pred=model.predict(X.to_numpy()[test]);forecasts[test]=pred;rec.update(max_label_maturity_utc=pd.Timestamp(int(maturity_sec[use].max()),unit='s',tz='UTC').isoformat(),model_file=cut.strftime('%Y%m%d')+'.json')
   doc=export_model(model,list(X.columns),{'max_label_maturity_epoch':int(maturity_sec[use].max()),'cutoff_epoch':epoch,'samples':int(use.sum()),'trained_only_on_matured_labels':True});np.testing.assert_allclose(portable_predict(doc,X.to_numpy()[test]),pred,rtol=1e-10,atol=1e-10);write(root/'models'/rec['model_file'],doc);rec['sha256']=source_hash(root/'models'/rec['model_file'])
  else:rec['status']='CASH_INSUFFICIENT_MATURED_LABELS'
  receipts.append(rec);cut=stop
 write(root/'FOLD_RECEIPTS.json',receipts);pd.DataFrame({'signal_available_utc':pd.to_datetime(times,unit='s',utc=True),'signal_index':idx,'side':side,'expected_net_R':forecasts,'research_label_net_R':labels,'label_maturity_epoch':np.where(mature>=0,ts[np.maximum(mature,0)],-1)}).to_csv(root/'PREDICTIONS_AND_LABELS.csv',index=False)
 outrows=[];a,b=bounds(ts,PERIODS['five_years']);cfg=config(sym,.01)
 for threshold in [0.,.15,.35]:
  gate=np.zeros(len(ts),np.int8);mask=np.isfinite(forecasts)&(forecasts>threshold);gate[idx[mask]]=side[mask];name='THRESHOLD_'+str(threshold);o=run(m,ts,gate,st,tar,cfg,a,b,True);d=export(root,name,sym,spec,o,m,ts,raw,a,b,cfg,gate,st,tar,selection='fixed_threshold_diagnostic; no performance-selected primary');outrows.append(d);print(sym,name,d['cagr'],d['trades'],d['annual_returns'],flush=True)
 write(root/'INDEX.json',outrows)
if __name__=='__main__':main()

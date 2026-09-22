"""Causal session bands. DVOL is actual options IV; RV/range are explicit proxies.
Project-specific implementation: Parrish Lyon. No proprietary indicator reproduced.
"""
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd

@dataclass(frozen=True)
class Spec:
 source:str='rv20'
 timeframe:int=5
 anchor_hour:int=8
 width:float=1.0
 family:str='rejection'
 stop_sigma:float=.5
 target:str='pivot'
 regime:str='all'
 direction:str='both'
 @property
 def id(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()[:16]

def source_hash(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def make_context(raw,iv_path=None):
 ts=raw['timestamp'];index=pd.to_datetime(ts,unit='ms',utc=True)
 frame=pd.DataFrame({k:raw[k] for k in ('open','high','low','close','volume')},index=index);bars={}
 for tf in (5,15):
  groups=frame.resample(f'{tf}min',origin='epoch');b=groups.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
  b=b.loc[groups.close.count()==tf].copy();b['timestamp']=b.index.asi8//1000000;bars[tf]=b
 iv=None
 if iv_path is not None and Path(iv_path).exists():
  iv=pd.read_csv(iv_path).sort_values('timestamp')
  if iv.timestamp.duplicated().any() or not iv['close'].between(1,1000).all():raise ValueError('invalid actual IV data')
  iv['available_ms']=iv.timestamp.astype(np.int64)+86400000+60000
  for days in (1,5,20):iv[f'iv{days}']=np.sqrt((iv.close/100).pow(2).rolling(days,min_periods=days).mean())/np.sqrt(365.)
 sessions={}
 for hour in (0,8):
  sid=(ts-hour*3600000)//86400000;f=frame.copy();f['session']=sid
  d=f.groupby('session').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'});log=np.log(d.close);r=log.diff()
  d['rv20']=r.rolling(20,min_periods=20).std(ddof=1).shift(1)
  d['range20']=((d.high-d.low)/d.open).rolling(20,min_periods=20).mean().shift(1)/1.59576912
  d['range_up']=np.log(d.high/d.open).rolling(20,min_periods=20).mean().shift(1)
  d['range_dn']=np.log(d.open/d.low).rolling(20,min_periods=20).mean().shift(1)
  d['efficiency']=(log.diff(20).abs()/r.abs().rolling(20,min_periods=20).sum()).shift(1)
  d['trend']=np.sign((d.close-d.close.ewm(span=50,adjust=False).mean()).shift(1))
  d['session_start_ms']=d.index.to_numpy()*86400000+hour*3600000
  d.loc[d.session_start_ms<ts[0],['rv20','range20','range_up','range_dn','efficiency','trend']]=np.nan
  # The current session does not need to finish: every volatility/trend feature uses earlier sessions.
  if iv is not None:
   joined=pd.merge_asof(d[['session_start_ms']].reset_index(drop=True),iv[['available_ms','timestamp','iv1','iv5','iv20']],left_on='session_start_ms',right_on='available_ms',direction='backward',tolerance=2*86400000)
   for k in ('iv1','iv5','iv20'):d[k]=joined[k].to_numpy()
   d['iv_available_ms']=joined.available_ms.to_numpy();d['iv_candle_ms']=joined.timestamp.to_numpy()
  sessions[hour]=d
 return {'bars':bars,'sessions':sessions,'timestamp':ts,'cache':{}}

def feature_base(context,spec):
 key=(spec.timeframe,spec.anchor_hour,spec.source)
 if key in context['cache']:return context['cache'][key]
 b=context['bars'][spec.timeframe];sids=(b.timestamp.to_numpy()-spec.anchor_hour*3600000)//86400000;d=context['sessions'][spec.anchor_hour].reindex(sids)
 if spec.source not in d.columns:raise ValueError('requested IV unavailable; no silent proxy fallback')
 z={'open':b.open.to_numpy(),'high':b.high.to_numpy(),'low':b.low.to_numpy(),'close':b.close.to_numpy(),'anchor':d.open.to_numpy(float),'sigma':d[spec.source].to_numpy(float),'trend':d.trend.to_numpy(),'eff':d.efficiency.to_numpy(),'sid':sids,'ix':np.searchsorted(context['timestamp'],b.timestamp.to_numpy()+(spec.timeframe-1)*60000),'source_available_ms':d.iv_available_ms.to_numpy() if spec.source.startswith('iv') else d.session_start_ms.to_numpy()-1,'session_ms':d.session_start_ms.to_numpy()}
 context['cache'][key]=z;return z

def signals(context,spec,return_levels=False):
 z=feature_base(context,spec);a=z['anchor'];vol=z['sigma'];c=z['close'];op=z['open'];hi=z['high'];lo=z['low'];up=a*np.exp(spec.width*vol);dn=a*np.exp(-spec.width*vol)
 prev=np.r_[np.nan,c[:-1]];same=z['sid']==np.r_[-10**10,z['sid'][:-1]]
 if spec.family=='rejection':buy=(lo<=dn)&(c>dn)&(c>op)&(c<a);sell=(hi>=up)&(c<up)&(c<op)&(c>a)
 elif spec.family=='breakout':buy=(c>up)&(prev<=up)&(c>op)&same;sell=(c<dn)&(prev>=dn)&(c<op)&same
 elif spec.family=='retest':
  prev2=np.r_[np.nan,np.nan,c[:-2]];buy=(prev>up)&(prev2>up)&(lo<=up)&(c>up)&(c>op)&same;sell=(prev<dn)&(prev2<dn)&(hi>=dn)&(c<dn)&(c<op)&same
 else:raise ValueError('invalid family')
 ok=np.isfinite(vol)&(vol>0)&(vol<.3)&same
 if spec.regime=='range':ok &=z['eff']<.30
 elif spec.regime=='trend':ok &=z['eff']>=.30
 elif spec.regime=='aligned':buy &=z['trend']>0;sell &=z['trend']<0
 elif spec.regime!='all':raise ValueError('bad regime')
 if spec.direction=='long':sell[:]=False
 elif spec.direction=='short':buy[:]=False
 side=np.where(buy&ok,1,np.where(sell&ok,-1,0)).astype(np.int8);sf=spec.stop_sigma*vol
 target=a.copy() if spec.target=='pivot' else c*(1+side*sf*float(spec.target.rstrip('R')))
 eligible=(side!=0)&(side*(target-c)>c*.0005)&(target>0);side[~eligible]=0
 n=len(context['timestamp']);sig=np.zeros(n,np.int8);stop=np.zeros(n);targets=np.full(n,np.nan);ix=z['ix'];sig[ix]=side;stop[ix]=sf;targets[ix]=target
 if return_levels:
  mask=side!=0
  levels=pd.DataFrame({'signal_index':ix[mask],'signal_available_ms':context['timestamp'][ix[mask]]+60000,'session_start_ms':z['session_ms'][mask],'volatility_available_ms':z['source_available_ms'][mask],'source':spec.source,'sigma_daily':vol[mask],'anchor':a[mask],'upper':up[mask],'lower':dn[mask],'signal_close':c[mask],'side':side[mask],'stop_fraction':sf[mask],'absolute_target':target[mask]})
  return sig,stop,targets,levels
 return sig,stop,targets

"""Fixed-grid search: 2 selection years, purged 3-year test, full 5y replay.
No exchange orders. Prior project exposure prevents a globally untouched claim.
"""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,itertools,json,time,sys
import numpy as np,pandas as pd
from core import *
ROOT=Path(__file__).resolve().parent
PERIODS={'development':['2021-09-01','2022-09-01'],'validation':['2022-09-01','2023-08-28'],
         'test':['2023-09-01','2026-09-01'],'five_years':['2021-09-01','2026-09-01'],
         '250weeks':['2021-11-15','2026-08-31']}
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')
def boundary(ts,period):return tuple(int(np.searchsorted(ts,pd.Timestamp(x,tz='UTC').timestamp()*1000)) for x in period)
def getstats(result,ts,a,b):return stats(result,int(ts[a]),int(ts[b-1])+60000)
def rank(d):return np.log(max(1e-12,1+d['net_return']))-1.0*d['conservative_drawdown']
def grid():
    return [Spec(family=fa,horizon=ho,multiplier=mult,timeframe=tf,buffer=buf,regime=reg,scale=sc)
        for fa,ho,mult,tf,buf,reg,sc in itertools.product(['reject','break','retest'],['daily','weekly','confluence'],
         [.75,1.25,1.75,2.25],[15,60],[.05,.20],['all','trend','long','iv_falling'],['latest','mean5','historical'])]

def main():
    p=argparse.ArgumentParser();p.add_argument('--symbol',required=True,choices=['ETHUSDT','BTCUSDT']);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--limit',type=int,default=0);args=p.parse_args();sym=args.symbol;out=ROOT/'results'/sym;out.mkdir(parents=True,exist_ok=True)
    specs=grid();specs=specs[:args.limit] if args.limit else specs
    save(out/'PROTOCOL.json',dict(created_utc=str(pd.Timestamp.now(tz='UTC')),periods=PERIODS,specs=[asdict(s) for s in specs],
       execution=asdict(Execution()),risk_grid=[.005,.01,.02,.04],selection='Max log validation growth minus intrabar drawdown; >=25 validation trades, no modeled liquidation, drawdown<=60%. Development selects 3 per family/horizon with >=30 trades. Full five-year result includes both selection years. Separate purged three-year test reported. No daily quota; previous 1000-trade preference remains a reported flag, not forced entries.',
       target='CAGR>45%; separately arithmetic mean of five anniversary returns>45%; report all five years and consistency, no guaranteed outcome',
       notes=['30x nominal with explicitly reserved additional isolated collateral; separate no-topup test.','5R is fixed initial price target, not guaranteed realized average payoff.','No current/future session high/low can change previously frozen levels.','Same previously researched market calendar; not globally untouched.']))
    ts,m,missing=load_market(args.data,sym);iv,rec=verify_iv(ROOT/'context'/'iv_data',sym[:3]);d=levels(ts,m,iv)
    save(out/'DATA_IDENTITY.json',dict(source_file_sha256=HASHES[sym],iv=rec,missing_mark_count=int(missing.sum()),
        missing_mark_model='Prior observed close plus previously sourced 15-minute bounds; otherwise explicitly hypothetical +/-5% mark envelope. Not exact historical liquidation prices.'))
    d.to_csv(out/'DAILY_WEEKLY_LEVEL_INPUTS.csv',index_label='day_utc')
    cache={tf:bars(ts,m,tf) for tf in [15,60]};bounds={k:boundary(ts,v) for k,v in PERIODS.items()}
    start=time.time();rows=[]
    for i,s in enumerate(specs):
        sg=make_signals(ts,m,d,cache[s.timeframe],s);a,b=bounds['development'];r=run(m,missing,sg,a,b,Execution(),sym)
        met=getstats(r,ts,a,b);rows.append(dict(id=s.id,spec=asdict(s),metrics=met,score=float(rank(met))))
        if (i+1)%100==0:print(sym,'development',i+1,len(specs),'seconds',round(time.time()-start,1),flush=True)
    save(out/'DEVELOPMENT.json',rows)
    candidates=[]
    for family,horizon in itertools.product(['reject','break','retest'],['daily','weekly','confluence']):
        eligible=[x for x in rows if x['spec']['family']==family and x['spec']['horizon']==horizon and x['metrics']['trades']>=30 and x['metrics']['liquidations']==0 and x['metrics']['conservative_drawdown']<=.7]
        candidates.extend(sorted(eligible,key=lambda x:x['score'],reverse=True)[:3])
    if not candidates:raise ValueError('No development candidate meets predeclared eligibility; review development log')
    val=[]
    for row in candidates:
        s=Spec(**row['spec']);sg=make_signals(ts,m,d,cache[s.timeframe],s)
        for risk in [.005,.01,.02,.04]:
            cfg=replace(Execution(),risk=risk);a,b=bounds['validation'];r=run(m,missing,sg,a,b,cfg,sym);met=getstats(r,ts,a,b)
            val.append(dict(id=s.id+f'_risk{risk}',spec=asdict(s),execution=asdict(cfg),metrics=met,score=float(rank(met))))
    save(out/'VALIDATION.json',val)
    eligible=sorted([x for x in val if x['metrics']['trades']>=25 and x['metrics']['liquidations']==0 and x['metrics']['conservative_drawdown']<=.6],key=lambda x:x['score'],reverse=True)
    if not eligible:raise ValueError('No validation candidate')
    primary=eligible[0];finalists=[primary]
    for family,horizon in itertools.product(['reject','break','retest'],['daily','weekly','confluence']):
        g=[x for x in eligible if x['spec']['family']==family and x['spec']['horizon']==horizon]
        if g and g[0]['id']!=primary['id']:finalists.append(g[0])
    save(out/'FROZEN_SELECTION.json',dict(primary=primary,finalists=finalists,frozen_at_utc=str(pd.Timestamp.now(tz='UTC'))))
    summary=[]
    from report import publish
    for i,row in enumerate(finalists):
        s=Spec(**row['spec']);cfg=Execution(**row['execution']);sg=make_signals(ts,m,d,cache[s.timeframe],s)
        for period in ['five_years','test']:
            a,b=bounds[period];r=run(m,missing,sg,a,b,cfg,sym,True)
            name=('PRIMARY' if i==0 else 'DIAGNOSTIC_'+row['id'])+'_'+period
            met=publish(out/name,r,m,missing,ts,sg,a,b,cfg,sym,row)
            summary.append(dict(symbol=sym,case=name,primary=i==0,period=period,**met))
            print('RESULT',sym,name,met['cagr'],met['mean_annual'],met['trades'],flush=True)
        if i==0:
            stress=[]
            for label,c in [('hold24h',replace(cfg,max_hold_hours=24)),('hold48h',replace(cfg,max_hold_hours=48)),('30x_initial_margin_only',replace(cfg,funded_collateral=False)),
               ('zero_cost',replace(cfg,fee_bps=0,slip_bps=0)),('double_cost',replace(cfg,fee_bps=10,slip_bps=4)),('delay_2_minutes',replace(cfg,delay_minutes=2)),
               ('risk1pct',replace(cfg,risk=.01)),('risk4pct',replace(cfg,risk=.04)),('initial100k',replace(cfg,initial=100000))]:
                a,b=bounds['five_years'];r=run(m,missing,sg,a,b,c,sym,True)
                met=publish(out/('STRESS_'+label),r,m,missing,ts,sg,a,b,c,sym,row)
                stress.append(dict(scenario=label,**met))
            save(out/'STRESSES.json',stress)
            a,b=bounds['250weeks'];r=run(m,missing,sg,a,b,cfg,sym,True);publish(out/'PRIMARY_250weeks',r,m,missing,ts,sg,a,b,cfg,sym,row)
            pd.DataFrame(sg,columns=['entry_index','side','absolute_stop','origin_day_index','upper_wall','lower_wall','daily_iv_available_ms','weekly_iv_available_ms']).to_csv(out/'PRIMARY_CANDIDATES.csv.gz',index=False)
    save(out/'SUMMARY.json',summary)
    print('DONE',sym,'elapsed',time.time()-start,flush=True)
if __name__=='__main__':
    from input_v7 import HASHES
    main()

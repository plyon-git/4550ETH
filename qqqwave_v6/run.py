"""Reproduce a transparent QQQWave-inspired forecast and executable path test.
No broker calls. Never treats a horizon-touch frequency as a trade win rate.
"""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,hashlib,itertools,json,sys,time
import numpy as np,pandas as pd
from bootstrap_engine import build
build()
from source.surface import SurfaceSpec,build_surface,event_evidence,event_summary
from source.inputs import load_crypto,daily_crypto,daily_equity,digest
from source.trades import TradeSpec,bar_view,signals,make_config,simulate
from source.reporting import metrics,publish,dump

ROOT=Path(__file__).resolve().parent
PERIODS={'development':('2020-09-01','2021-06-01'),'validation':('2021-06-01','2021-08-25'),
'evaluation':('2021-09-01','2026-09-01'),'250weeks':('2021-11-15','2026-08-31')}
HASHES={'ETHUSDT':'b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d',
'BTCUSDT':'2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3',
'XRPUSDT':'43678daef70287657734cf3eb6b6915ffa5df0b24d90d289d8892ee1d5f70859'}

def specs(symbol):
    surfaces=[SurfaceSpec(horizon=h,matching=match,scale=scale) for h,match,scale in itertools.product([1,5],['all','weekday'],['percent','realized']+(['iv_scaled'] if symbol!='XRPUSDT' else []))]
    trades=[]
    for q,buffer,target,regime in itertools.product([.50,.75,.90],[.25,.5],['pivot','opposite_mean'],['all','aligned']):
        trades.append(TradeSpec('fade',q,buffer,target,regime))
    for q,buffer,rr in itertools.product([.50,.75],[.25,.5],['2','4']):trades.append(TradeSpec('break',q,buffer,rr,'aligned'))
    for target in ['near97','mean_low']:trades.append(TradeSpec('toward_low',.90,.5,target,'all'))
    return surfaces,trades

def score(d):return np.log(max(1e-12,1+d['net_return']))-1.5*d['conservative_intrabar_drawdown']

def run_crypto(symbol,data_root,context):
    root=ROOT/'results'/symbol;root.mkdir(parents=True,exist_ok=True)
    path=data_root/symbol/'aligned_repaired.npz'
    if digest(path)!=HASHES[symbol]:raise ValueError('Unexpected source data '+symbol)
    surfaces,trades=specs(symbol)
    dump(root/'PROTOCOL.json',{'created_utc':str(pd.Timestamp.now(tz='UTC')),'source_sha256':HASHES[symbol],
         'periods':PERIODS,'surfaces':[asdict(s) for s in surfaces],'trade_grid':[asdict(t) for t in trades],
         'selection':'Per surface, top two development configurations with >=20 trades and no liquidation. Tune risk 0.5/1/2% on validation. Primary maximizes log growth minus 1.5 drawdown with >=10 validation trades and no liquidation. Family/source finalists are diagnostics. Freeze before test P&L.',
         'risk_grid':[.005,.01,.02], 'hypothesis_status':'new implementation inspired by screenshot; not vendor replication; prior calendar exposure',
         'user_target':'65% CAGR and separately arithmetic mean annual >65%, >=200 trades; report all five annual periods and 250 weeks separately',
         'execution':'next minute after completed 5-minute bar; absolute stop/target/expiry fixed before entry; account circuits retained; no live orders'})
    m,ts,raw,missing=load_crypto(path)
    iv=context/'iv_data'/(symbol.replace('USDT','')+'_1D.csv')
    daily=daily_crypto(raw,iv if iv.exists() else None);daily.to_csv(root/'daily_inputs.csv',index_label='origin_utc')
    bar=bar_view(raw);bounds={k:tuple(int(np.searchsorted(ts,pd.Timestamp(t,tz='UTC').timestamp())) for t in v) for k,v in PERIODS.items()}
    levels={s.id:build_surface(daily,s) for s in surfaces};dev=[];validation=[];t0=time.time()
    event_records=[]
    for ss in surfaces:
        surface=levels[ss.id]
        if ss.horizon==5:
            ev=event_evidence(daily,surface,*[pd.Timestamp(t,tz='UTC') for t in PERIODS['evaluation']])
            ev.to_csv(root/f'events_{ss.id}.csv',index=False)
            event_records.append({'surface_id':ss.id,'spec':asdict(ss),**event_summary(ev)})
            surface.to_csv(root/f'levels_{ss.id}.csv',index_label='origin_utc')
        local=[]
        for tr in trades:
            sg=signals(raw,daily,surface,bar,tr);cfg=make_config(symbol)
            out=simulate(m,ts,sg,cfg,*bounds['development'],False)
            d=metrics(out,ts,*bounds['development'],cfg)[0]
            row={'surface':asdict(ss),'trade':asdict(tr),'id':ss.id+'_'+tr.id,'metrics':d,'score':float(score(d))}
            local.append(row);dev.append(row)
        eligible=[r for r in local if r['metrics']['trades']>=20 and r['metrics']['liquidations']==0]
        best=sorted(eligible,key=lambda r:r['score'],reverse=True)[:2]
        for row in best:
            tr=TradeSpec(**row['trade']);sg=signals(raw,daily,surface,bar,tr)
            for risk in [.005,.01,.02]:
                cfg=make_config(symbol,risk);out=simulate(m,ts,sg,cfg,*bounds['validation'],False)
                d=metrics(out,ts,*bounds['validation'],cfg)[0]
                validation.append({'surface':asdict(ss),'trade':asdict(tr),'risk':risk,'id':row['id']+f'_risk{risk}','metrics':d,'score':float(score(d))})
        print(symbol,'surface',ss.id,asdict(ss),'elapsed',round(time.time()-t0,1),flush=True)
    dump(root/'EVENT_SUMMARIES.json',event_records);dump(root/'DEVELOPMENT.json',dev);dump(root/'VALIDATION.json',validation)
    candidates=sorted([r for r in validation if r['metrics']['trades']>=10 and r['metrics']['liquidations']==0],key=lambda r:r['score'],reverse=True)
    if not candidates:raise ValueError('No eligible validation configuration')
    chosen=candidates[0];finalists=[chosen]
    for family,scale in itertools.product(['fade','break','toward_low'],['percent','realized','iv_scaled']):
        group=[r for r in candidates if r['trade']['family']==family and r['surface']['scale']==scale]
        if group and group[0]['id']!=chosen['id']:finalists.append(group[0])
    for target in ['near97','mean_low']:
        ss=SurfaceSpec();tr=TradeSpec('toward_low',.9,.5,target)
        finalists.append({'surface':asdict(ss),'trade':asdict(tr),'risk':.01,'id':'SCREENSHOT_TOUCH_'+target,
                          'predeclared_diagnostic':True})
    dump(root/'FROZEN.json',{'frozen_at':str(pd.Timestamp.now(tz='UTC')),'primary':chosen,'finalists':finalists,
                            'primary_validation_positive':chosen['metrics']['net_return']>0,'prior_calendar_exposure':True})
    allrows=[];checks=[]
    for i,row in enumerate(finalists):
        ss=SurfaceSpec(**row['surface']);tr=TradeSpec(**row['trade']);cfg=make_config(symbol,row['risk'])
        surf=levels.get(ss.id)
        if surf is None:surf=build_surface(daily,ss)
        sg=signals(raw,daily,surf,bar,tr);out=simulate(m,ts,sg,cfg,*bounds['evaluation'],True)
        label=('PRIMARY_' if i==0 else 'DIAGNOSTIC_')+row['id']
        d,check=publish(root/label,out,m,ts,*bounds['evaluation'],cfg,sg,{**row,'simulation':asdict(cfg)},False)
        allrows.append({'symbol':symbol,'case':label,'primary':i==0,**d});checks.append(check)
        print('EVAL',symbol,label,d['net_return'],d['cagr'],d['trades'],flush=True)
        if i==0:
            stress=[]
            scenarios=[('no_fee_no_slippage',replace(cfg,fee_bps=0,slippage_bps=0)),
                       ('user5usd_round_trip',replace(cfg,fee_bps=(5/(3.6*2748.67)*10000)/2)),
                       ('user5usd_one_way',replace(cfg,fee_bps=(5/(3.6*2748.67)*10000))),
                       ('double_cost',replace(cfg,fee_bps=10,slippage_bps=4)),
                       ('delay2m',replace(cfg,entry_delay_bars=2)),('delay5m',replace(cfg,entry_delay_bars=5))]
            for name,cc in scenarios:
                oo=simulate(m,ts,sg,cc,*bounds['evaluation'],True)
                dd,ck=publish(root/('STRESS_'+name),oo,m,ts,*bounds['evaluation'],cc,sg,{**row,'simulation':asdict(cc),'cost_scenario':name},False)
                stress.append({'scenario':name,**dd});checks.append(ck)
            cc=cfg;oo=simulate(m,ts,sg,cc,*bounds['250weeks'],True)
            dd,ck=publish(root/'PRIMARY_250_WEEKS',oo,m,ts,*bounds['250weeks'],cc,sg,row,False)
            dump(root/'STRESSES.json',stress);dump(root/'PRIMARY_250W.json',dd);checks.append(ck)
    dump(root/'INDEX.json',allrows);dump(root/'ALL_AUDITS.json',checks)
    dump(root/'DATA_IDENTITY.json',{'source_sha256':HASHES[symbol],'raw_rows':len(ts),'missing_marks':len(missing),
        'missing_mark_model':'previous close plus sourced 15-minute bounds or explicit +/-5% sensitivity envelope; not observed values',
        'iv_data_sha256':digest(iv) if iv.exists() else None})
    return allrows

def run_equity_events(symbol,context):
    root=ROOT/'results'/symbol;root.mkdir(parents=True,exist_ok=True)
    p=context/'equity_data'/(symbol+'_daily.csv');daily=daily_equity(p);daily.to_csv(root/'daily_inputs.csv',index_label='origin_utc')
    records=[]
    for matching,scale in itertools.product(['weekday','all'],['percent','realized']):
        s=SurfaceSpec(matching=matching,scale=scale);surface=build_surface(daily,s)
        ev=event_evidence(daily,surface,*[pd.Timestamp(t,tz='UTC') for t in PERIODS['evaluation']])
        ev.to_csv(root/f'events_{s.id}.csv',index=False);surface.to_csv(root/f'levels_{s.id}.csv',index_label='origin_utc')
        records.append({'spec':asdict(s),'surface_id':s.id,**event_summary(ev)})
    dump(root/'EVENT_SUMMARIES.json',records);dump(root/'DATA_IDENTITY.json',{'daily_source_sha256':digest(p),
         'no_equity_order_execution_backtest':True,'not_ES_or_intraday_data':True})

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--context-root',type=Path,required=True)
    p.add_argument('--symbols',nargs='+',default=['ETHUSDT','BTCUSDT','XRPUSDT','QQQ','SPY']);a=p.parse_args()
    for s in a.symbols:
        if s in ('QQQ','SPY'):run_equity_events(s,a.context_root)
        else:run_crypto(s,a.data_root,a.context_root)
    rows=[]
    for f in (ROOT/'results').glob('*/INDEX.json'):rows.extend(json.loads(f.read_text()))
    dump(ROOT/'results'/'COMPARISON.json',rows)
    if rows:
        pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in rows]).to_csv(ROOT/'results'/'COMPARISON.csv',index=False)
    print('DONE: forecast statistics are not trading win rates; inspect net results.',flush=True)
if __name__=='__main__':main()

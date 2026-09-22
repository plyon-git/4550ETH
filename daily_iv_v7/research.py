"""Daily BTC/ETH IV-wall research. One position/day, no multi-day holding.
Pretest selection; every forecast day and actual simulated trade is retained.
"""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,itertools,json,time
import numpy as np,pandas as pd
from core import *
ROOT=Path(__file__).resolve().parent
PERIODS={'development':('2021-05-01','2021-07-01'),'validation':('2021-07-01','2021-08-25'),
 'five_years':('2021-09-01','2026-09-01'),'250_weeks':('2021-11-15','2026-08-31')}

def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')

def grid():
    policies=[]
    for r,e,w,st,tp in itertools.product(RULES[:12],[2,482],['latest_iv','mean5_iv','history_mean'],[.5,1.,1.5],[.25,.5,1.]):
        policies.append(Policy(r,e,w,st,tp))
    for rule,w,tr,st,tp in itertools.product(['wall_rejection','wall_continuation'],['latest_iv','mean5_iv','history_mean'],[.15,.25,.50],[.75,1.5],[0.,.5,1.]):
        if rule=='wall_continuation' and tp<=tr:continue
        policies.append(Policy(rule,2,w,st,tp,trigger_multiple=tr))
    return policies

def summarize(out,dates,initial=10000.):
    eq,ledger,skips,bound=out;days=len(dates)-1
    gains=eq[1:]/eq[:-1]-1
    if not np.isfinite(gains).all():raise ValueError('nonfinite daily returns')
    series=pd.Series(eq,index=dates);net=eq[-1]/initial-1
    complete=pd.date_range(dates[0],dates[-1],freq='W-MON')
    weeks=np.array([series.loc[b]/series.loc[a]-1 for a,b in zip(complete[:-1],complete[1:])])
    streak=best=0
    for r in weeks:
        streak=streak+1 if r<0 else 0;best=max(best,streak)
    annual=[]
    for i in range(5):
        a=dates[0]+pd.DateOffset(years=i);b=dates[0]+pd.DateOffset(years=i+1)
        if b in series.index:annual.append(float(series[b]/series[a]-1))
    rolling=(series/series.shift(365)-1).dropna();wins=ledger[:,13]>0;losses=ledger[:,13]<0
    profit=ledger[wins,13].sum();loss=-ledger[losses,13].sum()
    return {'calendar_days':days,'trades':len(ledger),'skipped_days':int((skips>0).sum()),
      'maximum_entries_per_day':1 if len(ledger) else 0,'all_trades_close_same_UTC_day':True,
      'initial_equity':initial,'final_equity':float(eq[-1]),'net_return':float(net),
      'cagr':float(max(0,1+net)**(365.2425/days)-1),'win_rate':float(wins.mean()) if len(ledger) else None,
      'net_profit_factor':float(profit/loss) if loss>0 else None,
      'average_win':float(ledger[wins,13].mean()) if wins.any() else 0.,
      'average_loss':float(ledger[losses,13].mean()) if losses.any() else 0.,
      'price_pnl_before_fees_funding':float(ledger[:,12].sum()),'commissions':float(ledger[:,9:11].sum()),
      'net_funding_paid':float(ledger[:,11].sum()),'close_to_close_drawdown':float(np.max(1-eq/np.maximum.accumulate(eq))),
      'conservative_intrabar_drawdown_bound':float(bound),'complete_Monday_weeks':len(weeks),
      'geometric_weekly_7day_equivalent':float(max(0,1+net)**(7/days)-1),
      'worst_complete_week':float(weeks.min()) if len(weeks) else None,'longest_losing_week_streak':int(best),
      'anniversary_year_returns':annual,'mean_anniversary_return':float(np.mean(annual)) if len(annual)==5 else None,
      'positive_years':int(sum(x>0 for x in annual)),'minimum_rolling_365day_return':float(rolling.min()) if len(rolling) else None,
      'maximum_rolling_365day_return':float(rolling.max()) if len(rolling) else None,
      'max_entry_notional_equity_ratio':float(ledger[:,16].max()) if len(ledger) else 0.,
      'modeled_liquidations':int((ledger[:,17]==4).sum()),'trades_exposed_to_mark_gaps':int(ledger[:,19].sum()),
      'counts_target_pass':len(ledger)>=1000,
      'CAGR65_trade1000_pass':bool(net>0 and (1+net)**(365.2425/days)-1>=.65 and len(ledger)>=1000),
      'arithmetic_annual65_trade1000_pass':bool(len(annual)==5 and np.mean(annual)>=.65 and len(ledger)>=1000),
      'all_five_years_positive':bool(len(annual)==5 and all(x>0 for x in annual))}

def audit(out,ts,m,missing,d,pol,start,end,fee_bps=5.,slip_bps=2.,initial=10000.,delay=0,decisions_override=None):
    eq,ledger,skips,_=out;args=decisions_override if decisions_override is not None else (wall_decisions(d,m,pol) if pol.rule.startswith('wall_') else decision_arrays(d,pol))
    step,tick,minnot=d.attrs['grid'];cash=initial;rebuilt=[initial];by_day={int(r[0]):r for r in ledger}
    if len(by_day)!=len(ledger):raise AssertionError('multiple entries in one day')
    for day in range(start,end):
        r=by_day.get(day)
        if r is None:
            assert skips[day-start]>0;rebuilt.append(cash);continue
        di,ei,xi,side=map(int,r[:4]);qty,en,ex,sl,tp,ef,xf,fp,gross,net,pre,post,lev,reason,adverse,gap,_=r[4:]
        assert di==day and ei//1440==day and xi//1440==day and ei<=xi<=day*1440+1439
        assert ei==day*1440+args[3][day]+delay and side==args[0][day]
        assert np.isfinite(d.iv_close.iloc[day]) and d.iv_available_ms.iloc[day]<=ts[ei]
        assert d.iv_candle_ms.iloc[day]+DAY+60000==d.iv_available_ms.iloc[day]
        assert sl==args[1][day] and tp==args[2][day] and side*(en-sl)>0 and side*(tp-en)>0
        assert qty<=m[ei-1,4]*.01+1e-8 and qty*en<=cash*pol.exposure_cap+1e-6
        assert qty*en>=minnot and abs(qty/step-round(qty/step))<1e-6
        expected_entry=m[ei,0]*(1+side*slip_bps/1e4)
        expected_entry=(np.ceil(expected_entry/tick) if side==1 else np.floor(expected_entry/tick))*tick
        np.testing.assert_allclose(en,expected_entry,rtol=1e-12,atol=1e-8)
        funds=side*qty*m[ei:xi+1,5]*m[ei:xi+1,9];funds=funds.copy();funds[0]=max(0,funds[0])
        netcalc=side*qty*(ex-en)-qty*en*fee_bps/1e4-qty*ex*(.01 if reason==4 else fee_bps/1e4)-funds.sum()
        np.testing.assert_allclose([ef,xf,fp,gross,net,pre,post,lev],
           [qty*en*fee_bps/1e4,qty*ex*(.01 if reason==4 else fee_bps/1e4),funds.sum(),side*qty*(ex-en),netcalc,cash,cash+netcalc,qty*en/cash],rtol=1e-9,atol=1e-7)
        cash+=netcalc;rebuilt.append(cash)
        assert bool(gap)==bool(missing[ei:xi+1].any())
        if reason==3:assert xi%1440==1439
        window=m[ei:day*1440+1440,:4]
        hit_open=(side*(window[:,0]-sl)<=0)|(side*(window[:,0]-tp)>=0)
        hit_range=((window[:,2]<=sl)|(window[:,1]>=tp)) if side==1 else ((window[:,1]>=sl)|(window[:,2]<=tp))
        hit_range[-1]=False
        candidate=np.flatnonzero(hit_open|hit_range)
        earliest=ei+int(candidate[0]) if len(candidate) else day*1440+1439
        if reason!=4:
            assert xi==min(earliest,day*1440+1439)
            o,h,l,c=m[xi,:4]
            if side*(o-sl)<=0:raw_exit=o;expected_reason=1
            elif side*(o-tp)>=0:raw_exit=o;expected_reason=2
            elif xi==day*1440+1439:raw_exit=o;expected_reason=3
            elif (side==1 and l<=sl) or (side==-1 and h>=sl):raw_exit=sl;expected_reason=1
            else:raw_exit=tp;expected_reason=2
            price=raw_exit*(1-side*slip_bps/1e4)
            price=(np.floor(price/tick) if side==1 else np.ceil(price/tick))*tick
            assert reason==expected_reason
            np.testing.assert_allclose(ex,price,rtol=1e-12,atol=1e-8)
    np.testing.assert_allclose(rebuilt,eq,rtol=1e-9,atol=1e-7)
    return {'passed':True,'closed_trades_checked':len(ledger),'days_checked':end-start,
      'one_trade_per_day_verified':True,'same_day_exits_verified':True,'IV_publication_timing_verified':True,
      'first_exit_crossing_checked_independently':True,'daily_equity_cash_flow_max_error':float(np.max(abs(np.array(rebuilt)-eq))),
      'gross_pnl':float(ledger[:,12].sum()),'commissions':float(ledger[:,9:11].sum()),'funding':float(ledger[:,11].sum()),
      'net_pnl_sum':float(ledger[:,13].sum()),'calculation_scope':'ledger identities, causal entry/IV references, quantity/capacity constraints and all daily account balances; not independent exchange fills or exact tick ordering'}

def publish(path,out,ts,m,missing,d,pol,start,end,label,symbol,fee_bps=5.,slip_bps=2.,initial=10000.,delay=0,decisions_override=None):
    path=Path(path);path.mkdir(parents=True,exist_ok=True);dates=d.index[start:end+1]
    if len(dates)==end-start:dates=dates.append(pd.DatetimeIndex([dates[-1]+pd.Timedelta(days=1)]))
    stats=summarize(out,dates,initial);check=audit(out,ts,m,missing,d,pol,start,end,fee_bps,slip_bps,initial,delay,decisions_override)
    stats.update(case=label,symbol=symbol,start_utc=str(dates[0]),end_exclusive_utc=str(dates[-1]))
    save(path/'METRICS.json',stats);save(path/'AUDIT.json',check)
    save(path/'PARAMETERS.json',{'owner':'Parrish Lyon','policy':asdict(pol) if decisions_override is None else {'type':'causal_adaptive_selection','risk_fraction':pol.risk_fraction,'exposure_cap':pol.exposure_cap,'exact_daily_policies':'../adaptive_research/SELECTION_JOURNAL.json'},'entry_clock':'UTC','daily_horizon':1,
      'exit_deadline':'23:59 UTC same day','fee_bps_per_side':fee_bps,'slippage_bps_per_side':slip_bps,
      'entry_delay_minutes':delay,'initial_equity':initial,'instrument_grid_assumptions':d.attrs['grid'],
      'maintenance_assumption':.01,'participation':.01,'nominal_contract_leverage':'not an account return multiplier; backtest uses account exposure and a fixed maintenance approximation'})
    frame=pd.DataFrame(out[1],columns=LEDGER);frame.insert(0,'trade_id',np.arange(1,len(frame)+1))
    days=frame.day_index.to_numpy(int);ei=frame.entry_index.to_numpy(int);xi=frame.exit_index.to_numpy(int)
    frame['UTC_day']=d.index[days];frame['IV_observation_candle_open_utc']=pd.to_datetime(d.iv_candle_ms.iloc[days].to_numpy(),unit='ms',utc=True)
    frame['IV_available_utc']=pd.to_datetime(d.iv_available_ms.iloc[days].to_numpy(),unit='ms',utc=True)
    frame['IV_annualized_percent']=d.iv_close.iloc[days].to_numpy();frame['one_day_sigma']=d.sigma.iloc[days].to_numpy()
    frame['reference_price']=d.reference.iloc[days].to_numpy();frame['entry_utc_simulated']=pd.to_datetime(ts[ei],unit='ms',utc=True)
    frame['exit_bar_open_utc']=pd.to_datetime(ts[xi],unit='ms',utc=True)
    frame['exit_latest_utc']=pd.to_datetime(ts[xi]+np.where(frame.reason==3,0,60000),unit='ms',utc=True)
    frame['exit_reason']=frame.reason.astype(int).map(REASONS)
    frame['realized_net_R']=frame.net_pnl/(frame.quantity*abs(frame.entry_price-frame.initial_stop))
    frame['initial_price_RR']=abs(frame.initial_target-frame.entry_price)/abs(frame.entry_price-frame.initial_stop)
    frame['time_precision']='simulated minute opens; intrabar exits only known within minute, not actual exchange fills'
    frame.to_csv(path/'EVERY_TRADE_UTC.csv',index=False)
    daily=pd.DataFrame({'UTC_day':dates[:-1],'start_equity':out[0][:-1],'end_equity':out[0][1:],
      'daily_return':out[0][1:]/out[0][:-1]-1,'entries':(out[2]==0).astype(int),'status':[SKIPS[int(i)] for i in out[2]],
      'IV_annualized_percent':d.iv_close.iloc[start:end].to_numpy(),'IV_available_ms':d.iv_available_ms.iloc[start:end].to_numpy()})
    daily.to_csv(path/'EVERY_DAY.csv',index=False);series=pd.Series(out[0],index=dates)
    for period,freq in [('MONTHLY','MS'),('WEEKLY','W-MON')]:
        boundaries=sorted(set([dates[0],dates[-1]]+list(pd.date_range(dates[0],dates[-1],freq=freq))))
        rows=[{'start_utc':a,'end_exclusive_utc':b,'return':float(series[b]/series[a]-1),
               'complete_period':bool((b-a).days==7) if period=='WEEKLY' else bool(a.day==1 and b==a+pd.offsets.MonthBegin(1))}
               for a,b in zip(boundaries[:-1],boundaries[1:])]
        pd.DataFrame(rows).to_csv(path/(period+'_RETURNS.csv'),index=False)
    (series/series.shift(365)-1).dropna().rename('return').to_csv(path/'ROLLING_365DAY.csv',index_label='end_boundary_utc')
    return stats

def run(symbol,data_root):
    root=ROOT/'results'/symbol;root.mkdir(parents=True,exist_ok=True);policies=grid()
    save(root/'PROTOCOL.json',{'created_at_utc':str(pd.Timestamp.now(tz='UTC')),'target_min_trades_per_market':1000,'calendar':'24/7, all UTC days including weekends',
      'holding_horizon':'same UTC day only; no carry','periods':PERIODS,'grid':[asdict(p) for p in policies],
      'selection':'Within each rule/wall model choose development top two (>=90% scheduled or >=60% wall-trigger entry days), validation risks .5/1/2%. Primary: scheduled 00:02 entry, >=90% validation days traded, highest validation log gain minus 0.5 daily drawdown. Wall-only winner reported separately. Selected before five-year evaluation. No global untouched holdout.',
      'limitations':'Only several months of daily DVOL precede evaluation; development/validation short; formerly researched periods. Daily DVOL is 30-day annualized IV scaled by sqrt(365), not actual one-day-tenor IV or gamma/OI walls.'})
    iv,ivrec=verify_iv(ROOT/'context/iv_data',symbol.replace('USDT',''))
    ts,m,missing=load_market(data_root/symbol/'aligned_repaired.npz',symbol);d=daily_inputs(ts,m,iv)
    d.attrs['grid']=(.001,.1,100.) if symbol=='BTCUSDT' else (.001,.01,20.)
    bounds={k:tuple(int(np.searchsorted(d.index.asi8//1000000,pd.Timestamp(x,tz='UTC').timestamp()*1000)) for x in dates) for k,dates in PERIODS.items()}
    d.to_csv(root/'DAILY_IV_AND_FEATURES.csv',index_label='day_utc');print(symbol,'input verified',len(ts),'minutes',len(iv),'IV days',flush=True)
    records=[];t0=time.monotonic()
    for i,p in enumerate(policies):
        out=run_policy(m,missing,d,p,*bounds['development']);x=summarize(out,d.index[bounds['development'][0]:bounds['development'][1]+1]);sc=np.log(max(1e-12,1+x['net_return']))-.5*x['close_to_close_drawdown']
        records.append({'id':p.id,'policy':asdict(p),'metrics':x,'score':float(sc)})
        if (i+1)%150==0:print(symbol,'development',i+1,'/',len(policies),'seconds',round(time.monotonic()-t0,1),flush=True)
    save(root/'DEVELOPMENT.json',records);survivors=[]
    for rule,wall in itertools.product(RULES,['latest_iv','mean5_iv','history_mean']):
        subset=[r for r in records if r['policy']['rule']==rule and r['policy']['wall_model']==wall and r['metrics']['modeled_liquidations']==0 and r['metrics']['trades']>=r['metrics']['calendar_days']*(.60 if rule.startswith('wall_') else .90)]
        survivors.extend(sorted(subset,key=lambda x:x['score'],reverse=True)[:2])
    vals=[]
    for r in survivors:
        for risk in [.005,.01,.02]:
            p=replace(Policy(**r['policy']),risk_fraction=risk);out=run_policy(m,missing,d,p,*bounds['validation'])
            x=summarize(out,d.index[bounds['validation'][0]:bounds['validation'][1]+1]);sc=np.log(max(1e-12,1+x['net_return']))-.5*x['close_to_close_drawdown']
            vals.append({'id':p.id,'policy':asdict(p),'metrics':x,'score':float(sc)})
    save(root/'VALIDATION.json',vals)
    ranked=sorted([x for x in vals if x['metrics']['modeled_liquidations']==0 and x['metrics']['trades']>=.90*x['metrics']['calendar_days'] and x['policy']['entry_minute']==2 and not x['policy']['rule'].startswith('wall_')],key=lambda x:x['score'],reverse=True)
    if not ranked:raise ValueError('No sufficiently frequent scheduled primary')
    primary=ranked[0];finalists=[('PRIMARY_DAILY',primary)]
    wallrank=sorted([x for x in vals if x['policy']['rule'].startswith('wall_') and x['metrics']['trades']>=.60*x['metrics']['calendar_days'] and x['metrics']['modeled_liquidations']==0],key=lambda x:x['score'],reverse=True)
    if wallrank:finalists.append(('WALL_ONLY_PRIMARY',wallrank[0]))
    for rule in RULES:
        rows=[x for x in vals if x['policy']['rule']==rule]
        if rows:
            choice=max(rows,key=lambda x:x['score'])
            if choice['id'] not in [x[1]['id'] for x in finalists]:finalists.append(('DIAGNOSTIC_'+rule,choice))
    save(root/'FROZEN.json',{'frozen_at_utc':str(pd.Timestamp.now(tz='UTC')),'primary':primary,'cases':finalists})
    outputs=[]
    for label,choice in finalists:
        p=Policy(**choice['policy']);out=run_policy(m,missing,d,p,*bounds['five_years'])
        stats=publish(root/label,out,ts,m,missing,d,p,*bounds['five_years'],label,symbol);outputs.append(stats)
        print(symbol,label,stats['trades'],'return',round(stats['net_return']*100,2),'CAGR',round(stats['cagr']*100,2),flush=True)
    p=Policy(**primary['policy']);stress=[];fee=5/(3.6*2748.67)*10000
    for label,fb,sb,delay in [('NO_FEE_NO_SLIPPAGE',0.,0.,0),('USER_5USD_ROUNDTRIP_EQUIVALENT',fee/2,2.,0),('DOUBLE_COST',10.,4.,0),('DELAY_2MIN',5.,2.,2),('DELAY_5MIN',5.,2.,5)]:
        out=run_policy(m,missing,d,p,*bounds['five_years'],fb,sb,entry_delay=delay)
        stress.append(publish(root/label,out,ts,m,missing,d,p,*bounds['five_years'],label,symbol,fb,sb,delay=delay))
    out=run_policy(m,missing,d,p,*bounds['250_weeks']);p250=publish(root/'PRIMARY_250_WEEKS',out,ts,m,missing,d,p,*bounds['250_weeks'],'PRIMARY_250_WEEKS',symbol)
    save(root/'FINALISTS.json',outputs);save(root/'STRESSES.json',stress);save(root/'PRIMARY_250_WEEK_METRICS.json',p250)
    save(root/'DATA_IDENTITY.json',{'market_sha256':HASHES[symbol],'minute_rows':len(ts),'IV':ivrec,
      'missing_mark_minutes_entire_source':int(missing.sum()),'historical_wall_lookback':'up to 200 prior IV-normalized daily excursions, min30; counts exported',
      'five_year_IV_days_available':int(d.iv_close.iloc[bounds['five_years'][0]:bounds['five_years'][1]].notna().sum()),
      'raw_missing_marks_preserved_in_original':True,'mark_gap_simulation':'previous observed close; sourced 15m bounds where available, else +/-5% stress envelope. Not observed mark prices.'})
    print(symbol,'COMPLETE',round(time.monotonic()-t0,1),flush=True);return outputs

def finish():
    cases=[];stresses=[];audits=[];p250=[]
    for s in ('BTCUSDT','ETHUSDT'):
        p=ROOT/'results'/s;cases+=json.loads((p/'FINALISTS.json').read_text());stresses+=json.loads((p/'STRESSES.json').read_text());p250.append(json.loads((p/'PRIMARY_250_WEEK_METRICS.json').read_text()))
        audits.extend(json.loads(f.read_text()) for f in p.glob('*/AUDIT.json'))
    mains=[x for x in cases if x['case']=='PRIMARY_DAILY']
    summary={'owner':'Parrish Lyon','horizon':'1 UTC day; entry once, flat 23:59, no carry','primary_count_requirement_met':all(x['trades']>=1000 for x in mains),
      'five_year_primary_one_entry_every_day':all(x['trades']==1826 for x in mains),
      'any_tested_CAGR65_trade1000':any(x['CAGR65_trade1000_pass'] for x in cases),
      'any_tested_mean_annual65_trade1000':any(x['arithmetic_annual65_trade1000_pass'] for x in cases),
      'primaries':mains,'wall_only_primaries':[x for x in cases if x['case']=='WALL_ONLY_PRIMARY'],
      'best_test_diagnostic_not_primary':max(cases,key=lambda x:x['cagr']),'periods':PERIODS,'250week_primaries':p250,
      'cases':len(cases),'audits':len(audits),'audited_trades_across_separate_simulations':sum(x['closed_trades_checked'] for x in audits),
      'maximum_independent_daily_equity_error':max(x['daily_equity_cash_flow_max_error'] for x in audits),
      'all_audits_passed':all(x['passed'] for x in audits),'live_orders_submitted':False,
      'caveats':['Daily DVOL measurements scaled to a 1-day horizon; not true 1D option IV or dealer-position walls.',
      'Previously researched data; short pretest actual-IV history; test results are not a globally untouched holdout.',
      'Fees, slippage, grid, volume participation and maintenance are explicit simulation assumptions.',
      'Mark-price gaps model conservative bounds. Actual exchange fills and liquidation cannot be certified.',
      'Scheduled daily directional bets and conditional IV-wall entries are separate; no skip-day padding.']}
    save(ROOT/'ASSESSMENT.json',summary)
    pd.DataFrame([{k:v for k,v in x.items() if not isinstance(v,(dict,list))} for x in cases]).to_csv(ROOT/'ALL_CASES.csv',index=False)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',required=True,type=Path)
    p.add_argument('--symbols',nargs='+',choices=['BTCUSDT','ETHUSDT'],default=['BTCUSDT','ETHUSDT']);a=p.parse_args()
    for s in a.symbols:run(s,a.data_root)
    if all((ROOT/'results'/s/'FINALISTS.json').exists() for s in ('BTCUSDT','ETHUSDT')):finish()

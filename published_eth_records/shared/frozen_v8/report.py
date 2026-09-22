"""Independent cash/position reconstruction, UTC ledgers, five annual periods."""
from dataclasses import asdict
from pathlib import Path
import json
import numpy as np,pandas as pd
from core import LEDGER,REASONS,stats,DAY

def save(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')
def audit(out,m,missing,ts,sg,a,b,cfg,symbol):
    daily,ledger,z=out;n=b-a;delta=np.zeros(n);position=np.zeros(n);entrybasis=np.zeros(n);prior=-1
    step,tick=(.001,.01) if symbol=='ETHUSDT' else (.001,.1)
    overnight=0;holds=[];gaps=0
    for row in ledger:
        ei,xi,side=map(int,row[:3]);q,en,ex,sl,tp,ef,xf,fp,gross,net,pre,after,exp,initialmargin,coll,reason,atopen,gap,sidx=row[3:]
        assert a<=ei<=xi<b and ei>prior
        sr=sg[int(sidx)];assert int(sr[0])+cfg.delay_minutes==ei and int(sr[1])==side
        assert ts[ei]>=sr[6] and ts[ei]>=sr[7]
        assert xi-ei<=cfg.max_hold_hours*60
        assert side*(en-sl)>0 and side*(tp-en)>0
        computed=side*(tp-en)/(side*(en-sl))
        assert abs(computed-5)<=tick/(abs(en-sl))+1e-6
        assert abs(q/step-round(q/step))<1e-6
        assert q<=m[ei-1,4]*cfg.participation+1e-8 and q*en<=pre*cfg.cap+1e-6
        np.testing.assert_allclose([ef,gross,net,exp,initialmargin],[q*en*cfg.fee_bps/10000,side*q*(ex-en),gross-ef-xf-fp,q*en/pre,q*en/30],rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(xf,q*ex*(.01 if int(reason)==4 else cfg.fee_bps/10000),rtol=1e-10,atol=1e-7)
        assert coll>=initialmargin-1e-7 and coll+ef<=pre*.900001
        fund=side*q*m[ei:xi+1,5]*m[ei:xi+1,9];fund=fund.copy();fund[0]=max(0,fund[0]);np.testing.assert_allclose(fund.sum(),fp,rtol=1e-9,atol=1e-7)
        d,u=ei-a,xi-a;delta[d:u+1]-=fund;delta[d]-=ef;delta[u]+=gross-xf;position[d:u]=side*q;entrybasis[d:u]=en
        priorbars=m[ei:xi]
        if len(priorbars):
            assert not ((priorbars[:,2]<=sl).any() if side==1 else (priorbars[:,1]>=sl).any())
            assert not ((priorbars[:,1]>=tp).any() if side==1 else (priorbars[:,2]<=tp).any())
        if int(reason)==1:
            assert m[xi,2]<=sl if side==1 else m[xi,1]>=sl
        if int(reason)==2:
            assert m[xi,1]>=tp if side==1 else m[xi,2]<=tp
        if int(reason)==3:assert xi-ei==cfg.max_hold_hours*60
        assert gap==missing[ei:xi+1].sum()
        holds.append((xi-ei)/60);overnight+=int(ei//1440!=xi//1440);gaps+=int(gap);prior=xi
    cash=cfg.initial+np.cumsum(delta);eq=cash+position*(m[a:b,8]-entrybasis)
    rebuilt=np.r_[cfg.initial,eq[1439::1440]]
    np.testing.assert_allclose(rebuilt,daily,rtol=1e-9,atol=1e-6)
    np.testing.assert_allclose(cfg.initial+np.cumsum(ledger[:,12]),ledger[:,14],rtol=1e-9,atol=1e-6)
    return dict(passed=True,trades=len(ledger),minute_rows=n,days=len(daily)-1,ledger_cash_reconstructed=True,
       max_daily_equity_error=float(np.max(np.abs(rebuilt-daily))),all_hold_hours_le72=True,all_initial_targets_5R=True,
       trades_carried_overnight=overnight,max_hold_hours=max(holds) if holds else 0,median_hold_hours=float(np.median(holds)) if holds else 0,
       position_missing_mark_minutes=gaps,gross_price_pnl=float(ledger[:,11].sum()),fees=float(ledger[:,8:10].sum()),funding=float(ledger[:,10].sum()),net_pnl=float(ledger[:,12].sum()))

def publish(folder,out,m,missing,ts,sg,a,b,cfg,symbol,row):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    met=stats(out,ts[a],ts[b-1]+60000);check=audit(out,m,missing,ts,sg,a,b,cfg,symbol)
    met.update({k:check[k] for k in ['trades_carried_overnight','max_hold_hours','median_hold_hours','position_missing_mark_minutes']})
    met['at_least1000_trades']=met['trades']>=1000
    met['cagr_above45']=met['cagr']>.45;met['mean_annual_above45']=met['mean_annual'] is not None and met['mean_annual']>.45
    frame=pd.DataFrame(out[1],columns=LEDGER);frame.insert(0,'trade_id',np.arange(1,len(frame)+1))
    ei=frame.entry_index.to_numpy(int);xi=frame.exit_index.to_numpy(int);si=frame.signal_row.to_numpy(int)
    frame['entry_utc']=pd.to_datetime(ts[ei],unit='ms',utc=True)
    frame['exit_bar_open_utc']=pd.to_datetime(ts[xi],unit='ms',utc=True)
    frame['exit_utc_upper_bound']=pd.to_datetime(ts[xi]+np.where(frame.exit_at_open==1,0,60000),unit='ms',utc=True)
    frame['hold_hours']=(xi-ei)/60.;frame['overnight']=(ei//1440)!=(xi//1440)
    frame['reason_text']=frame.reason.map(REASONS);frame['target_price_R']=abs(frame.initial_target-frame.entry_price)/abs(frame.entry_price-frame.initial_stop)
    frame['net_realized_R']=frame.net_pnl/(frame.quantity*abs(frame.entry_price-frame.initial_stop))
    frame['daily_iv_available_utc']=pd.to_datetime(sg[si,6],unit='ms',utc=True);frame['weekly_iv_available_utc']=pd.to_datetime(sg[si,7],unit='ms',utc=True)
    frame['signal_upper_wall']=sg[si,4];frame['signal_lower_wall']=sg[si,5];frame['additional_collateral']=frame.allocated_collateral-frame.initial_margin_30x
    frame.to_csv(folder/'EVERY_TRADE_UTC.csv',index=False)
    series=pd.Series(out[0],index=pd.date_range(pd.Timestamp(ts[a],unit='ms',tz='UTC'),periods=len(out[0]),freq='D'),name='equity')
    series.to_csv(folder/'DAILY_EQUITY.csv',index_label='boundary_utc')
    mon=series[series.index.weekday==0];mon.pct_change().dropna().rename('net_return').to_csv(folder/'WEEKLY_RETURNS.csv',index_label='week_end_exclusive_utc')
    (series/series.shift(365)-1).dropna().rename('net_return').to_csv(folder/'ROLLING_365D.csv',index_label='end_exclusive_utc')
    bounds=sorted(set([series.index[0],series.index[-1]]+list(pd.date_range(series.index[0],series.index[-1],freq='MS'))))
    pd.DataFrame([dict(start_utc=x,end_exclusive_utc=y,net_return=series[y]/series[x]-1) for x,y in zip(bounds[:-1],bounds[1:])]).to_csv(folder/'MONTHLY_RETURNS.csv',index=False)
    save(folder/'ANNUAL_RETURNS.json',dict(start_utc=str(series.index[0]),anniversary_returns=met['annual_returns'],mean=met['mean_annual'],cagr=met['cagr']))
    save(folder/'METRICS.json',met);save(folder/'INDEPENDENT_AUDIT.json',check);save(folder/'PARAMETERS.json',dict(selected=row,actual_execution=asdict(cfg),symbol=symbol))
    return met

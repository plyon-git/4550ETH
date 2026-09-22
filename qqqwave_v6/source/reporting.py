from pathlib import Path
import json
import numpy as np,pandas as pd
from .engine import summary,TRADE_COLS,REASONS

def dump(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')

def metrics(out,ts,a,b,cfg):
    d,w=summary(out,ts,a,b,cfg)
    for k in ['gates','passes_historical_average_target']:d.pop(k,None)
    days=(int(ts[b-1])+60-int(ts[a]))/86400
    d['days']=days;d['cagr']=max(0,1+d['net_return'])**(365.2425/days)-1
    eq,eo=out[:2];boundary=ts[a:b]%86400==0
    dates=pd.to_datetime(ts[a:b][boundary],unit='s',utc=True)
    daily=pd.Series(np.r_[eo[boundary],eq[-1]],index=list(dates)+[pd.Timestamp(ts[b-1]+60,unit='s',tz='UTC')])
    rolling=daily/daily.shift(365)-1
    valid=rolling.dropna()
    d['minimum_rolling_365day_return']=float(valid.min()) if len(valid) else None
    d['maximum_rolling_365day_return']=float(valid.max()) if len(valid) else None
    begin=daily.index[0];annual=[]
    for i in range(5):
        at=begin+pd.DateOffset(years=i);end=begin+pd.DateOffset(years=i+1)
        if at in daily.index and end in daily.index:annual.append(float(daily.loc[end]/daily.loc[at]-1))
    d['anniversary_year_returns']=annual
    d['arithmetic_mean_annual_return']=float(np.mean(annual)) if len(annual)==5 else None
    d['positive_anniversary_years']=sum(x>0 for x in annual)
    d['cagr65_and_min200trades']=bool(d['cagr']>=.65 and d['trades']>=200)
    d['mean_annual65_and_min200trades']=bool(len(annual)==5 and np.mean(annual)>=.65 and d['trades']>=200)
    d['all_5_years_positive']=bool(len(annual)==5 and all(x>0 for x in annual))
    return d,w,daily,rolling

def independent(out,m,ts,a,b,cfg,sg):
    ledger=out[3];n=b-a;delta=np.zeros(n);q=np.zeros(n);basis=np.zeros(n);last=-1
    for r in ledger:
        ei,xi,side=map(int,r[:3]);qty,en,ex,ef,xf,funding,gross,net,bal,reason,pre,lev,upper=r[3:]
        assert a<=ei<=xi<b and ei>last and sg[0][ei-cfg.entry_delay_bars]==side
        stop=sg[1][ei-cfg.entry_delay_bars];target=sg[2][ei-cfg.entry_delay_bars]
        assert side*(en-stop)>0 and side*(target-en)>0
        assert ts[ei]<sg[3][ei-cfg.entry_delay_bars]
        np.testing.assert_allclose([gross,net,ef,lev],[side*qty*(ex-en),gross-ef-xf-funding,qty*en*cfg.fee_bps/1e4,qty*en/pre],rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(xf,qty*ex*(cfg.liquidation_fee_bps if reason==5 else cfg.fee_bps)/1e4,rtol=1e-10,atol=1e-7)
        assert qty<=m[ei-1,4]*cfg.participation+1e-8
        assert abs(qty/cfg.quantity_step-round(qty/cfg.quantity_step))<1e-6
        fund=side*qty*m[ei:xi+1,5]*m[ei:xi+1,9];fund=fund.copy();fund[0]=max(0,fund[0])
        np.testing.assert_allclose(fund.sum(),funding,rtol=1e-10,atol=1e-7)
        l,u=ei-a,xi-a;delta[l:u+1]-=fund;delta[l]-=ef;delta[u]+=gross-xf;q[l:u]=side*qty;basis[l:u]=en;last=xi
    cash=cfg.initial_equity+np.cumsum(delta)
    close=cash+q*(m[a:b,8]-basis)
    op=np.r_[cfg.initial_equity,cash[:-1]]+np.r_[0.,q[:-1]]*(m[a:b,5]-np.r_[0.,basis[:-1]])
    np.testing.assert_allclose(close,out[0],rtol=1e-10,atol=1e-7);np.testing.assert_allclose(op,out[1],rtol=1e-10,atol=1e-7)
    np.testing.assert_allclose(cfg.initial_equity+ledger[:,10].sum(),out[0][-1],rtol=1e-10,atol=1e-7)
    return {'passed':True,'trade_rows':len(ledger),'minute_rows':n,'reconstructed_series':2,
            'largest_absolute_equity_error':float(max(np.max(abs(close-out[0])),np.max(abs(op-out[1])))),
            'gross_price_pnl':float(ledger[:,9].sum()),'commissions':float(ledger[:,6:8].sum()),'funding_paid':float(ledger[:,8].sum()),'net_pnl':float(ledger[:,10].sum())}

def publish(folder,out,m,ts,a,b,cfg,sg,metadata,full=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    d,w,daily,rolling=metrics(out,ts,a,b,cfg);check=independent(out,m,ts,a,b,cfg,sg)
    d['start_utc']=str(daily.index[0]);d['end_exclusive_utc']=str(daily.index[-1])
    frame=pd.DataFrame(out[3],columns=TRADE_COLS)
    frame.insert(0,'trade_id',np.arange(1,len(frame)+1))
    ei=frame.entry_index.to_numpy(dtype=int);xi=frame.exit_index.to_numpy(dtype=int)
    frame['signal_available_utc']=pd.to_datetime(ts[ei-cfg.entry_delay_bars]+60,unit='s',utc=True)
    frame['entry_utc_simulated']=pd.to_datetime(ts[ei],unit='s',utc=True)
    frame['exit_bar_open_utc']=pd.to_datetime(ts[xi],unit='s',utc=True)
    frame['exit_utc_upper_bound']=pd.to_datetime(frame.exit_epoch_upper_bound,unit='s',utc=True)
    frame['initial_stop']=sg[1][ei-cfg.entry_delay_bars];frame['initial_target']=sg[2][ei-cfg.entry_delay_bars]
    frame['forecast_expires_utc']=pd.to_datetime(sg[3][ei-cfg.entry_delay_bars],unit='s',utc=True)
    frame['planned_price_RR']=abs(frame.initial_target-frame.entry_price)/abs(frame.entry_price-frame.initial_stop)
    frame['realized_net_R']=frame.net_pnl/(frame.quantity*abs(frame.entry_price-frame.initial_stop))
    frame['exit_reason']=frame.reason_code.astype(int).map(REASONS)
    frame['intrabar_precision']='minute interval; not exact exchange fill'
    frame.to_csv(folder/'all_trades_UTC.csv',index=False)
    pd.DataFrame(w,columns=['week_start_epoch','net_return']).to_csv(folder/'weekly_returns.csv',index=False)
    daily.rename('equity').to_csv(folder/'daily_equity.csv',index_label='boundary_utc')
    rolling.dropna().rename('rolling_365day_return').to_csv(folder/'rolling_365day_returns.csv',index_label='boundary_utc')
    bounds=sorted(set([daily.index[0],daily.index[-1]]+[t for t in pd.date_range(daily.index[0],daily.index[-1],freq='MS')]))
    months=[{'start_utc':str(l),'end_exclusive_utc':str(u),'return':float(daily.loc[u]/daily.loc[l]-1),'full_calendar_month':l.day==1 and u==l+pd.offsets.MonthBegin(1)} for l,u in zip(bounds[:-1],bounds[1:])]
    pd.DataFrame(months).to_csv(folder/'monthly_returns.csv',index=False)
    if full:pd.DataFrame({'timestamp':ts[a:b],'equity_close':out[0],'equity_open':out[1],'conservative_equity_low':out[2]}).to_csv(folder/'minute_equity.csv.gz',index=False)
    dump(folder/'METRICS.json',d);dump(folder/'AUDIT.json',check);dump(folder/'PARAMETERS.json',metadata)
    return d,check

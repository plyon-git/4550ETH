#!/usr/bin/env python3
"""Reproduce the untouched 45.50% baseline and compare only its target R.

Owner of project-specific work: Parrish Lyon; see OWNERSHIP.md.
No learner, live broker, exchange credentials, or order submission is used.
"""
from __future__ import annotations
import argparse
from dataclasses import replace, asdict
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v3.engine import Config, TRADE_COLS, REASONS, load_npz, run, summary
from v3.signals import hypotheses

KEYS = ['timestamp','open','high','low','close','volume','quote_volume','trades',
        'taker_buy_volume','taker_buy_quote_volume','mark_open','mark_high',
        'mark_low','mark_close','funding_rate','funding_verified']
EXPECTED_DATA = 'cdecadabcd6152bca34bf322c3e140924ec13b51fdfc88e42b8ab650984ed6aa'
EXPECTED_EXTENDED = '7156e32e9e3813e2ef041ca03e9a30cb9f7246ea3b22e6549e09d2f750e6388c'
EXPECTED_RETURNS = {4.0: 0.4550402603689372, 1.75: -0.042664570961280734,
                    2.0: 0.030222539603360188}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def utc(epoch: int | float) -> str:
    return pd.Timestamp(int(epoch), unit='s', tz='UTC').isoformat().replace('+00:00','Z')


def prepare_data(extended: Path | None) -> Path:
    target = ROOT/'data/aligned_data.npz'
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        if digest(target) != EXPECTED_DATA:
            raise ValueError('Existing baseline data identity mismatch; refusing overwrite')
        return target
    if extended is None or digest(extended) != EXPECTED_EXTENDED:
        raise ValueError('Provide the verified extended-history artifact or original baseline data')
    with np.load(extended, allow_pickle=False) as z:
        ts = z['timestamp']
        start, end = np.searchsorted(ts, [1724198400000, 1780272000000])
        arrays = {k: z[k][start:end] for k in KEYS}
    np.savez_compressed(target, **arrays)
    if digest(target) != EXPECTED_DATA:
        target.unlink()
        raise ValueError('Recovered subset does not match the original canonical ZIP bytes')
    return target


def independent_audit(out, ts, raw, start, end, cfg, signal):
    """Reconstruct cash and every minute's open/close equity from closed trades."""
    eq, eo, _, ledger, _ = out
    n = end-start
    cash_delta = np.zeros(n)
    quantity = np.zeros(n)
    entry_basis = np.zeros(n)
    all_funding = 0.0
    last_exit = -1
    for row in ledger:
        ei, xi, side = map(int, row[:3])
        a, b = ei-start, xi-start
        qty, ent, ex, ef, xf, fp, gross, net, bal, reason, pre, lev, exit_upper = row[3:]
        assert 0 <= a <= b < n and ei > last_exit
        assert side == signal[ei-cfg.entry_delay_bars]
        assert qty > 0 and int(reason) in REASONS
        assert ts[xi] <= exit_upper <= ts[xi]+60
        q = side*qty
        np.testing.assert_allclose(gross, q*(ex-ent), rtol=1e-12, atol=1e-8)
        np.testing.assert_allclose(net, gross-ef-xf-fp, rtol=1e-12, atol=1e-8)
        np.testing.assert_allclose(lev, qty*ent/pre, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(ef, qty*ent*cfg.fee_bps/1e4, rtol=1e-12, atol=1e-8)
        rate = cfg.liquidation_fee_bps if int(reason)==5 else cfg.fee_bps
        np.testing.assert_allclose(xf, qty*ex*rate/1e4, rtol=1e-12, atol=1e-8)
        assert abs(qty/cfg.quantity_step-round(qty/cfg.quantity_step)) < 1e-7
        for price in [ent, ex]:
            assert abs(price/cfg.price_tick-round(price/cfg.price_tick)) < 1e-7
        funds = q*raw['mark_open'][ei:xi+1]*raw['funding_rate'][ei:xi+1]
        funds = funds.copy()
        funds[0] = max(funds[0], 0.0)
        np.testing.assert_allclose(funds.sum(), fp, rtol=1e-12, atol=1e-8)
        all_funding += float(funds.sum())
        cash_delta[a:b+1] -= funds
        cash_delta[a] -= ef
        cash_delta[b] += gross-xf
        quantity[a:b] = q
        entry_basis[a:b] = ent
        last_exit = xi
    cash = cfg.initial_equity + np.cumsum(cash_delta)
    rebuilt_close = cash + quantity*(raw['mark_close'][start:end]-entry_basis)
    previous_q = np.r_[0.0, quantity[:-1]]
    previous_basis = np.r_[0.0, entry_basis[:-1]]
    previous_cash = np.r_[cfg.initial_equity, cash[:-1]]
    rebuilt_open = previous_cash+previous_q*(raw['mark_open'][start:end]-previous_basis)
    np.testing.assert_allclose(rebuilt_close, eq, rtol=1e-11, atol=1e-7)
    np.testing.assert_allclose(rebuilt_open, eo, rtol=1e-11, atol=1e-7)
    np.testing.assert_allclose(cfg.initial_equity+ledger[:,10].sum(), eq[-1], rtol=1e-11, atol=1e-7)
    np.testing.assert_allclose(cfg.initial_equity+np.cumsum(ledger[:,10]), ledger[:,11], rtol=1e-11, atol=1e-7)
    return {'passed': True, 'trades_checked': len(ledger), 'minute_rows_checked': n,
            'equity_series_independently_reconstructed': 2,
            'max_close_equity_error': float(np.max(np.abs(rebuilt_close-eq))),
            'max_open_equity_error': float(np.max(np.abs(rebuilt_open-eo))),
            'sum_gross_pnl': float(ledger[:,9].sum()),
            'sum_entry_exit_fees': float(ledger[:,6:8].sum()),
            'sum_funding_paid': all_funding, 'sum_net_pnl': float(ledger[:,10].sum()),
            'wins_net_of_costs': int((ledger[:,10]>0).sum()),
            'losses_net_of_costs': int((ledger[:,10]<0).sum())}


def enriched_trades(ledger, ts, stops, cfg):
    df = pd.DataFrame(ledger, columns=TRADE_COLS)
    for k in ['entry_index','exit_index','side','reason_code','exit_epoch_upper_bound']:
        df[k] = df[k].astype(np.int64)
    ei, xi = df.entry_index.to_numpy(), df.exit_index.to_numpy()
    df.insert(0, 'trade_id', np.arange(1,len(df)+1))
    df.insert(1, 'target_r', cfg.target_r)
    df['signal_minute_open_utc'] = [utc(ts[i-cfg.entry_delay_bars]) for i in ei]
    df['signal_timeframe_start_utc'] = [utc((ts[i-cfg.entry_delay_bars]//900)*900) for i in ei]
    df['signal_available_utc'] = [utc(ts[i-cfg.entry_delay_bars]+60) for i in ei]
    df['entry_utc_simulated'] = [utc(ts[i]) for i in ei]
    df['exit_bar_open_utc'] = [utc(ts[i]) for i in xi]
    df['exit_utc_upper_bound'] = [utc(x) for x in df.exit_epoch_upper_bound]
    df['exit_time_precision'] = [
        'simulated_final_close' if int(r)==8 else
        ('simulated_bar_open' if int(u)==int(ts[i]) else 'within_minute_not_exact_tick')
        for i,u,r in zip(xi,df.exit_epoch_upper_bound,df.reason_code)]
    df['exit_reason'] = df.reason_code.map(REASONS)
    distance = df.entry_price.to_numpy()*stops[ei-cfg.entry_delay_bars]
    df['initial_stop_price'] = df.entry_price-df.side*distance
    df['initial_target_price'] = df.entry_price+df.side*distance*cfg.target_r
    df['initial_price_risk_usdt'] = df.quantity*distance
    df['realized_net_r'] = df.net_pnl/df.initial_price_risk_usdt
    df['net_return_on_entry_equity'] = df.net_pnl/df.equity_before
    return df


def period_returns(out, timestamps, freq):
    eq, eo = out[0], out[1]
    start, end = int(timestamps[0]), int(timestamps[-1])+60
    first, last = pd.Timestamp(start,unit='s',tz='UTC'), pd.Timestamp(end,unit='s',tz='UTC')
    interior = [int(t.timestamp()) for t in pd.date_range(first.normalize(),last,freq=freq)
                if start < t.timestamp() < end]
    bounds = [start]+interior+[end]
    def equity(t):
        return float(eq[-1]) if t==end else float(eo[np.searchsorted(timestamps,t)])
    rows=[]
    for a,b in zip(bounds[:-1],bounds[1:]):
        at,bt=pd.Timestamp(a,unit='s',tz='UTC'),pd.Timestamp(b,unit='s',tz='UTC')
        expected=(at+pd.offsets.MonthBegin(1)) if freq=='MS' else (at+pd.offsets.YearBegin(1))
        complete=bool(at.day==1 and at.hour==0 and at.minute==0 and expected==bt and (freq=='MS' or at.month==1))
        ea,eb=equity(a),equity(b)
        rows.append({'period':at.strftime('%Y-%m' if freq=='MS' else '%Y'),
                     'start_utc':utc(a),'end_utc_exclusive':utc(b),
                     'complete_calendar_period':complete,'days':(b-a)/86400,
                     'equity_start':ea,'equity_end':eb,'net_return':eb/ea-1})
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--extended-data',type=Path)
    args=p.parse_args()
    saved=json.loads((ROOT/'SAVED_DIAGNOSTIC.json').read_text())
    data=prepare_data(args.extended_data)
    for rel,wanted in saved['source_hashes'].items():
        if digest(ROOT/rel)!=wanted:
            raise ValueError(f'Original identity mismatch: {rel}')
    base=Config(**saved['candidate']['config'])
    m,ts,raw=load_npz(data)
    spec,signals,stops=next(x for x in hypotheses(raw) if x[0]['id']==saved['candidate']['id'])
    a,b=[int(np.searchsorted(ts,pd.Timestamp(s).timestamp())) for s in
         json.loads((ROOT/'PROTOCOL.json').read_text())['evaluation']]
    results=ROOT/'results';results.mkdir(exist_ok=True)
    stats_list=[];audits={};months=[];years=[];trades=[];weekly=[]
    for rr in [4.0,1.75,2.0]:
        cfg=replace(base,target_r=rr)
        out=run(m,ts,signals,stops,cfg,a,b,True)
        stats,weeks=summary(out,ts,a,b,cfg)
        np.testing.assert_allclose(stats['net_return'],EXPECTED_RETURNS[rr],rtol=1e-10,atol=1e-9)
        audit=independent_audit(out,ts,raw,a,b,cfg,signals)
        audits[str(rr)]=audit
        stats['target_r']=rr
        stats['wins']=audit['wins_net_of_costs'];stats['losses']=audit['losses_net_of_costs']
        days=(ts[b-1]+60-ts[a])/86400
        stats['days']=days
        stats['annualized_return_365_2425_day_basis']=(1+stats['net_return'])**(365.2425/days)-1
        stats['annualized_note']='Annualization of a 364-day sample, not an observed full-calendar-year result.'
        positive=out[3][:,10][out[3][:,10]>0];negative=out[3][:,10][out[3][:,10]<0]
        stats['realized_average_win_to_average_loss']=float(positive.mean()/-negative.mean())
        stats_list.append(stats)
        t=enriched_trades(out[3],ts,stops,cfg);trades.append(t)
        mt=period_returns(out,ts[a:b],'MS');mt.insert(0,'target_r',rr);months.append(mt)
        yt=period_returns(out,ts[a:b],'YS');yt.insert(0,'target_r',rr);years.append(yt)
        wk=pd.DataFrame(weeks,columns=['week_start_epoch','net_return'])
        wk.insert(0,'target_r',rr);wk['week_start_utc']=wk.week_start_epoch.map(utc);weekly.append(wk)
        if rr==4.0:
            for k,v in saved['recorded_evaluation'].items():
                if k in stats and isinstance(v,(int,float)) and not isinstance(v,bool):
                    np.testing.assert_allclose(stats[k],v,rtol=1e-10,atol=1e-8,err_msg=k)
            # Existing reference files, when supplied locally, must match before any write.
            reference=results/'breakout_trades.csv.gz'
            raw_trades=pd.DataFrame(out[3],columns=TRADE_COLS)
            if reference.exists():
                np.testing.assert_allclose(raw_trades.to_numpy(),pd.read_csv(reference).to_numpy(),rtol=1e-12,atol=1e-8)
            eqframe=pd.DataFrame({'timestamp':ts[a:b], 'equity_close':out[0],
                                'equity_open_pre_funding':out[1], 'conservative_equity_low':out[2]})
            eqreference=results/'breakout_equity.csv.gz'
            if eqreference.exists():
                ref=pd.read_csv(eqreference)
                for col in ['equity_close','equity_open_pre_funding','conservative_equity_low']:
                    np.testing.assert_allclose(eqframe[col],ref[col],rtol=1e-12,atol=1e-8)
            raw_trades.to_csv(results/'breakout_trades.csv',index=False)
            if not reference.exists():
                raw_trades.to_csv(reference,index=False,compression={'method':'gzip','mtime':0})
            if not eqreference.exists():
                eqframe.to_csv(eqreference,index=False,compression={'method':'gzip','mtime':0})
            t.to_csv(results/'breakout_trades_timestamped.csv',index=False)
            # Compact daily evidence is readable on GitHub; minute reference remains complete.
            daymask=ts[a:b]%86400==0
            daily=pd.DataFrame({'boundary_utc':[utc(x) for x in ts[a:b][daymask]],
                                'equity_pre_funding':out[1][daymask]})
            daily.loc[len(daily)]={'boundary_utc':utc(ts[b-1]+60),'equity_pre_funding':float(out[0][-1])}
            daily.to_csv(results/'breakout_daily_equity.csv',index=False)
    monthly=pd.concat(months,ignore_index=True);yearly=pd.concat(years,ignore_index=True)
    alltrades=pd.concat(trades,ignore_index=True)
    monthly.to_csv(results/'exit_target_monthly_comparison.csv',index=False)
    yearly.to_csv(results/'exit_target_calendar_year_segments.csv',index=False)
    alltrades.to_csv(results/'exit_target_all_trades_timestamped.csv',index=False)
    pd.concat(weekly,ignore_index=True).to_csv(results/'exit_target_weekly_comparison.csv',index=False)
    save_json(results/'EXIT_TARGET_COMPARISON.json',stats_list)
    save_json(results/'INDEPENDENT_LEDGER_AUDIT.json',audits)
    paired=monthly.pivot(index='period',columns='target_r',values='net_return')
    complete=monthly.loc[monthly.target_r==4,'complete_calendar_period'].to_numpy()
    gate={'original_source_unchanged':True,'changed_config_field_only':'target_r',
          'two_r_total_gain_exceeds_four_r':stats_list[2]['net_return']>stats_list[0]['net_return'],
          'two_r_better_months_including_partial':int((paired[2.0]>paired[4.0]).sum()),
          'paired_month_segments':len(paired),
          'two_r_better_complete_months':int(((paired[2.0]>paired[4.0]).to_numpy()&complete).sum()),
          'complete_months':int(complete.sum()),
          'two_r_beats_four_r_every_month':bool((paired[2.0]>paired[4.0]).all()),
          'observed_full_calendar_year_or_12_month_yoy_available':False,
          'yoy_limitation':'Exactly 52 weeks is 364 days; calendar-year rows are partial. No complete 12-month YoY comparison is claimed.',
          'create_4550_gain_variant_folder':False,
          'decision':'Do not create a performance-named 2R folder: its total gain is lower than unchanged 4R.'}
    save_json(results/'CONDITIONAL_PUBLICATION_GATE.json',gate)
    manifest={}
    for item in [data,*sorted(results.glob('*')),*sorted((ROOT/'v3').glob('*.py')),
                 ROOT/'SAVED_DIAGNOSTIC.json',ROOT/'PROTOCOL.json',Path(__file__)]:
        if item.is_file() and item.name!='EVIDENCE_SHA256.json':
            manifest[str(item.relative_to(ROOT))]={'sha256':digest(item),'bytes':item.stat().st_size}
    save_json(ROOT/'EVIDENCE_SHA256.json',manifest)
    print(json.dumps({'summary':stats_list,'gate':gate,'audits':audits},indent=2))

if __name__=='__main__':
    main()

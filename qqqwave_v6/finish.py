"""Assemble factual cross-market evidence; return targets are never fabricated."""
from pathlib import Path
import argparse,hashlib,json,platform,shutil,zipfile
import numpy as np,pandas as pd
from source.reporting import dump
from source.inputs import digest
ROOT=Path(__file__).resolve().parent
SYMBOLS=('ETHUSDT','BTCUSDT','XRPUSDT')
EXPECTED={'ETHUSDT':(-.22720773841546038,1250),'BTCUSDT':(-.4513016551204604,978),'XRPUSDT':(-.07567586767268386,1376)}

def inventory():
    result=[]
    for path in ROOT.rglob('*'):
        rel=path.relative_to(ROOT)
        if not path.is_file() or any(p in rel.parts for p in ('__pycache__','.pytest_cache','data','.venv')):continue
        if path.suffix in ('.nbc','.nbi','.pyc','.log') or path.name in ('MANIFEST.json',):continue
        result.append(path)
    return sorted(result)

def assemble(context=None,verify_reference=False):
    if context is not None:
        for sub,names in {'iv_data':['ETH_1D.csv','BTC_1D.csv','ETH_1D_000.json','ETH_1D_001.json','BTC_1D_000.json','BTC_1D_001.json','PROVENANCE.json'],
                          'equity_data':['QQQ_daily.csv','SPY_daily.csv','QQQ_raw.json','SPY_raw.json','PROVENANCE.json']}.items():
            for name in names:
                origin=context/sub/name;dest=ROOT/'context'/sub/name;dest.parent.mkdir(parents=True,exist_ok=True)
                if origin.resolve()!=dest.resolve():shutil.copy2(origin,dest)
    cases=[];audits=[];primary=[];stresses=[];events={};screenshot=[];all_periods=[]
    for sym in SYMBOLS:
        base=ROOT/'results'/sym;rows=json.loads((base/'INDEX.json').read_text());cases.extend(rows)
        chosen=next(x for x in rows if x['primary']);primary.append(chosen)
        if verify_reference:
            gain,trades=EXPECTED[sym]
            np.testing.assert_allclose(chosen['net_return'],gain,rtol=1e-10,atol=1e-10)
            if chosen['trades']!=trades:raise ValueError('Primary trade count differs from separate reference run')
        stresses.extend([{'symbol':sym,**x} for x in json.loads((base/'STRESSES.json').read_text())])
        all_periods.append({'symbol':sym,**json.loads((base/'PRIMARY_250W.json').read_text())})
        for path in base.glob('*/AUDIT.json'):
            audit=json.loads(path.read_text());tr=pd.read_csv(path.parent/'all_trades_UTC.csv')
            if not audit['passed'] or len(tr)!=audit['trade_rows'] or tr.trade_id.duplicated().any():raise ValueError('Missing or mismatched trade evidence')
            if len(tr) and not (tr.trade_id.to_numpy()==np.arange(1,len(tr)+1)).all():raise ValueError('Omitted trade IDs')
            audits.append(audit)
        for row in rows:
            if 'SCREENSHOT_TOUCH_' in row['case']:
                frame=pd.read_csv(base/row['case']/'all_trades_UTC.csv');win=frame.net_pnl[frame.net_pnl>0];loss=frame.net_pnl[frame.net_pnl<0]
                payoff=float(win.mean()/-loss.mean())
                screenshot.append({**row,'mean_winning_trade':float(win.mean()),'mean_losing_trade':float(loss.mean()),
                    'realized_average_win_loss_ratio':payoff,'empirical_breakeven_win_rate_for_observed_payoffs':1/(1+payoff),
                    'median_planned_price_RR':float(frame.planned_price_RR.median()),
                    'target_exits':int((frame.exit_reason=='target').sum()),
                    'target_exits_with_net_loss':int(((frame.exit_reason=='target')&(frame.net_pnl<0)).sum())})
    for sym in (*SYMBOLS,'QQQ','SPY'):
        rows=json.loads((ROOT/'results'/sym/'EVENT_SUMMARIES.json').read_text())
        events[sym]=next(x for x in rows if x['surface_id']=='2c21ef7fba1d')
    screenshot_analysis=json.loads((ROOT/'SCREENSHOT_ANALYSIS.json').read_text())
    counts={'development_configurations':sum(len(json.loads((ROOT/'results'/s/'DEVELOPMENT.json').read_text())) for s in SYMBOLS),
            'validation_configurations':sum(len(json.loads((ROOT/'results'/s/'VALIDATION.json').read_text())) for s in SYMBOLS),
            'final_cases':len(cases),'cost_delay_stresses':len(stresses),'separate_250_week_cases':len(all_periods),
            'independent_ledger_audits':len(audits),'trade_rows_across_separate_simulations':sum(x['trade_rows'] for x in audits)}
    if counts['final_cases']!=22 or counts['independent_ledger_audits']!=43:raise ValueError('Research export is incomplete')
    assessment={'status':'NO_TESTED_65_PERCENT_ANNUAL_STRATEGY','owner':'Parrish Lyon',
                'replication_status':'transparent analogue of visible settings; not vendor formula or MinAvg replication',
                'evaluation':{'start_inclusive_utc':'2021-09-01T00:00:00Z','end_exclusive_utc':'2026-09-01T00:00:00Z','days':1826,'calendar_years':5},
                'separate_250weeks':{'start':'2021-11-15T00:00:00Z','end_exclusive':'2026-08-31T00:00:00Z','days':1750},
                'counts':counts,'cagr65_trade200_passes':sum(r['cagr65_and_min200trades'] for r in cases),
                'arithmetic_annual65_trade200_passes':sum(r['mean_annual65_and_min200trades'] for r in cases),
                'primaries':primary,'best_evaluation_diagnostic_not_primary':max(cases,key=lambda x:x['cagr']),
                'fixed_screenshot_hypotheses':screenshot,'default_event_surfaces':events,'primary_stresses':stresses,
                'separate_250week_primaries':all_periods,
                'limitations':['No proprietary MinAvg, bear subset, 76-sample construction or tooltip formula recovered.',
                    'Projected horizon-touch counts are not target-before-stop odds, terminal odds or net trade win rates.',
                    'Percentile chosen to target a high training touch frequency is not evidence of economic alpha.',
                    'QQQ and SPY are daily/session forecast-event diagnostics only, not intraday order simulations or ES futures.',
                    'Crypto trade tests use fixed prior-session levels, completed 5-minute signal bars and next-minute entries.',
                    'Historical scenarios are not live fills. V6 has no broker calls and was not armed into V4 live execution.',
                    'Missing marks use disclosed model bounds; grids, fees, impact, maintenance and latency remain assumptions.',
                    'Five-session outcomes overlap. Every fifth-origin sensitivity does not establish independent observations.',
                    'Previously researched calendar; validation selection does not create a globally untouched holdout.']}
    dump(ROOT/'ASSESSMENT.json',assessment)
    verification={'all_audits_passed':True,'audits':len(audits),'maximum_equity_reconstruction_error':max(x['largest_absolute_equity_error'] for x in audits),
                  'separate_reference_primary_check_requested':verify_reference,'no_live_orders':True,'python':platform.python_version(),
                  'visible_count_rows_checked':len(screenshot_analysis['count_rows']),
                  'all_visible_rows_fit_candidate_display_rule':all(x['adjusted_matches_rounding'] for x in screenshot_analysis['count_rows'])}
    dump(ROOT/'VERIFICATION.json',verification)
    def pct(x):return f'{100*x:+.2f}%'
    report=['# QQQWave-inspired V6: visible parameters and five-year evidence','',
        'Owner: Parrish Lyon. This is new empirical-range research, not proprietary QQQWave replication or a live trading recommendation.','',
        '**The high-touch forecasting structure is reproducible. No tested strategy reaches 65% CAGR or a 65% arithmetic mean annual return with 200 trades.**','',
        '## What the screenshot establishes','',
        'QQQ, one-day aggregation, 200 daily aggregations, five forward aggregations, Weekday Matching selected and HL Matching unselected. Reference 721.45001; MinAvg 715.69, 0.7983935% below reference. The displayed 97.37% does not establish profitable trades without the event, denominator, stop and payoff definitions.','',
        'All 25 visible count rows match `max(1%,100*(count-1)/(76-2))` to displayed precision. For example 24/76 is 31.5789%, but `(24-1)/74` is the shown 31.08%. This is a numerical fit, not documented vendor source. The tooltip may use a different calculation; 74/76 happens to round to 97.37%, but its denominator is not shown.','',
        'The IV column is present but empty in the screenshot. We cannot tell from that whether option IV drives the graph. Historical excursion distributions, option-derived IV and strike-position walls are separately identified, not conflated.','',
        '## New model','',
        'At each origin use the previous close and only 200 prior observed sessions. A historical five-session sample is eligible only after all five sessions finish. Match origin weekdays when selected. Calculate historical maximum highs, minimum lows and terminal returns relative to that sample\'s reference; normalize by its known RV20 and rescale using current known RV20. Test raw-percent and actual-DVOL-scaled variants separately.','',
        'The `mean_low_proxy` is an arithmetic mean of projected lows, not the vendor\'s unknown MinAvg. A separate 97.3684th-percentile low target tests the high-touch hypothesis. Under the specified weekday rule this uses 28 crypto samples or approximately 39-40 equity samples, not an invented 76.','',
        '## Five-session event results','',
        '| Market | Forecast origins | Lower-level touch | Terminal below level | Already at/below at origin open | Touch when target actually below open |',
        '|---|---:|---:|---:|---:|---:|']
    for sym,e in events.items():
        v=e['near97_low'];report.append(f"| {sym} | {e['forecast_origins']} | {v['all_origin_touch_rate']:.2%} | {v['terminal_rate']:.2%} | {v['already_beyond_at_origin_open']} | {v['valid_direction_touch_rate']:.2%} |")
    report += ['', 'These are forecast-event denominators, not executed trades. The QQQ lower level is touched in 95.52% of windows, but 922/1,250 already open at or below it; only 328 are valid lower short targets. Among those 328, 272 touch, or 82.93%. Its unconditional terminal-below frequency is 50.88%. The fixed screenshot percentage offset, a different diagnostic, is touched in 69.76% of QQQ windows, not a test of unknown vendor conditioning.','',
        '## Fixed high-touch trade test: same 200/5/weekday/realized parameters','',
        'Short after the first completed five-minute bar only when the fixed low target remains below the executable entry; use the projected upper-90th-percentile stop. Exit at stop, target, risk circuit or fixed five-day forecast deadline. One open position per account, 1% planned account risk, up to 5x exposure, previous-volume and order-grid limits. An eventual touch after a stop does not restore the losing trade.','',
        '| Market | Trades | Net win rate | Five-year net | CAGR | Mean of five annual returns |',
        '|---|---:|---:|---:|---:|---:|']
    for x in screenshot:
        if x['case'].endswith('near97'):report.append(f"| {x['symbol']} | {x['trades']} | {x['win_rate']:.2%} | {pct(x['net_return'])} | {pct(x['cagr'])} | {pct(x['arithmetic_mean_annual_return'])} |")
    eth=next(x for x in screenshot if x['symbol']=='ETHUSDT' and x['case'].endswith('near97'))
    report += ['',f"ETH averaged a {eth['mean_winning_trade']:.2f} USDT net winner versus {abs(eth['mean_losing_trade']):.2f} USDT net loser. At those observed payoffs the break-even win rate is {eth['empirical_breakeven_win_rate_for_observed_payoffs']:.2%}, above the actual {eth['win_rate']:.2%}. {eth['target_exits']} trades exited at target, but {eth['target_exits_with_net_loss']} of those still lost after the modeled fill/cost/funding arithmetic. This is why a high event hit rate alone is insufficient.",'',
        '## Validation-selected primaries','',
        '| Market | Five-year net | CAGR | Trades | Net WR | Worst week | Longest losing-week streak | Five annual returns |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for x in primary:report.append(f"| {x['symbol']} | {pct(x['net_return'])} | {pct(x['cagr'])} | {x['trades']} | {x['win_rate']:.2%} | {pct(x['worst_week'])} | {x['longest_losing_streak']} | {', '.join(pct(v) for v in x['anniversary_year_returns'])} |")
    report += ['', 'These primaries use different validation-selected families and risk settings; they are not the fixed 1% screenshot tests above. The five calendar years are 2021-09-01 through 2026-09-01 exclusive, 1,826 days. A separate 250-week account run spans 2021-11-15 through 2026-08-31. These durations are not equivalent.','',
        '## Execution-cost check, using the supplied example','',
        '3.6 ETH at 2,748.67 equals 9,895.212 USDT notional. Initial margin at 150x is 65.96808 USDT. Five dollars is 5.05295 basis points of notional, 7.5794% of initial margin, or 0.05% of a 10,000-USDT account. Which denominator matters depends on the question. The screenshot/user example does not verify whether $5 is one-way, round-trip or includes slippage.','',
        '| ETH selected primary scenario | Five-year net | CAGR | Net WR |',
        '|---|---:|---:|---:|']
    for x in stresses:
        if x['symbol']=='ETHUSDT' and x['scenario'] in ('no_fee_no_slippage','user5usd_round_trip','user5usd_one_way','double_cost'):
            report.append(f"| {x['scenario']} | {pct(x['net_return'])} | {pct(x['cagr'])} | {x['win_rate']:.2%} |")
    report += ['', 'The two $5 scenarios preserve 2bps adverse slippage per side and translate $5 at the quoted notional into a proportional fee; they do not charge a flat $5 on every differently sized trade. Zero-fee/zero-slippage retains historical funding and price-grid rounding. All scenarios rerun the sequential account; they are not a post-hoc fee-column subtraction.','',
        '## Audit and scope','',
        f"{counts['development_configurations']} development configurations; {counts['validation_configurations']} validation settings; {counts['final_cases']} finalists/fixed diagnostics; {counts['cost_delay_stresses']} stresses; {counts['separate_250_week_cases']} separate 250-week runs. All {counts['independent_ledger_audits']} trade/equity audits passed. Across separate simulations there are {counts['trade_rows_across_separate_simulations']:,} exported trade rows. These are related experiments, not independent discoveries or one combined portfolio.",'',
        'Every case retains timestamped trades, absolute initial levels and expiry, fees/funding, daily equity, weekly/monthly/rolling-year returns, source configuration and independent reconciliation. Minute-equity series can be regenerated; the default export is daily equity plus full trade records. QQQ/SPY results are event-only daily diagnostics, not five-minute ES executions. No broker calls or live V6 orders were made.','',
        'Actual BTC/ETH DVOL is options-derived; our IV variant uses it to scale historical excursions and is explicitly a hybrid. Historical RV is not renamed IV. Raw option strikes, OI, dealer inventory and the proprietary Milk/QQQWave formula were not supplied or replicated. Prior periods were researched before; this is not a globally untouched holdout.','',
        '## Source definitions','',
        'Deribit DVOL methodology: https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/','',
        'CME option position/volume concentrations by strike and expiry: https://www.cmegroup.com/education/courses/tools-for-option-analysis/cmed-qs-open-interest-heatmap','',
        'Visible parameters come from the user-supplied image. See SCREENSHOT_ANALYSIS.json for exact transcribed rows, arithmetic and unknowns. See docs/USERINSTRUCTIONS.md for portable snapshots and reproductions.']
    (ROOT/'RESULTS.md').write_text('\n'.join(report)+'\n')
    return assessment,verification

def main():
    p=argparse.ArgumentParser();p.add_argument('--context-root',type=Path);p.add_argument('--verify-reference',action='store_true');p.add_argument('--zip-out',type=Path);a=p.parse_args()
    assessment,verification=assemble(a.context_root,a.verify_reference)
    manifest={str(p.relative_to(ROOT)):{'sha256':digest(p),'bytes':p.stat().st_size} for p in inventory()}
    dump(ROOT/'MANIFEST.json',manifest)
    if a.zip_out:
        a.zip_out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.zip_out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for path in inventory():z.write(path,'qqqwave_v6/'+str(path.relative_to(ROOT)))
            z.write(ROOT/'MANIFEST.json','qqqwave_v6/MANIFEST.json')
        with zipfile.ZipFile(a.zip_out) as z:
            if z.testzip():raise ValueError('corrupt ZIP')
            for name,rec in manifest.items():
                if hashlib.sha256(z.read('qqqwave_v6/'+name)).hexdigest()!=rec['sha256']:raise ValueError('archive hash mismatch')
        print(json.dumps({'zip':str(a.zip_out),'sha256':digest(a.zip_out),'bytes':a.zip_out.stat().st_size,'verified_files':len(manifest),'verification':verification},indent=2))
    else:print(json.dumps(verification,indent=2))
if __name__=='__main__':main()

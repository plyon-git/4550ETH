"""Package only actual computed daily-IV evidence. No preset profit claims."""
from pathlib import Path
import argparse,json,zipfile,hashlib
import numpy as np,pandas as pd
from core import sha
from research import ROOT,save,finish

def build():
    data=finish();adapt=[]
    for s in ['BTCUSDT','ETHUSDT']:
        f=ROOT/'results'/s/'ADAPTIVE_DAILY'/'METRICS.json'
        if f.exists():adapt.append(json.loads(f.read_text()))
    data['adaptive_extensions']=adapt
    cases=[];audits=[]
    for path in (ROOT/'results').glob('*/*/METRICS.json'):
        if path.parent.name=='adaptive_research':continue
        cases.append(json.loads(path.read_text()))
        audit=json.loads((path.parent/'AUDIT.json').read_text());audits.append(audit)
        frame=pd.read_csv(path.parent/'EVERY_TRADE_UTC.csv');day=pd.read_csv(path.parent/'EVERY_DAY.csv')
        if len(frame)!=audit['closed_trades_checked'] or not frame.UTC_day.is_unique or day.entries.max()>1 or day.entries.sum()!=len(frame):raise ValueError('Count integrity failure')
        if not audit['passed'] or not audit.get('first_exit_crossing_checked_independently'):raise ValueError('Incomplete audit')
    data['audits']=len(audits);data['audited_trades_across_separate_simulations']=sum(x['closed_trades_checked'] for x in audits)
    data['maximum_independent_daily_equity_error']=max(x['daily_equity_cash_flow_max_error'] for x in audits)
    data['any_tested_CAGR65_trade1000']=any(x['CAGR65_trade1000_pass'] for x in cases)
    data['any_tested_mean_annual65_trade1000']=any(x['arithmetic_annual65_trade1000_pass'] for x in cases)
    save(ROOT/'ASSESSMENT.json',data)
    pct=lambda x:f'{x*100:+.2f}%'
    report=['# V7: one daily IV-based trade on BTC and ETH','',
      'Project owner: Parrish Lyon. Historical simulation, not real account fills.','',
      '**Both scheduled primaries complete 1,826 trades: one trade on every UTC day of five calendar years. Each market independently exceeds 1,000 trades. No position is carried into the next day.**','',
      'Actual daily BTC/ETH DVOL is scaled to a one-day range using sqrt(365). A five-reading IV average is smoothing, not a five-day forecast. These are IV-derived range boundaries, not option-strike dealer walls.','',
      '## Five-year scheduled daily results','',
      '| Market | Trades | Skipped days | Five-year net | CAGR | Net WR | Worst full week | Longest losing-week streak |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in data['primaries']:report.append(f"| {r['symbol']} | {r['trades']} | {r['skipped_days']} | {pct(r['net_return'])} | {pct(r['cagr'])} | {r['win_rate']:.2%} | {pct(r['worst_complete_week'])} | {r['longest_losing_week_streak']} |")
    report+=['','Evaluation: 2021-09-01 to 2026-09-01 exclusive, 1,826 days. Each account begins with 10,000 USDT. Enter once at 00:02; stop, target or 23:59 scheduled exit; no second entry after an early exit.','',
      'BTC selected opening-movement continuation with historical mean one-day IV-normalized walls. ETH selected seven-day directional momentum with a five-observation mean of daily IV. Both use 2% planned equity risk and a 5x exposure cap, not 150x account exposure. These settings were selected on the pretest validation window; that window is short and the full calendar has prior project exposure.','',
      '## Five successive annual returns','', '| Market | Sep2021-Aug2022 | Sep2022-Aug2023 | Sep2023-Aug2024 | Sep2024-Aug2025 | Sep2025-Aug2026 | Arithmetic annual average |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for r in data['primaries']:report.append('| '+r['symbol']+' | '+' | '.join(pct(x) for x in r['anniversary_year_returns'])+' | '+pct(r['mean_anniversary_return'])+' |')
    report+=['','## Separate 250-week accounts','', '| Market | Days / trades | Net return | CAGR |','|---|---:|---:|---:|']
    for r in data['250week_primaries']:report.append(f"| {r['symbol']} | {r['calendar_days']} / {r['trades']} | {pct(r['net_return'])} | {pct(r['cagr'])} |")
    report+=['','250 weeks is 1,750 days, from 2021-11-15 to 2026-08-31 exclusive. It is not five calendar years. These are separate account reruns, not a suffix cut out of the five-year account.','',
      '## Wait for the wall: at most one entry per day','',
      '| Market | Completed trades | No-trade days | CAGR | Net WR |','|---|---:|---:|---:|---:|']
    for r in data['wall_only_primaries']:report.append(f"| {r['symbol']} | {r['trades']} | {r['skipped_days']} | {pct(r['cagr'])} | {r['win_rate']:.2%} |")
    report+=['','These are separate conditional rejection tests. Both exceed 1,000 trades, but do not pretend to enter on every day. All skipped days and their reason codes are exported.','',
      '## Additional prior-only adaptive selection','',
      'This extension was specified after viewing the fixed-policy results. Every seven UTC days, choose using at most126 prior fully matured daily returns, not current/future outcomes. Account equity does not reset. This is not a fresh untouched holdout.','',
      '| Market | Trades | CAGR | Five-year net |','|---|---:|---:|---:|']
    for r in adapt:report.append(f"| {r['symbol']} | {r['trades']} | {pct(r['cagr'])} | {pct(r['net_return'])} |")
    report+=['','## Cost controls','',
      'Base case: 5bps commission plus2bps adverse fill slippage per side, actual historical funding, prior-volume cap, order-grid assumptions and fixed1% maintenance. Costs are neither omitted nor blamed without a comparison.','',
      '| Market | Zero-fee/zero-slippage CAGR | User $5 round-trip equivalent CAGR |','|---|---:|---:|']
    for s in ['BTCUSDT','ETHUSDT']:
        rows=json.loads((ROOT/'results'/s/'STRESSES.json').read_text());z=next(x for x in rows if x['case']=='NO_FEE_NO_SLIPPAGE');u=next(x for x in rows if x['case']=='USER_5USD_ROUNDTRIP_EQUIVALENT')
        report.append(f"| {s} | {pct(z['cagr'])} | {pct(u['cagr'])} |")
    report+=['','The $5 case uses the quoted 9,895.212-USDT notional to derive a proportional round-trip commission and retains2bps slippage per side. Zero fees/slippage retains funding and price-grid rounding. Every case resimulates the compounded account.','',
      '**No tested daily case meets 65% CAGR or65% arithmetic average annual return with1,000 trades.**' if not data['any_tested_CAGR65_trade1000'] and not data['any_tested_mean_annual65_trade1000'] else 'Inspect the individual target gates in ASSESSMENT.json; passing a historical gate is not forward-profit certification.','',
      '## Evidence and limits','',
      f"All {len(audits)} published case audits passed, covering {data['audited_trades_across_separate_simulations']:,} trade rows across separate simulations. Maximum independently reconstructed daily-equity discrepancy: {data['maximum_independent_daily_equity_error']:.3g} USDT. Every trade has timestamps, initial IV/walls, size, fees, funding, P&L and a same-day exit. Every calendar day, including no-trade days, is present.",'',
      'The audits separately locate the earliest stop/target crossing in minute OHLC, verify IV availability before entry, prohibit duplicate daily entries and reconstruct account cash. Intraminute timestamps are bounded, not fabricated exact fills. Mark gaps, fee/impact/margin assumptions and prior research exposure remain limitations. The intrabar drawdown is a conservative bound; daily drawdown is also reported.','',
      'This addition is research only. Existing live-execution code and all original strategy/report folders remain unchanged. It does not establish a live profitable strategy. Read README.md and USERINSTRUCTIONS.md for definitions, exact inputs and reproduction.']
    (ROOT/'RESULTS.md').write_text('\n'.join(report)+'\n')
    return data

def main():
    p=argparse.ArgumentParser();p.add_argument('--zip-out',type=Path);a=p.parse_args();data=build()
    files=[x for x in ROOT.rglob('*') if x.is_file() and not any(t in x.relative_to(ROOT).parts for t in ['__pycache__','.pytest_cache','.venv','data']) and x.suffix not in ('.pyc','.nbi','.nbc') and x.name!='MANIFEST.json']
    manifest={str(x.relative_to(ROOT)):{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(files)};save(ROOT/'MANIFEST.json',manifest)
    if a.zip_out:
        a.zip_out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.zip_out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for f in sorted(files)+[ROOT/'MANIFEST.json']:z.write(f,'daily_iv_v7/'+str(f.relative_to(ROOT)))
        with zipfile.ZipFile(a.zip_out) as z:
            if z.testzip():raise ValueError('corrupt archive')
            for name,rec in manifest.items():
                if hashlib.sha256(z.read('daily_iv_v7/'+name)).hexdigest()!=rec['sha256']:raise ValueError('archive hash mismatch')
        print(json.dumps({'bytes':a.zip_out.stat().st_size,'sha256':sha(a.zip_out),'verified_files':len(manifest),'audits':data['audits'],'primary_trades':[x['trades'] for x in data['primaries']]},indent=2))

if __name__=='__main__':main()

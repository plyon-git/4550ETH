"""Aggregate actual results, enforce local-reproduction checks, and package evidence."""
from pathlib import Path
import argparse,json,hashlib,zipfile
import numpy as np,pandas as pd
from research import ROOT,write,EXPECTED,PERIODS
from bands import source_hash

def aggregate():
 rows=[];audits=[]
 for p in sorted((ROOT/'results').rglob('METRICS.json')):
  r=json.loads(p.read_text());r['path']=str(p.relative_to(ROOT));rows.append(r);a=json.loads((p.parent/'AUDIT.json').read_text());audits.append(a)
  if not a['passed']:raise ValueError('case audit failed')
  annual=r.get('annual_returns',[])
  if len(annual)==5:np.testing.assert_allclose(np.prod(1+np.asarray(annual)),1+r['net_return'],rtol=1e-9,atol=1e-8)
 if len(rows)!=127:raise ValueError('incomplete final/stress case set')
 checks={'ETHUSDT':(-.018895792475581374,450),'BTCUSDT':(-.9346330746135456,792),'XRPUSDT':(-.14506563827705543,371),'SPY':(-.1959039178662636,145)}
 primary=[]
 for sym in ['ETHUSDT','BTCUSDT','XRPUSDT','SPY','QQQ']:
  r=json.loads((ROOT/'results'/sym/'FROZEN.json').read_text())['primary']
  if r is None:continue
  name='PRIMARY_'+r['id']+('_risk'+str(r['risk']) if 'risk' in r else '');found=next(x for x in rows if x['symbol']==sym and x['name']==name);primary.append(found)
  if sym in ['ETHUSDT','BTCUSDT','XRPUSDT']:
   np.testing.assert_allclose(found['net_return'],checks[sym][0],rtol=1e-8,atol=1e-8)
   if found['trades']!=checks[sym][1]:raise ValueError('trade count differs from independent local run')
 keys=['symbol','name','net_return','cagr','average_annual_return','trades','win_rate','worst_week','conservative_intrabar_drawdown','max_drawdown_adverse_daily_path','longest_losing_streak','positive_anniversary_years','historical_65pct_cagr_gate','selection','path'];pd.DataFrame([{k:r.get(k) for k in keys} for r in rows]).to_csv(ROOT/'ALL_RESULTS.csv',index=False)
 quality=[]
 for s in ['ETH','BTC']:
  p=ROOT/'iv_data'/f'{s}_1D.csv';d=pd.read_csv(p)
  if len(d)!=1987 or d.timestamp.duplicated().any() or not np.all(np.diff(d.timestamp)==86400000):raise ValueError('IV coverage differs')
  quality.append({'symbol':s,'daily_observations':len(d),'start':pd.Timestamp(d.timestamp.iloc[0],unit='ms',tz='UTC').isoformat(),'last_candle':pd.Timestamp(d.timestamp.iloc[-1],unit='ms',tz='UTC').isoformat(),'sha256':source_hash(p)})
 models=list((ROOT/'results').glob('*/META/models/*.json'))
 for p in models:
  d=json.loads(p.read_text())
  if d['max_label_maturity_epoch']>d['cutoff_epoch']-86400:raise ValueError('label leakage')
 dev=sum(len(json.loads(p.read_text())) for p in (ROOT/'results').glob('*/DEVELOPMENT.json'));val=sum(len(json.loads(p.read_text())) for p in (ROOT/'results').glob('*/VALIDATION.json'))
 best=max([r for r in rows if r['trades']>=200 and not any(k in r['name'] for k in ['STRESS','NO_FEES','NO_COST','250W','UNVERIFIED'])],key=lambda x:x['cagr']);notional=3.6*2748.67;margin=notional/150
 write(ROOT/'FEE_ARITHMETIC.json',{'eth_quantity':3.6,'user_price':2748.67,'notional':notional,'initial_margin_at_150x':margin,'reported_cost_unverified':5,'cost_bps_notional':5/notional*10000,'cost_fraction_margin':5/margin,'cost_fraction_10000_equity':5/10000,'price_move_covering_5_total':5/3.6,'price_move_covering_5_each_side':10/3.6,'note':'Margin is not whole-account equity. Displayed loss may include spread/mark-to-market. No receipt establishes whether five dollars is fees or one-way/round-trip.'})
 assessment={'owner':'Parrish Lyon','status':'TARGET_NOT_ESTABLISHED' if not any(r['historical_65pct_cagr_gate'] for r in rows) else 'HISTORICAL_CANDIDATE_REQUIRES_REVIEW','target_cagr':.65,'minimum_trades':200,'periods':PERIODS,'reported_cases':len(rows),'audited_cases':len(audits),'summed_trade_rows_across_distinct_simulations':sum(a['trades'] for a in audits),'full_five_year_candle_minutes':2629440,'development_configurations':dev,'validation_cases':val,'model_artifacts':len(models),'actual_daily_IV':quality,'selected_primaries':primary,'best_after_cost_200trade_diagnostic':best,'target_passes_including_stresses':sum(bool(r['historical_65pct_cagr_gate']) for r in rows),'es_or_milk_exact_replication':False,'actual_broker_orders_submitted':False,'new_signals_integrated_into_live_runtime':False,'limitations':['Prior calendar research exposure and later extensions are disclosed.','IV expected-move bands are not dealer-inventory walls.','Exact ES intraday/options-chain wall history not supplied or tested.','SPY/QQQ daily OHLC diagnostics do not validate intraday execution.','Remaining mark gaps use modeled envelopes; depth and historical margin tiers are incomplete.','Fees are scenario assumptions, not a verified account tier.']}
 write(ROOT/'ASSESSMENT.json',assessment);write(ROOT/'VERIFICATION.json',{'audited_cases':len(audits),'trade_rows':sum(a['trades'] for a in audits),'max_independent_crypto_equity_error':max(a.get('max_equity_error',0.) for a in audits),'all_five_anniversary_returns_reconcile':True,'actual_daily_IV_continuous':True,'models_checked':len(models),'three_primary_results_match_independent_local_run':True,'no_actual_orders_submitted':True,'source_hashes':{str(p.relative_to(ROOT)):source_hash(p) for p in sorted((ROOT/'source').glob('*.py'))}})
 report=['# Volatility V5 results','','Owner: Parrish Lyon. Historical simulation; no live orders.','','**No tested case meets 65% CAGR plus 200 closed trades.**','',f'{dev:,} development configurations; {val:,} validation cases; {len(rows)} final/stress cases; {len(models)} numerical ML models. These are related experiments, not independent discoveries.','','Five calendar years: 2021-09-01 to 2026-09-01 exclusive, 1,826 days. Separate 250 weeks: 2021-11-15 to 2026-08-31, 1,750 days.','', '## Pre-evaluation selected cases','','| Market | Total net | CAGR | Trades | WR | Sep-to-Sep annual returns |','|---|---:|---:|---:|---:|---|']
 for r in primary:report.append(f"| {r['symbol']} | {r['net_return']*100:+.2f}% | {r['cagr']*100:+.2f}% | {r['trades']} | {r['win_rate']*100:.2f}% | "+', '.join(f'{x*100:+.2f}%' for x in r['annual_returns'])+' |')
 report+=['','SPY/QQQ are daily-candle diagnostics, not validated ES trades; their selected cases also miss the minimum trade count.','', '## Best after-cost diagnostic, not the selected primary','',f"{best['symbol']} / {best['name']}: {best['net_return']*100:+.2f}% cumulative, {best['cagr']*100:+.2f}% CAGR, {best['trades']} trades. Highlighted after seeing results, not a holdout-selected solution.",'', '## Actual IV and methodology','','BTC and ETH each have 1,987 continuous daily DVOL observations, 2021-03-24 through 2026-08-31. Use only completed, published IV candles; freeze session bands. RV/range proxies are separately labeled. Rolling prior26-week selection and mature-label ML filters were also evaluated. All trades, levels, available timestamps, models and period returns are retained.','', '## Fees and the supplied example','','3.6 ETH at 2,748.67 equals 9,895.212 notional, or 65.96808 initial margin at150x. Five dollars equals5.05295bps of notional,7.5794% of that margin, but0.05% of a10,000 account. Margin is not account equity. Whether five dollars is one-way or round-trip or includes spread was not verified.','','The ETH frozen primary has +6,387.479070 USDT gross price P&L, -6,291.336605 commissions and -285.100389 net funding: -188.957925 net. Gross price P&L already includes fill-price slippage. Its separate no-commission/no-slippage resimulation retains funding and returns+113.16% cumulative /+16.34%CAGR, still below65%. Changing costs changes later sizing/account state; this is not an identical trade path with only a column removed.','', '## Limits','','No proprietary Milk formula, dealer-position archive or exact ES entry sequence was replicated. Missing crypto marks use disclosed sensitivity values rather than invented observed prices. SPY/QQQ daily adverse-ordering assumptions cannot prove intraday fills. No V5 signal was armed for live trading; previous V4 execution and baseline are unchanged. The calendar is previously researched, and later extensions follow earlier results.','', 'Read README.md and docs/METHODOLOGY.md. Every case is in results/, with its specification, trades, timestamps, cost/funding accounting and independent audit.']
 (ROOT/'RESULTS.md').write_text('\n'.join(report)+'\n');return assessment

def package(out=None):
 files=[]
 for p in sorted(ROOT.rglob('*')):
  rel=p.relative_to(ROOT)
  if not p.is_file() or any(x in rel.parts for x in ['data','vendor','revisions','__pycache__','.pytest_cache','.venv']) or p.suffix in ['.pyc','.nbc','.nbi','.log'] or p.name=='MANIFEST.json':continue
  files.append(p)
 manifest={str(p.relative_to(ROOT)):{'sha256':source_hash(p),'bytes':p.stat().st_size} for p in files};write(ROOT/'MANIFEST.json',manifest)
 if out:
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for p in files+[ROOT/'MANIFEST.json']:z.write(p,'volatility_v5/'+str(p.relative_to(ROOT)))
  with zipfile.ZipFile(out) as z:
   if z.testzip():raise ValueError('archive corrupt')
   for rel,r in manifest.items():
    if hashlib.sha256(z.read('volatility_v5/'+rel)).hexdigest()!=r['sha256']:raise ValueError('packaged hash mismatch')
  return {'path':str(out),'sha256':source_hash(out),'bytes':Path(out).stat().st_size,'manifest_files_verified':len(manifest)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--zip',type=Path);a=p.parse_args();assessment=aggregate();receipt=package(a.zip);print(json.dumps({'status':assessment['status'],'cases':assessment['reported_cases'],'package':receipt},indent=2))

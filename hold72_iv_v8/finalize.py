"""Publish every V8 result, preserve failed gates, compare reference reproduction."""
from pathlib import Path
import argparse,hashlib,json,platform,zipfile
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):Path(p).write_text(json.dumps(d,indent=2,allow_nan=False,default=str)+'\n')
def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ['data','revisions','__pycache__','.pytest_cache','.venv']) and p.suffix not in ['.pyc','.nbc','.nbi','.log'] and p.name!='MANIFEST.json')
def main():
    p=argparse.ArgumentParser();p.add_argument('--zip-out',type=Path);p.add_argument('--verify-reference',action='store_true');a=p.parse_args()
    rows=[];audits=[];byname={}
    for f in sorted((ROOT/'results').rglob('METRICS.json')):
        d=json.loads(f.read_text());d['case']=str(f.parent.relative_to(ROOT/'results'));rows.append(d);byname[d['case']]=d
        check=json.loads((f.parent/'INDEPENDENT_AUDIT.json').read_text());tr=pd.read_csv(f.parent/'EVERY_TRADE_UTC.csv')
        assert check['passed'] and len(tr)==check['trades']==d['trades']
        assert (tr.hold_hours<=72).all() and tr.trade_id.is_unique
        if len(tr):assert (tr.target_price_R>=5-1e-9).all()
        audits.append(check)
    if len(audits)!=100:raise ValueError(f'Expected complete 100-case export, got {len(audits)}')
    reference={'ETHUSDT/PRIMARY_five_years':(-.008287822610488549,243),'BTCUSDT/PRIMARY_five_years':(.08101790980395895,201),
      'ETHUSDT/LEARNING/threshold0.5_risk0.04':(1.4624875643255195,363),'ETHUSDT/SIZING_DIAGNOSTICS/risk0.06_cap30.0':(2.6161752280307375,361)}
    if a.verify_reference:
        for name,(ret,n) in reference.items():
            np.testing.assert_allclose(byname[name]['net_return'],ret,rtol=1e-9,atol=1e-9)
            assert byname[name]['trades']==n
    models=[]
    for f in (ROOT/'results').glob('*/LEARNING/models/*.json'):
        doc=json.loads(f.read_text());assert doc['last_label_maturity_ms']<=doc['training_cutoff_ms']
        models.append({'path':str(f.relative_to(ROOT)),'sha256':sha(f),'cutoff_ms':doc['training_cutoff_ms'],'samples':doc['candidate_samples']})
    save(ROOT/'MODEL_INVENTORY.json',models)
    pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(list,dict))} for r in rows]).to_csv(ROOT/'ALL_CASES.csv',index=False)
    selected=[byname[s+'/PRIMARY_five_years'] for s in ['BTCUSDT','ETHUSDT']]
    highlighted=byname['ETHUSDT/LEARNING/threshold0.5_risk0.04'];sizing=byname['ETHUSDT/SIZING_DIAGNOSTICS/risk0.06_cap30.0']
    learned=[byname[s+'/LEARNING/PRIMARY'] for s in ['BTCUSDT','ETHUSDT']]
    comparable=[r for r in rows if r['days']==1826 and '/STRESS_' not in r['case'] and not any(w in r['case'] for w in ['hold24','hold48','zero_cost','double_cost','delay2m','no_extra'])]
    summary=dict(owner='Parrish Lyon',period={'start':'2021-09-01T00:00:00Z','end_exclusive':'2026-09-01T00:00:00Z','days':1826},
        requested=dict(max_hold_hours=72,initial_target_R=5,nominal_contract_leverage=30,daily_and_weekly_iv=True,annual_return_goal=.45),
        study='Frozen fixed-rule selection plus separately labeled walk-forward and post-test sizing diagnostics.',
        fixed_primaries=selected,predeclared_learned_primaries=learned,highlighted_diagnostic_not_selected_primary=highlighted,
        highest_after_cost_CAGR_post_sizing_diagnostic=sizing,
        base_cost_cases_cagr45_count=sum(r['cagr']>.45 for r in comparable),
        base_cost_cases_arithmetic_mean45_count=sum(r['mean_annual'] is not None and r['mean_annual']>.45 for r in comparable),
        base_cost_cases_cagr45_and_all_years_positive_count=sum(r['cagr']>.45 and r['positive_years']==5 for r in comparable),
        models=len(models),audited_case_count=len(audits),live_orders=False,
        limits=['Full fixed-policy 5-year diagnostic includes first two years used in selection; separate 3-year account replay is reported.',
        'All calendars have earlier project exposure. ML extension follows fixed-policy result exposure; threshold0.25/risk1% is its predeclared primary; highlighted threshold0.5/risk4% is a hindsight diagnostic.',
        'Sizing extension is subsequent sensitivity, not validation. Three losing years make arithmetic averages misleading as consistent annualized performance.',
        'Daily/weekly model ranges use daily 30-day-tenor DVOL. They are not strike-OI/dealer-position walls or separate 1D/7D-tenor IV.',
        'Thirty times is the nominal contract setting. Additional initial isolated collateral is modeled when necessary; maximum notional/equity is a separately reported risk cap.',
        'Maintenance margin, slippage, fee tiers and volume limits are modeling assumptions; remaining mark gaps have disclosed hypothetical bounds.',
        'No daily entry quota. The earlier 1000-trade preference is reported separately; highlighted cases do not meet it.',
        'One open position at a time; no pyramiding, no averaging down, no equity reset between model refits. V4 live service is unchanged and V8 was not armed.'])
    save(ROOT/'ASSESSMENT.json',summary)
    verification=dict(case_audits=len(audits),all_passed=True,trade_rows_across_separate_accounts=sum(x['trades'] for x in audits),
       max_reconstructed_daily_equity_error=max(x['max_daily_equity_error'] for x in audits),model_artifacts=len(models),all_model_labels_mature=True,
       max_traded_hold_hours=max(x['max_hold_hours'] for x in audits),all_initial_target_R5=True,source_platform=platform.platform(),
       reference_comparison_requested=a.verify_reference,live_orders_submitted=False)
    save(ROOT/'VERIFICATION.json',verification)
    fmt=lambda x:f'{x*100:+.2f}%'
    lines=['# V8: daily/weekly IV, overnight carry, 72h, 5R, 30x','',
      'Owner: Parrish Lyon. Hypothetical historical executions, not authenticated live fills.','',
      '**No base-cost case established CAGR above 45%. Some arithmetic averages exceed 45% because one strong year offsets several losing years.**','',
      '## Matched ETH holding-limit comparison','',
      'Same fixed 5R target, threshold 0.5, 4% planned risk, 5x account exposure cap and 30x nominal contract setting with a collateral reserve. Models and entry candidates are unchanged; account paths are rerun. This is a hindsight-highlighted diagnostic, not the predeclared primary.','',
      '| Hold | Five-year net | CAGR | Mean annual return | Trades | Drawdown bound |','|---|---:|---:|---:|---:|---:|']
    for label,k in [('24h','ETHUSDT/SIZING_DIAGNOSTICS/hold24'),('48h','ETHUSDT/SIZING_DIAGNOSTICS/hold48'),('72h','ETHUSDT/LEARNING/threshold0.5_risk0.04')]:
        r=byname[k];lines.append(f"| {label} | {fmt(r['net_return'])} | {fmt(r['cagr'])} | {fmt(r['mean_annual'])} | {r['trades']} | {r['conservative_drawdown']:.2%} |")
    lines+=['','## Five annual periods','','| Period | Net return |','|---|---:|']
    for year,r in zip(range(2021,2026),highlighted['annual_returns']):lines.append(f'| Sep {year} to Aug {year+1} | {fmt(r)} |')
    lines+=['',f"Arithmetic mean {fmt(highlighted['mean_annual'])} is not CAGR {fmt(highlighted['cagr'])}. Three years lose. Net WR {highlighted['win_rate']:.2%}; worst week {fmt(highlighted['worst_week'])}; longest losing streak {highlighted['longest_losing_weeks']} weeks. {highlighted['trades_carried_overnight']} of {highlighted['trades']} trades cross midnight. This falls short of the earlier 1000-trade requirement.",'',
      '## Selected primaries','','| Study | Market | CAGR | Five-year net | Trades |','|---|---|---:|---:|---:|']
    for r in selected+learned:
        lines.append(f"| {'Walk-forward primary' if '/LEARNING/' in r['case'] else 'Validation-selected fixed primary'} | {r['case'].split('/')[0]} | {fmt(r['cagr'])} | {fmt(r['net_return'])} | {r['trades']} |")
    lines+=['',f"Subsequent ETH sizing raised the highest after-cost CAGR to {fmt(sizing['cagr'])}, with mean annual {fmt(sizing['mean_annual'])}, {sizing['trades']} trades and {sizing['conservative_drawdown']:.2%} drawdown. It uses 6% planned risk and a 30x account cap; actual peak exposure is {sizing['max_exposure']:.3f}x. Only {sizing['positive_years']} years are positive. Not a validated or selected primary.",'',
      '## Fragility checks on ETH 4%-risk diagnostic','','| Scenario | CAGR | Five-year net | Modeled liquidations |','|---|---:|---:|---:|']
    for label in ['30x_no_extra_collateral','zero_cost','double_cost','delay2m']:
        r=byname['ETHUSDT/SIZING_DIAGNOSTICS/'+label];lines.append(f"| {label} | {fmt(r['cagr'])} | {fmt(r['net_return'])} | {r['liquidations']} |")
    lines+=['','Base costs: 5bps commission and 2bps adverse slippage per side, funding, grids and 1% prior-minute volume cap. Zero cost retains funding and grids. Two additional minutes of entry delay make the highlighted case negative. No robust live edge is established.','',
      '## Method and verification','',
      'Daily ranges freeze after previous daily DVOL close plus a modeled one-minute publication allowance. Weekly ranges freeze Monday after 00:01 using the preceding Sunday close and known IV. Use sqrt(1/365) and sqrt(7/365) scaling. These are model range estimates, not dealer gamma walls or separate 1D/7D-tenor options histories.','',
      'Rejection, break and recent-bar retest signals use completed 15m/1h bars and next-minute entries. Stops are known before entry; targets are five times initial price risk and do not repaint. Maximum hold is 72 hours from entry, not midnight. No averaging down or pyramiding.','',
      'Development Sep2021-Aug2022 and validation Sep2022-Aug28 2023 precede a purged three-year test. Full five-year diagnostics include those selection years. ML refits every 13 weeks using at most 730 prior days of fully matured candidate labels. Labels overlap. Prior project exposure and subsequent extensions are disclosed.','',
      'Initial margin is notional/30. Additional isolated collateral is reserved when needed for the planned stop plus maintenance/funding/buffer. That is a model allocation, not a claim the exchange automatically adds margin. Exact account brackets and margin/latency must be verified separately.','',
      f"All {len(audits)} case audits passed. {len(models)} saved models have mature training labels. Every trade, daily equity and annual/monthly/weekly/rolling-year result is retained. Independent checks reconstruct cash, margin quantities and daily equity, and reject missed earlier stop/target crossings. Intraminute timestamps are bounds; mark gaps use disclosed sensitivity values, not invented observations.",'',
      'The original 45.50% program and V4 live service remain unchanged. V8 is not armed for live orders. Read USERINSTRUCTIONS.md and ASSESSMENT.json.']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    manifest={str(f.relative_to(ROOT)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in files()};save(ROOT/'MANIFEST.json',manifest)
    if a.zip_out:
        a.zip_out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.zip_out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for f in files():z.write(f,'hold72_iv_v8/'+str(f.relative_to(ROOT)))
            z.write(ROOT/'MANIFEST.json','hold72_iv_v8/MANIFEST.json')
        with zipfile.ZipFile(a.zip_out) as z:
            if z.testzip():raise ValueError('ZIP corruption')
            for name,v in manifest.items():assert hashlib.sha256(z.read('hold72_iv_v8/'+name)).hexdigest()==v['sha256']
        print(json.dumps(dict(file=str(a.zip_out),sha256=sha(a.zip_out),bytes=a.zip_out.stat().st_size,manifest_files=len(manifest),verification=verification),indent=2))
if __name__=='__main__':main()

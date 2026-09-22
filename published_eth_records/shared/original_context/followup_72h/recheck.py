"""Parrish Lyon: replay the interrupted V8 study and test both $5 fee interpretations.
No trading-account access or order calls. Existing strategy, models and ledgers remain unchanged.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, zipfile
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from core import Execution, LEDGER, load_market, run, stats
from learning import choose
from research import boundary, PERIODS
from report import audit, publish

SOURCE_COMMIT='4ff2d40b51ce152d34175318a9d1c30184509a60'

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''): h.update(part)
    return h.hexdigest()

def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')

def verify_original_exports():
    """Use independent Pandas/accounting arithmetic, not the simulation summary helper."""
    manifest=json.loads((ROOT/'MANIFEST.json').read_text())
    for name,rec in manifest.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()):raise ValueError('unsafe manifest path')
        if digest(path)!=rec['sha256'] or path.stat().st_size!=rec['bytes']:
            raise ValueError('Frozen source/evidence identity mismatch: '+name)
    checked=[];total=0
    for mp in sorted((ROOT/'results').rglob('METRICS.json')):
        folder=mp.parent;t=pd.read_csv(folder/'EVERY_TRADE_UTC.csv')
        d=pd.read_csv(folder/'DAILY_EQUITY.csv',index_col=0,parse_dates=True).equity
        saved=json.loads(mp.read_text())
        np.testing.assert_allclose(d.iloc[0]+t.net_pnl.cumsum(),t.equity_after,rtol=1e-10,atol=1e-7)
        np.testing.assert_allclose(t.gross_pnl-t.entry_fee-t.exit_fee-t.funding_paid,t.net_pnl,rtol=1e-10,atol=1e-7)
        gain=d.iloc[-1]/d.iloc[0]-1
        years=(d.index[-1]-d.index[0]).total_seconds()/(365.2425*86400)
        np.testing.assert_allclose([gain,(1+gain)**(1/years)-1],[saved['net_return'],saved['cagr']],rtol=1e-10,atol=1e-10)
        entry=pd.to_datetime(t.entry_utc,utc=True);exit=pd.to_datetime(t.exit_bar_open_utc,utc=True)
        assert ((exit-entry).dt.total_seconds()<=72*3600).all()
        assert (entry.iloc[1:].to_numpy()>exit.iloc[:-1].to_numpy()).all()
        assert (pd.to_datetime(t.daily_iv_available_utc,utc=True)<=entry).all()
        assert (pd.to_datetime(t.weekly_iv_available_utc,utc=True)<=entry).all()
        assert np.array_equal(t.trade_id,np.arange(1,len(t)+1))
        assert len(t)==saved['trades']
        np.testing.assert_allclose((t.net_pnl>0).mean(),saved['win_rate'],rtol=1e-10,atol=1e-10)
        annual=[]
        for i in range(5):
            left=d.index[0]+pd.DateOffset(years=i);right=d.index[0]+pd.DateOffset(years=i+1)
            if left in d.index and right in d.index:annual.append(d.loc[right]/d.loc[left]-1)
        np.testing.assert_allclose(annual,saved['annual_returns'],rtol=1e-10,atol=1e-10)
        checked.append({'case':str(folder.relative_to(ROOT)),'trades':len(t),'passed':True})
        total+=len(t)
    models=[]
    for path in sorted((ROOT/'results').glob('*/LEARNING/models/*.json')):
        doc=json.loads(path.read_text())
        assert doc['last_label_maturity_ms']<=doc['training_cutoff_ms']
        assert len(doc['trees'])==100
        models.append({'model':str(path.relative_to(ROOT)),'sha256':digest(path),'labels_mature':True})
    assert len(checked)==100 and total==34154 and len(models)==42
    return {'original_files_hash_verified':len(manifest),'original_exported_cases':len(checked),
            'original_trade_rows_checked':total,'model_artifacts_checked':len(models),
            'case_checks':checked,'model_checks':models}

def scenarios():
    c=replace(Execution(),risk=.04)
    rows=[
      ('matched_hold24',replace(c,max_hold_hours=24),'results/ETHUSDT/SIZING_DIAGNOSTICS/hold24'),
      ('matched_hold48',replace(c,max_hold_hours=48),'results/ETHUSDT/SIZING_DIAGNOSTICS/hold48'),
      ('matched_hold72',c,'results/ETHUSDT/LEARNING/threshold0.5_risk0.04'),
      ('highest_cagr_risk6_cap30',replace(c,risk=.06,cap=30.),'results/ETHUSDT/SIZING_DIAGNOSTICS/risk0.06_cap30.0'),
      ('nominal30_no_extra_collateral',replace(c,funded_collateral=False),'results/ETHUSDT/SIZING_DIAGNOSTICS/30x_no_extra_collateral'),
      ('zero_fee_zero_slippage',replace(c,fee_bps=0,slip_bps=0),'results/ETHUSDT/SIZING_DIAGNOSTICS/zero_cost'),
      ('double_cost',replace(c,fee_bps=10,slip_bps=4),'results/ETHUSDT/SIZING_DIAGNOSTICS/double_cost'),
      ('two_additional_minutes_delay',replace(c,delay_minutes=2),'results/ETHUSDT/SIZING_DIAGNOSTICS/delay2m')]
    quoted_bps=5/(3.6*2748.67)*10000
    for interpretation,factor in [('roundtrip',.5),('oneway',1.)]:
        rows.append(('user5_usd_'+interpretation+'_equivalent',replace(c,fee_bps=quoted_bps*factor),None))
    low=replace(c,risk=.06,cap=30.,fee_bps=quoted_bps/2)
    rows += [('user5_usd_roundtrip_risk6_cap30',low,None),
             ('user5_usd_oneway_risk6_cap30',replace(low,fee_bps=quoted_bps),None),
             ('roundtrip_risk6_cap30_delay1m',replace(low,delay_minutes=1),None),
             ('roundtrip_risk6_cap30_delay2m',replace(low,delay_minutes=2),None),
             ('roundtrip_risk6_cap30_no_extra_collateral',replace(low,funded_collateral=False),None)]
    return rows

def report_text(rows,verification):
    by={r['name']:r for r in rows}
    def pct(v):return f'{v*100:+.2f}%'
    lines=['# V8 interrupted-run recovery and 72-hour follow-up','',
    'Owner: Parrish Lyon. Original source commit: `'+SOURCE_COMMIT+'`. No live orders.',
    '',
    '**72 hours improves the highlighted ETH account, but the result is not a consistent 45% compound-return system.** The original 4%-risk diagnostic averages +55.83% across five annual periods while compounding at +19.75%. These are different measures.',
    '',
    'The full five-year window is 2021-09-01 to 2026-09-01 exclusive. Each account starts at 10,000 USDT. All entry candidates/model weights are fixed from the original V8 run; changing the holding limit does not retrain the 72-hour-label models. This is a matched execution sensitivity, not a new validation exercise.',
    '',
    '## Holding-limit comparison','',
    '| Hold | Five-year net | CAGR | Mean of five annual returns | Trades | Drawdown bound |',
    '|---|---:|---:|---:|---:|---:|']
    for hours in [24,48,72]:
        x=by['matched_hold'+str(hours)]['metrics']
        lines.append(f"| {hours}h | {pct(x['net_return'])} | {pct(x['cagr'])} | {pct(x['mean_annual'])} | {x['trades']} | {x['conservative_drawdown']:.2%} |")
    lines += ['','All three rows have nominal 30x leverage, a 5x account-exposure cap, a 5R initial target, 4% planned risk and extra collateral reserved when required. The 72-hour case is a hindsight-highlighted diagnostic, not the predeclared primary.',
    '','## Higher-risk fee sensitivity','',
    'The user quoted $5 on 3.6 ETH at 2,748.67, or 9,895.212 USDT notional. Its one-way/round-trip interpretation was not verified. A $5 round-trip commission implies 2.5264744 bps per side; $5 one-way implies 5.0529488 bps per side. Both scenarios additionally retain 2 bps adverse slippage per side. Fees are proportional to each trade notional, not a flat $5 per trade.',
    '',
    '| 72h / 6% planned risk / 30x account cap | CAGR | Mean annual | Five-year net | Trades | Drawdown bound |',
    '|---|---:|---:|---:|---:|---:|']
    for name,label in [('highest_cagr_risk6_cap30','Base 5bps commission per side'),
                       ('user5_usd_oneway_risk6_cap30','$5 one-way equivalent'),
                       ('user5_usd_roundtrip_risk6_cap30','$5 full-round-trip equivalent')]:
        x=by[name]['metrics']
        lines.append(f"| {label} | {pct(x['cagr'])} | {pct(x['mean_annual'])} | {pct(x['net_return'])} | {x['trades']} | {x['conservative_drawdown']:.2%} |")
    x=by['user5_usd_roundtrip_risk6_cap30']['metrics']
    lines += ['',
    f"**The lower-fee scenario crosses 45% CAGR at {pct(x['cagr'])}, but that commission assumption is unverified and its settings were highlighted after evaluation.** Peak actual exposure is {x['max_exposure']:.3f}x account equity, not constant 30x. Worst week is {pct(x['worst_week'])}; {x['positive_years']} of five years are positive. It is not a validated strategy or a performance guarantee.",
    '',
    '| Annual period | Original 4%-risk / base cost | 6%-risk / lower assumed fee |',
    '|---|---:|---:|']
    base=by['matched_hold72']['metrics']
    for j,(av,bv) in enumerate(zip(base['annual_returns'],x['annual_returns'])):
        lines.append(f'| Sep {2021+j} to Aug {2022+j} | {pct(av)} | {pct(bv)} |')
    lines += ['','## Delay and collateral fragility','',
    '| Lower-fee, 6%-risk scenario | CAGR | Modeled liquidations |',
    '|---|---:|---:|']
    for name,label in [('user5_usd_roundtrip_risk6_cap30','Baseline entry timing'),
                       ('roundtrip_risk6_cap30_delay1m','One additional minute delay'),
                       ('roundtrip_risk6_cap30_delay2m','Two additional minutes delay'),
                       ('roundtrip_risk6_cap30_no_extra_collateral','No extra isolated collateral')]:
        v=by[name]['metrics']
        lines.append(f"| {label} | {pct(v['cagr'])} | {v['liquidations']} |")
    lines += ['',
    'The lower-fee result does not remain above 45% with those extra delays. A 30x initial-margin setting is not sufficient collateral for every wide stop; extra collateral is an explicit model assumption, not a claim the exchange adds it automatically. Model margin/maintenance and remaining mark gaps are not an exchange liquidation certificate.',
    '',
    '## Integrity and scope','',
    f"All {verification['original_exported_cases']} original exported cases and {verification['original_trade_rows_checked']:,} trade rows were rechecked by separate Pandas cash/annual-return arithmetic. All {verification['original_files_hash_verified']} original manifest identities and {verification['model_artifacts_checked']} model maturity records passed. Eight reference simulations reproduce every raw trade and daily equity value. Seven new fee/execution sensitivities are independently audited against minute inputs. Existing strategy files, parameters and model weights are unchanged.",
    '',
    'Complete timestamped trades, initial levels, 5R target, margin, fees, funding, account equity, holding time and every annual/monthly/weekly return are under `results/`. No winners or losing years are omitted. The highlighted cases have 361-363 trades, below the earlier 1,000-trade preference; relaxing daily entries does not manufacture more independent trades.',
    '',
    'Original fixed-policy five-year diagnostics include two selection years. Walk-forward models use matured labels, but the overall calendar and subsequent threshold/risk/fee choices have research exposure. No untouched holdout or live validation is claimed. Daily and weekly boundaries use daily observations of annualized 30-day DVOL, not actual 1D/7D option chains or dealer gamma walls. The original V4 live service remains unchanged and unarmed with V8.',
    '',
    'Reproduce from the repository root after obtaining the V4 ETH market input:',
    '',
    '```sh',
    'python hold72_iv_v8/followup_72h/recheck.py --data /path/to/ETHUSDT/aligned_repaired.npz',
    '```',
    '',
    'No credentials are needed. The supplied source refuses altered baseline identities and unexpected data hashes. All outputs are historical simulations.']
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--out',type=Path,default=HERE/'results')
    p.add_argument('--zip-out',type=Path)
    args=p.parse_args()
    verification=verify_original_exports()
    ts,m,missing=load_market(args.data,'ETHUSDT')
    with np.load(ROOT/'results/ETHUSDT/LEARNING/PREDICTIONS.npz',allow_pickle=False) as z:
        candidates=z['candidates'];predictions=z['prediction']
    signals,chosen=choose(candidates,predictions,.5)
    a,b=boundary(ts,PERIODS['five_years'])
    records=[]
    for name,cfg,ref in scenarios():
        out=run(m,missing,signals,a,b,cfg,'ETHUSDT',True)
        if ref:
            trades=pd.read_csv(ROOT/ref/'EVERY_TRADE_UTC.csv')
            eq=pd.read_csv(ROOT/ref/'DAILY_EQUITY.csv')
            np.testing.assert_allclose(out[1],trades[list(LEDGER)],rtol=1e-11,atol=1e-7)
            np.testing.assert_allclose(out[0],eq.equity,rtol=1e-11,atol=1e-7)
        met=publish(args.out/name,out,m,missing,ts,signals,a,b,cfg,'ETHUSDT',
           {'purpose':'matched_replay_or_fee_sensitivity_not_new_validation','source_commit':SOURCE_COMMIT,
            'known_reference':ref,'threshold':.5,'verified_venue_fee':False})
        check=json.loads((args.out/name/'INDEPENDENT_AUDIT.json').read_text())
        records.append({'name':name,'reference_ledger_and_daily_equity_matched':ref is not None,
           'new_fee_sensitivity':ref is None,'metrics':met,'audit':check,'execution':asdict(cfg)})
        print(name,met['cagr'],met['mean_annual'],met['trades'],flush=True)
    # Cross-runtime verification of this separately executed follow-up, not optimization to these numbers.
    known={'matched_hold72':.19752315174111512,'highest_cagr_risk6_cap30':.29319163456280406,
           'user5_usd_roundtrip_risk6_cap30':.46049838972058876,
           'user5_usd_oneway_risk6_cap30':.29008755468220393,
           'roundtrip_risk6_cap30_delay1m':.2747904403134671,
           'roundtrip_risk6_cap30_delay2m':.1766993645484598}
    for rec in records:
        if rec['name'] in known:np.testing.assert_allclose(rec['metrics']['cagr'],known[rec['name']],rtol=1e-10,atol=1e-10)
    verification.update(source_commit=SOURCE_COMMIT,replayed_cases=len(records),reference_full_trade_series_matches=8,
                        new_fee_and_execution_sensitivities=7,live_orders=False,verified_venue_fee=False,
                        market_input_sha256=digest(args.data),
                        predictions_sha256=digest(ROOT/'results/ETHUSDT/LEARNING/PREDICTIONS.npz'))
    save(HERE/'REPLAY_RESULTS.json',records)
    save(HERE/'VERIFICATION.json',verification)
    (HERE/'RESULTS.md').write_text(report_text(records,verification))
    manifest={str(f.relative_to(HERE)):{'sha256':digest(f),'bytes':f.stat().st_size}
              for f in sorted(HERE.rglob('*')) if f.is_file() and '__pycache__' not in f.parts
              and f.suffix not in ('.pyc','.nbc','.nbi') and f.name!='MANIFEST.json'}
    save(HERE/'MANIFEST.json',manifest)
    if args.zip_out:
        args.zip_out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(args.zip_out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name in [*manifest,'MANIFEST.json']:z.write(HERE/name,'followup_72h/'+name)
        with zipfile.ZipFile(args.zip_out) as z:
            if z.testzip():raise ValueError('corrupt archive')
            for name,rec in manifest.items():
                if hashlib.sha256(z.read('followup_72h/'+name)).hexdigest()!=rec['sha256']:raise ValueError('archive hash mismatch')
    print(json.dumps({k:v for k,v in verification.items() if k not in ('case_checks','model_checks')},indent=2))
if __name__=='__main__':main()

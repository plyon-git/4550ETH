"""Publish exact Parrish Lyon ETH records without changing their source or results.
The whole minute input is committed as ordered binary chunks and included in ZIP.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile
SOURCE_COMMIT='2d070ea62f847b944f538fb4a6e9073b109b8549'
DATA_SHA='b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d'
CASES=[('564.37','followup_72h/results/user5_usd_roundtrip_risk6_cap30',5.643695278817943,362),
       ('261.62','results/ETHUSDT/SIZING_DIAGNOSTICS/risk0.06_cap30.0',2.6161752280307375,361)]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def make(source,data,out):
    if sha(data)!=DATA_SHA:raise ValueError('Wrong historical data')
    if (out/'CATALOG.json').exists():raise ValueError('Publication already exists; refusing replacement')
    original=source/'hold72_iv_v8';mapping={}
    def copy(path,rel):
        dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        mapping[str(rel)]={'original_repository_path':str(path.relative_to(source)),
                          'source_commit':SOURCE_COMMIT,'sha256':sha(path),'bytes':path.stat().st_size}
    paths=list(original.glob('*.py'))+[original/'requirements.txt']
    paths+=list((original/'tests').glob('*.py'))+list((original/'context/iv_data').glob('*'))
    learning=original/'results/ETHUSDT/LEARNING'
    paths += [p for p in learning.iterdir() if p.is_file()] + list((learning/'models').glob('*.json'))
    paths += [p for p in (original/'results/ETHUSDT').iterdir() if p.is_file()]
    for p in sorted(set(paths)):copy(p,Path('shared/frozen_v8')/p.relative_to(original))
    for name in ('README.md','RESULTS.md','USERINSTRUCTIONS.md','ASSESSMENT.json','MODEL_INVENTORY.json','VERIFICATION.json','MANIFEST.json'):
        copy(original/name,Path('shared/original_context')/name)
    for name in ('recheck.py','RESULTS.md','REPLAY_RESULTS.json','VERIFICATION.json','MANIFEST.json'):
        copy(original/'followup_72h'/name,Path('shared/original_context/followup_72h')/name)
    copy(source/'OWNERSHIP.md',Path('OWNERSHIP.md'))
    provenance=source/'execution_v4/data_provenance/ETHUSDT'
    if provenance.exists():
        for p in provenance.iterdir():
            if p.is_file():copy(p,Path('shared/data_provenance/ETHUSDT')/p.name)
    records=[]
    for ident,rel,gain,trades in CASES:
        path=original/rel;met=json.loads((path/'METRICS.json').read_text());par=json.loads((path/'PARAMETERS.json').read_text())
        if abs(met['net_return']-gain)>1e-12 or met['trades']!=trades:raise ValueError('Unexpected source result')
        folder=f"ETHUSDT_{ident}pct_5Y_20210901-20260901_WR{100*met['win_rate']:.2f}pct_RR5"
        for p in path.iterdir():
            if p.is_file():copy(p,Path(folder)/p.name)
        cfg=par['actual_execution']
        info={'id':ident,'folder':folder,'source_record':str(path.relative_to(source)),
              'source_commit':SOURCE_COMMIT,'cumulative_return_percent':met['net_return']*100,
              'cagr_percent':met['cagr']*100,'win_rate_percent':met['win_rate']*100,'trades':trades,
              'initial_target_rr':5,'maximum_hold_hours':72,'nominal_contract_leverage':30,
              'fee_bps_per_side':cfg['fee_bps'],'fee_verified_for_live_account':False,
              'state':'frozen_historical_diagnostic_not_live_certified'}
        records.append(info)
        notes='The unverified $5-complete-round-trip commission interpretation at 9,895.212 USDT notional.' if ident=='564.37' else 'Original base-cost sizing diagnostic: 5bps commission per side.'
        (out/folder/'README.md').write_text(f'''# ETHUSDT +{ident}% five-year record

Project-specific owner: **Parrish Lyon**. Frozen original source commit: `{SOURCE_COMMIT}`.

**{ident}% is cumulative, not annual.** Period: 2021-09-01 00:00 UTC through 2026-09-01 00:00 UTC exclusive, 1,826 days / 260 complete Monday weeks plus boundary days.

| Metric | Exact archived case |
|---|---:|
| Net cumulative return | {100*met['net_return']:.8f}% |
| CAGR | {100*met['cagr']:.8f}% |
| Closed trades | {trades} |
| Net win rate | {100*met['win_rate']:.8f}% |
| Initial / final equity | {met['initial']:.2f} / {met['final']:.8f} USDT |
| Configured initial target | 5R |
| Maximum holding period | 72 hours |
| Nominal leverage | 30x |
| Planned account risk / exposure cap | 6% / 30x |
| Actual peak exposure | {met['max_exposure']:.8f}x |
| Conservative modeled drawdown | {100*met['conservative_drawdown']:.8f}% |
| Worst full week | {100*met['worst_week']:.8f}% |
| Commission per side | {cfg['fee_bps']:.10f} bps |

{notes} Both fee cases additionally retain 2bps adverse slippage per side and historical funding. The paths and trade counts differ because costs change account equity and later sizing.

## Files and execution

`EVERY_TRADE_UTC.csv` contains all winners and losers, UTC entry/exit bounds, prices, stop/5R target, quantity, fees, funding, P&L, balances, margin/collateral and IV availability. Annual, monthly, weekly, rolling-year and daily-equity reports are original unchanged records. `PARAMETERS.json` is the original exact configuration.

All original source, candidate policies, 21 fitted ETH models, features, forecasts, IV data, training and historical execution are in `../shared/frozen_v8/`. All 201,104,903 bytes of the historical minute input are in the ordered checksum-verified parts in `../shared/data/`. The published `MINUTE_EQUITY_RECONSTRUCTED.csv.gz` independently reconstructs every evaluation minute from the frozen trades. Original mark gaps remain flagged.

From this folder, after installing Python 3.13:

```sh
python -m pip install -r ../shared/frozen_v8/requirements.txt
python reproduce.py --verify-models --retrain --minute-equity
```

This reconstructs the exact input automatically, verifies the original files, rebuilds every model forecast, retrains original folds without retuning, and matches all ledger fields, daily equity values, metrics and annual returns. Outputs go to the parent `reproduced/` folder, never over the original records. No network is required after dependencies and the complete publication are available.

## Scope retained

This is a hindsight-highlighted historical diagnostic, not an untouched holdout or an authenticated live account. Fees, slippage, margin, collateral and market impact are assumptions. One exposed minute has missing original mark data handled by a disclosed sensitivity bound. A 5R target does not guarantee a 5R realized payoff. The trade count does not meet the earlier 1,000 preference.

Publishing does not arm the V4 live service or implement an online V8 broker integration. The frozen training and historical-execution code is functional; original V4 and earlier research are unchanged. See the parent README and original context for the complete recorded limitations. Third-party rights remain applicable.
''')
        (out/folder/'reproduce.py').write_text("\"\"\"Replay this immutable historical record, never a live order.\"\"\"\nfrom pathlib import Path\nimport subprocess,sys\nroot=Path(__file__).resolve().parent.parent\nraise SystemExit(subprocess.call([sys.executable,str(root/'reproduce.py'),'--case',"+repr(ident)+"]+sys.argv[1:]))\n")
        save(out/folder/'PUBLICATION.json',info)
    d=out/'shared/data';d.mkdir(parents=True,exist_ok=True);parts=[]
    with data.open('rb') as stream:
        i=0
        while block:=stream.read(40*1024*1024):
            name=f'ETHUSDT_aligned_repaired.npz.part{i:03d}';(d/name).write_bytes(block)
            parts.append({'filename':name,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()});i+=1
    save(d/'DATA_MANIFEST.json',{'filename':'aligned_repaired.npz','sha256':DATA_SHA,'bytes':data.stat().st_size,
        'parts':parts,'reconstruction':'Concatenate in exact manifest order; verify the full SHA-256.',
        'source_release':'v4-research-20260922','source_asset':'ETHUSDT_aligned_repaired.npz',
        'source_url':'https://github.com/plyon-git/4550ETH/releases/download/v4-research-20260922/ETHUSDT_aligned_repaired.npz',
        'price_mark_funding_input':True,'missing_mark_values_preserved':True})
    save(out/'SOURCE_MAP.json',{'source_commit':SOURCE_COMMIT,'files':mapping})
    save(out/'CATALOG.json',{'owner':'Parrish Lyon','source_commit':SOURCE_COMMIT,'cases':records,
         'shared_data_sha256':DATA_SHA,'raw_input_stored_in_git_parts':True,'live_orders_submitted':False})
    (out/'.gitignore').write_text('__pycache__/\n*.pyc\n*.nbc\n*.nbi\n.pytest_cache/\n.venv/\nreproduced/\nshared/data/aligned_repaired.npz\nshared/data/*.partial\n.env\n.env.*\n')
    (d/'README.md').write_text('# Complete historical market input\n\nAll bytes of the original ETHUSDT minute input are in these five ordered binary parts. Run the publication reproduce.py to assemble and verify the exact NPZ offline. Do not replace missing original marks with invented observations. The unchanged simulator applies the previously disclosed sensitivity handling.\n')
    rows=''.join(f"| [{r['id']}%]({r['folder']}/README.md) | {r['cumulative_return_percent']:.4f}% | {r['cagr_percent']:.4f}% | {r['trades']} | {r['win_rate_percent']:.4f}% | {r['fee_bps_per_side']:.10f} |\n" for r in records)
    (out/'README.md').write_text('''# Parrish Lyon: frozen +564.37% and +261.62% ETH records

The percentages are **five-year cumulative simulated returns**, not annual gains. Exact frozen source, model weights, data and every trade are published. No parameters were optimized or silently changed for this publication.

| Record | Cumulative return | CAGR | Trades | Net WR | Commission bps/side |
|---|---:|---:|---:|---:|---:|
'''+rows+'''
Both retain 2bps slippage per side, funding, 5R initial targets, 72h maximum holds, 6% planned account risk and 30x nominal leverage. The higher return uses an unverified full-round-trip interpretation of the quoted $5 cost. Actual account exposure and all losing years are reported separately. These were hindsight-highlighted diagnostics, not new holdout results.

## Complete contents

Each named case contains exact parameters, every timestamped trade, all annual/monthly/weekly/rolling-year returns, daily equity, minute-equity reconstruction and audit receipts. `shared/frozen_v8` contains the original IV/range logic, candidates, features, model forecasts, training, risk sizing, historical execution, reporting, tests and all 21 fitted ETH model folds. `SOURCE_MAP.json` maps every copied file back to its original repository path and commit.

**The entire 201,104,903-byte historical ETH minute input is directly in Git**, as five ordered parts in `shared/data`. The whole-publication ZIP also contains every part. It is not merely a downloader or an expiring artifact pointer. Prior-price, mark-price and funding observations and the original missing-data markers are preserved.

## Run

From this folder with Python 3.13:

```sh
python -m pip install -r shared/frozen_v8/requirements.txt
python reproduce.py --case both
python reproduce.py --case both --verify-models --retrain --minute-equity
python -m pytest -q shared/frozen_v8/tests
```

The first replay assembles input offline and matches every trade and daily equity value. The full command rebuilds features, recomputes all model forecasts, retrains all original folds without selection changes, and exports the complete minute-equity curves. It writes only `reproduced/`. Native Windows/macOS have not been tested; Linux dependencies are pinned. The install needs package access, but reruns use no credentials, external service or Internet connection once dependencies and data are available.

`PUBLICATION_VERIFICATION.json` records the actual completed rerun. `MANIFEST.json` hashes the publication, including every data part and nested original manifest. Original metadata in `shared/original_context` describes the broader study; some original metadata paths refer to other cases not part of these two records.

## Historical research, not live activation

Source snapshot: `'''+SOURCE_COMMIT+'''`. Original strategy folders and V4 live code are unchanged. This publication does not arm V8 or add an online broker integration. The included training and historical-execution programs are functional; the historical gains are not authenticated live fills or guaranteed future returns. Fee, collateral, execution-delay, drawdown, missing-mark and post-evaluation-selection limitations remain explicit. Third-party data and software retain their respective rights.
''')
    print('PREPARED',len(mapping),'unchanged source/reference files;',len(parts),'data parts',flush=True)

def finish(out,zip_path=None):
    receipt=json.loads((out/'reproduced/VERIFICATION.json').read_text())
    if len(receipt['cases'])!=2 or sum(r['trade_rows_matched'] for r in receipt['cases'])!=723:raise ValueError('Both exact ledgers must reproduce')
    if not receipt.get('models',{}).get('all_folds_retrained'):raise ValueError('Full model reconstruction not verified')
    save(out/'PUBLICATION_VERIFICATION.json',receipt)
    for case in json.loads((out/'CATALOG.json').read_text())['cases']:
        check=next(x for x in receipt['cases'] if x['id']==case['id'])
        save(out/case['folder']/'REPRODUCTION_VERIFICATION.json',check)
        minute=out/'reproduced'/case['folder']/'MINUTE_EQUITY.csv.gz'
        if not minute.exists():raise ValueError('Full minute-equity reconstruction missing')
        shutil.copy2(minute,out/case['folder']/'MINUTE_EQUITY_RECONSTRUCTED.csv.gz')
    items=[]
    for p in out.rglob('*'):
        rel=p.relative_to(out)
        if not p.is_file() or any(x in rel.parts for x in ('reproduced','__pycache__','.pytest_cache','.venv')) or p.suffix in ('.pyc','.nbc','.nbi') or rel==Path('MANIFEST.json') or rel==Path('shared/data/aligned_repaired.npz'):continue
        items.append(p)
    manifest={str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(items)}
    source_map=json.loads((out/'SOURCE_MAP.json').read_text())
    if not set(source_map['files']).issubset(manifest):raise ValueError('Archive would omit a required frozen source file')
    save(out/'MANIFEST.json',manifest)
    if zip_path:
        zip_path.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            for p in sorted(items):z.write(p,'published_eth_records/'+str(p.relative_to(out)))
            z.write(out/'MANIFEST.json','published_eth_records/MANIFEST.json')
        with zipfile.ZipFile(zip_path) as z:
            if z.testzip():raise ValueError('Corrupt complete-data archive')
            for name,rec in manifest.items():
                if hashlib.sha256(z.read('published_eth_records/'+name)).hexdigest()!=rec['sha256']:raise ValueError('Archive hash mismatch')
        print(json.dumps({'archive':str(zip_path),'sha256':sha(zip_path),'bytes':zip_path.stat().st_size,'verified_files':len(manifest)},indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--data',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--finish',action='store_true');p.add_argument('--zip-out',type=Path);a=p.parse_args()
    if a.finish:finish(a.out,a.zip_out)
    else:
        if not a.source or not a.data:p.error('--source and --data required for assembly')
        make(a.source,a.data,a.out)
if __name__=='__main__':main()

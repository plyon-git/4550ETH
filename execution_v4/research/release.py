"""Repeat causal research and export evidence. Never invokes the order runtime."""
from pathlib import Path
import argparse,json,os,subprocess,sys
from dataclasses import asdict
import pandas as pd
from trader.config import Settings
from research.data import sha256
from research.search import PERIODS

def call(*args):
    subprocess.run([sys.executable,'-u','-m',*map(str,args)],check=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})

def build_configs(root):
    folder=root/'configs';folder.mkdir(exist_ok=True);rows=[]
    for symbol in ['ETHUSDT','BTCUSDT','XRPUSDT']:
        start='2020-02-01T00:00:00Z' if symbol=='XRPUSDT' else '2020-01-01T00:00:00Z'
        r=root/'results';base=r if symbol=='ETHUSDT' else r/symbol
        rule=json.loads((base/'FROZEN_SELECTION.json').read_text())['primary']
        settings=asdict(Settings(symbol=symbol,bootstrap_start_utc=start))
        doc={'owner':'Parrish Lyon','strategy':rule['spec'],'execution':settings,'status':'research configuration; not an investment recommendation or 200% result','backtest_ref':f'evidence_repaired/{symbol}/RULE_PRIMARY_'+rule['id']+'/METRICS.json'}
        (folder/(symbol+'_rule.json')).write_text(json.dumps(doc,indent=2)+'\n')
        d=r/('DIRECTIONAL_'+symbol);choice=json.loads((d/'FROZEN.json').read_text());receipt=json.loads((d/'evaluation_receipts.json').read_text())[-1]
        modelpath=d/'models'/receipt['file'];assert sha256(modelpath)==receipt['sha256']
        settings.update(ml_model_path=str(modelpath.relative_to(root)),ml_model_sha256=receipt['sha256'],directional_threshold_r=choice['threshold_r'],auto_refit=True)
        doc={'owner':'Parrish Lyon','strategy':choice['spec'],'execution':settings,'status':'live-capable research configuration; target not established','backtest_ref':f'evidence_repaired/{symbol}/DIRECTIONAL_PRIMARY/METRICS.json','initial_model_cutoff':'last causal evaluation refit, not retrained using future values'}
        (folder/(symbol+'_directional.json')).write_text(json.dumps(doc,indent=2)+'\n')
        rows.extend(json.loads((root/'evidence_repaired'/symbol/'INDEX.json').read_text()))
    keys=['symbol','case','net_return','cagr','geometric_weekly','worst_week','conservative_intrabar_drawdown','trades','win_rate','profit_factor','longest_losing_streak','minimum_rolling_365_day_return','maximum_rolling_365_day_return','all_requested_targets_pass']
    pd.DataFrame([{k:r[k] for k in keys} for r in rows]).to_csv(root/'ALL_EVALUATION_CASES.csv',index=False)
    status={'research_status':'TARGET_NOT_MET' if not any(r['all_requested_targets_pass'] for r in rows) else 'HISTORICAL_TARGET_CANDIDATE_REQUIRES_REVIEW','evaluation':PERIODS['evaluation'],'complete_weeks':152,'min_requested_trades':200,'target_cagr':2.,'rolling_365_day_target':2.,'reported_cases':len(rows),'passes':sum(r['all_requested_targets_pass'] for r in rows),'directional_per_asset_primaries':[r for r in rows if r['case']=='DIRECTIONAL_PRIMARY'],'broker_status':'production submission implemented; no authenticated testnet or live exchange orders tested in this session','source_history':'original 45.50% baseline untouched; V4 uses separately repaired actual trade history','selection_disclosure':'fixed development/validation selection within each stage; later family extensions follow earlier result exposure; not a globally untouched holdout'}
    (root/'ASSESSMENT.json').write_text(json.dumps(status,indent=2)+'\n')

def manifest(root):
    out={}
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not p.is_file() or any(x in rel.parts for x in ('__pycache__','.pytest_cache','state','revisions','data','private_exports','private-exports','.venv')) or p.suffix in ('.pyc','.nbc','.nbi') or p.name=='RELEASE_MANIFEST.json' or p.name.startswith('.env'):continue
        out[str(rel)]={'sha256':sha256(p),'bytes':p.stat().st_size}
    (root/'RELEASE_MANIFEST.json').write_text(json.dumps(out,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True,type=Path);p.add_argument('--report-only',action='store_true');a=p.parse_args();root=Path.cwd()
    for symbol in ['ETHUSDT','BTCUSDT','XRPUSDT']:
        data=a.data_root/symbol/'aligned_repaired.npz';r=root/'results';base=r if symbol=='ETHUSDT' else r/symbol
        if not a.report_only:
            call('research.search','--data',data,'--symbol',symbol,'--out',base)
            call('research.trend_search','--data',data,'--symbol',symbol,'--out',r/('TREND_'+symbol))
            call('research.reversion_search','--data',data,'--symbol',symbol,'--out',r/('REVERSION_'+symbol))
            call('research.ml_search','--data',data,'--symbol',symbol,'--base-results',base,'--out',r/('ML_'+symbol))
            call('research.directional_search','--data',data,'--symbol',symbol,'--out',r/('DIRECTIONAL_'+symbol))
            call('research.directional_extension','--data',data,'--symbol',symbol,'--models',r/('DIRECTIONAL_'+symbol),'--out',r/('DIRECTIONAL_EXTENSION_'+symbol))
        call('research.replay_revision','--data',data,'--symbol',symbol,'--sources',r,'--out',root/'evidence_repaired'/symbol)
    build_configs(root);manifest(root)
    print('COMPLETE: inspect ASSESSMENT.json; process success is not strategy target success.',flush=True)
if __name__=='__main__':main()

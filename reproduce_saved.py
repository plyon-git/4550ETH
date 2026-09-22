#!/usr/bin/env python3
"""Reproduce only the preserved breakout diagnostic. Never places orders."""
from pathlib import Path
import hashlib,json,argparse
import numpy as np
import pandas as pd
from v3.engine import load_npz,run,summary,Config,TRADE_COLS
from v3.signals import hypotheses
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data/aligned_data.npz')
    args=parser.parse_args()
    saved=json.loads((ROOT/'SAVED_DIAGNOSTIC.json').read_text())
    for rel,wanted in saved['source_hashes'].items():
        p=args.data if rel=='data/aligned_data.npz' else ROOT/rel
        if hashlib.sha256(p.read_bytes()).hexdigest()!=wanted:
            raise ValueError(f'Original input/source identity differs: {p}')
    m,ts,raw=load_npz(args.data)
    spec=saved['candidate'];cfg=Config(**spec['config'])
    match=next((row for row in hypotheses(raw) if row[0]['id']==spec['id']),None)
    if match is None:raise RuntimeError('Exact saved signal not found')
    _,signal,stops=match
    protocol=json.loads((ROOT/'PROTOCOL.json').read_text())
    start,end=[int(np.searchsorted(ts,pd.Timestamp(x).timestamp())) for x in protocol['evaluation']]
    result=run(m,ts,signal,stops,cfg,start,end,True)
    stats,weeks=summary(result,ts,start,end,cfg)
    out=ROOT/'reproduced';out.mkdir(exist_ok=True)
    trades=pd.DataFrame(result[3],columns=TRADE_COLS)
    orig_trades=pd.read_csv(ROOT/'results/breakout_trades.csv.gz')
    np.testing.assert_allclose(trades.to_numpy(),orig_trades.to_numpy(),rtol=1e-12,atol=1e-8)
    eq=pd.read_csv(ROOT/'results/breakout_equity.csv.gz')
    for i,col in enumerate(['equity_close','equity_open_pre_funding','conservative_equity_low']):
        np.testing.assert_allclose(result[i],eq[col].to_numpy(),rtol=1e-12,atol=1e-8)
    original_weeks=pd.read_csv(ROOT/'results/breakout_weeks.csv')
    np.testing.assert_allclose([w[1] for w in weeks],original_weeks.net_return.to_numpy(),rtol=1e-10,atol=1e-12)
    for k,v in saved['recorded_evaluation'].items():
        if k in stats and isinstance(v,(int,float)) and not isinstance(v,bool):
            np.testing.assert_allclose(stats[k],v,rtol=1e-10,atol=1e-8,err_msg=k)
    checks={'matched':True,'trade_rows':len(trades),'minute_equity_rows':len(eq),'equity_series_checked':3,'weekly_rows':len(weeks),'candidate_id':spec['candidate_id'],'max_trade_cell_absolute_error':float(np.max(np.abs(trades.to_numpy()-orig_trades.to_numpy()))),'metrics':stats}
    (out/'REPRODUCTION_VERIFICATION.json').write_text(json.dumps(checks,indent=2,allow_nan=False))
    np.savez_compressed(out/'breakout_signal.npz',signal=signal,stops=stops)
    trades.to_csv(out/'breakout_trades.csv.gz',index=False)
    print(json.dumps(checks,indent=2))
if __name__=='__main__':main()

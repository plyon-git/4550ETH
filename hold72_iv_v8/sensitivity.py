"""Post-evaluation sizing/carry sensitivity, not independently selected alpha."""
from pathlib import Path
from dataclasses import replace,asdict
import argparse,itertools,json
import numpy as np
from core import *
from learning import choose
from research import save,boundary,PERIODS
from report import publish
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',required=True);p.add_argument('--data',required=True);a=p.parse_args()
 root=ROOT/'results'/a.symbol/'SIZING_DIAGNOSTICS';root.mkdir(parents=True,exist_ok=True)
 variations=[(f'risk{risk}_cap{cap}',replace(Execution(),risk=risk,cap=cap)) for risk,cap in itertools.product([.02,.04,.06,.08],[3.,5.,10.,30.])]
 base=replace(Execution(),risk=.04)
 variations.extend([(f'hold{h}',replace(base,max_hold_hours=h)) for h in [24,48]])
 variations.extend([('30x_no_extra_collateral',replace(base,funded_collateral=False)),('zero_cost',replace(base,fee_bps=0,slip_bps=0)),('double_cost',replace(base,fee_bps=10,slip_bps=4)),('delay2m',replace(base,delay_minutes=2))])
 save(root/'PROTOCOL.json',dict(created_utc=str(pd.Timestamp.now(tz='UTC')),post_evaluation_diagnostic=True,threshold=.5,
    variations=[dict(name=n,execution=asdict(c)) for n,c in variations],notes='Not promoted to primary; a risk sensitivity is not independently validated alpha. Target/yearly consistency must be reported separately.'))
 ts,m,missing=load_market(a.data,a.symbol)
 with np.load(ROOT/'results'/a.symbol/'LEARNING/PREDICTIONS.npz',allow_pickle=False) as z:
  s=z['candidates'];prob=z['prediction'];pol=z['policy']
 sg,chosen=choose(s,prob,.5);left,right=boundary(ts,PERIODS['five_years']);rows=[]
 for name,cfg in variations:
  out=run(m,missing,sg,left,right,cfg,a.symbol,True)
  met=publish(root/name,out,m,missing,ts,sg,left,right,cfg,a.symbol,dict(learning_threshold=.5,post_evaluation=True,execution=asdict(cfg)))
  rows.append(dict(scenario=name,**met));print(a.symbol,name,met['cagr'],met['mean_annual'],met['trades'],met['conservative_drawdown'],flush=True)
 save(root/'SUMMARY.json',rows)
if __name__=='__main__':main()

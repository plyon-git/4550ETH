"""Correct secondary daily-equity excursion accounting; preserve crypto results.
Project-specific work: Parrish Lyon. This is a tested method correction, not new alpha.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parent
OLD='excursion=qty*abs(ent-stop)+qty*ent*fee if stopped else max(0.,-net);dd=max(dd,1-(before-excursion)/highwater)'
NEW='adverse_price=ex if stopped else (lo if side==1 else hi);loweq=min(balance,before-qty*ent*fee+side*qty*(adverse_price-ent));dd=max(dd,1-loweq/highwater)'
TEST='''\n\ndef test_profitable_equity_trade_still_records_intraday_excursion():
 from equity_research import simulate
 eq,ledger,dd=simulate(np.array([[100.,100.6,99.4,100.5]]),np.array([1],np.int8),np.array([.01]),np.array([1000000.]),np.array([19000],np.int64),0,1,.25,1.,1.,True,True,.01,.0001,.0001,4.)
 assert len(ledger)==1 and ledger[0,9]>0 and dd>0
'''
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def crypto_identity():
 return {str(p.relative_to(ROOT)):digest(p) for symbol in ['ETHUSDT','BTCUSDT','XRPUSDT'] for p in sorted((ROOT/'results'/symbol).rglob('*')) if p.is_file()}
def main():
 source=ROOT/'source/equity_research.py';before=crypto_identity();text=source.read_text();already=NEW in text
 if not already and text.count(OLD)!=1:raise ValueError('Unexpected equity source; refusing broad replacement')
 history=ROOT/'revisions';history.mkdir(exist_ok=True)
 backup=history/'before_equity_excursion_correction.zip'
 if not already and not backup.exists():
  with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
   z.write(source,'source/equity_research.py')
   for symbol in ['SPY','QQQ']:
    for p in (ROOT/'results'/symbol).rglob('*'):
     if p.is_file():z.write(p,str(p.relative_to(ROOT)))
 if not already:source.write_text(text.replace(OLD,NEW))
 test=ROOT/'tests/test_v5.py'
 if 'def test_profitable_equity_trade_still_records_intraday_excursion' not in test.read_text():test.write_text(test.read_text()+TEST)
 note={'owner':'Parrish Lyon','correction':'Count adverse intraday excursions on profitable daily ETF trades and include actual modeled exit costs on stopped trades. Previous daily model understated excursion drawdown.','selection_impact':'Recompute development/validation rankings and all SPY/QQQ reporting. No new unseen holdout is created. The fixed-strategy profit formula is unchanged.','crypto_results_unchanged':True,'scope':'Secondary daily ETF diagnostics only, not ES intraday execution. Drawdown is the modeled adverse excursion from prior equity high-water; exact tick drawdown remains unavailable.','prior_release':'v5-volatility-20260922','corrected_release':'v5.1-volatility-20260922'}
 for symbol in ['SPY','QQQ']:
  path=ROOT/'results'/symbol
  if path.exists():shutil.rmtree(path)
 env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
 subprocess.run([sys.executable,str(ROOT/'source/equity_research.py')],check=True,env=env)
 if crypto_identity()!=before:raise ValueError('Unexpected alteration of crypto evidence')
 checks={'SPY':(-0.07945591445485445,131),'QQQ':(-0.17900609002391246,168)}
 for symbol,(expected,trades) in checks.items():
  folder=ROOT/'results'/symbol;frozen=json.loads((folder/'FROZEN.json').read_text());key=frozen['primary']['id'];m=json.loads((folder/('PRIMARY_'+key)/'METRICS.json').read_text())
  if abs(m['net_return']-expected)>1e-7 or m['trades']!=trades:raise ValueError('ETF reproduction does not match independent local correction: '+symbol)
  note[symbol]={'primary_id':key,'net_return':m['net_return'],'trades':m['trades'],'cagr':m['cagr']}
 (history/'EQUITY_CORRECTION.json').write_text(json.dumps(note,indent=2)+'\n')
 marker='## V5.1 daily-ETF excursion correction'
 for file in ['README.md','docs/METHODOLOGY.md']:
  path=ROOT/file;body=path.read_text()
  if marker not in body:path.write_text(body+'\n'+marker+'\n\nThe secondary daily-equity drawdown model now records adverse excursions on profitable trades and includes modeled exit costs on stopped trades. SPY/QQQ development/validation selection and reports were rerun. Crypto evidence is byte-for-byte unchanged. The original release remains in Git history; the corrected release is v5.1-volatility-20260922. This is a method correction on already observed data, not a new holdout or proof of ES intraday fills.\n')
 subprocess.run([sys.executable,'-m','pytest','-q',str(ROOT/'tests'),'--junitxml='+str(ROOT/'results/TESTS.xml')],check=True,env=env)
 subprocess.run([sys.executable,str(ROOT/'source/assemble.py')],check=True,env=env)
 print(json.dumps(note,indent=2))
if __name__=='__main__':main()

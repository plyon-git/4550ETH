"""Sequential research only. No exchange credentials or order submission."""
from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parent
ENV={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
def call(script,*args):subprocess.run([sys.executable,'-u',str(ROOT/'source'/script),*args],check=True,env=ENV)
def main():
 for symbol in ['ETHUSDT','BTCUSDT','XRPUSDT']:
  call('research.py','--symbol',symbol)
  call('adaptive.py','--symbol',symbol)
  if symbol!='XRPUSDT':call('meta_filter.py','--symbol',symbol)
 call('equity_research.py')
 subprocess.run([sys.executable,'-m','pytest','-q',str(ROOT/'tests'),'--junitxml='+str(ROOT/'results/TESTS.xml')],check=True,env=ENV)
 call('assemble.py')
if __name__=='__main__':main()

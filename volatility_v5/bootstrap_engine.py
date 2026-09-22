"""Create the separate V5 kernel from an immutable verified original, never edit V4."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent
SOURCE_SHA='93495e625108d0e4e4bc9b422629d1167d29dd053609f5d79d9b9e0118112e9c'
RESULT_SHA='7df5ab28c88c4acd0378acf702ccbbf09090bf5bffa7844079e434099cd4f271'
def main():
 p=ROOT.parent/'execution_v4/research/simulator.py';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('original engine identity mismatch')
 s=raw.decode();patches=[('Independent causal linear-perpetual research engine. No order submission.','V5 separate engine derived from the preserved V4 simulator. Adds absolute target levels. No order submission.'),('def _run(m,ts,sig,stop,start,end,p,record):','def _run(m,ts,sig,stop,absolute_target,start,end,p,record):'),('ledger=np.empty((2*n if record else 0, 16)); nt=0','ledger=np.empty((min(2*n, int((ts[end-1]-ts[start])//86400+3)*int(p[17])+100) if record else 0, 16)); nt=0'),('valid_target=ent0+s*dist*rr>0','candidate_target=absolute_target[i-int(delay)]\n                if not np.isfinite(candidate_target):candidate_target=ent0+s*dist*rr\n                valid_target=candidate_target>0 and s*(candidate_target-ent0)>0'),('st=ent-s*dist;target=ent+s*dist*rr','st=ent-s*dist;target=candidate_target'),('def run(m,ts,signals,stops,cfg=Config(),start=0,end=None,record=False):','def run(m,ts,signals,stops,absolute_target,cfg=Config(),start=0,end=None,record=False):'),('return _run(m,ts,signals,stops,start,end,p,record)','return _run(m,ts,signals,stops,absolute_target,start,end,p,record)')]
 for old,new in patches:
  if s.count(old)!=1:raise ValueError('unexpected source patch count')
  s=s.replace(old,new)
 if hashlib.sha256(s.encode()).hexdigest()!=RESULT_SHA:raise ValueError('result differs from tested local V5 kernel')
 (ROOT/'source').mkdir(exist_ok=True);(ROOT/'source/engine.py').write_text(s)
 print('Separate tested V5 kernel reproduced; V4 untouched.')
if __name__=='__main__':main()

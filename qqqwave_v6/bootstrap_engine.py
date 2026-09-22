"""Build only the separately versioned V6 kernel from its immutable V5 source.
Both input and output are SHA-pinned. Existing mismatched files are not overwritten.
"""
from pathlib import Path
import hashlib,difflib
ROOT=Path(__file__).resolve().parent
ORIGINAL_SHA='7df5ab28c88c4acd0378acf702ccbbf09090bf5bffa7844079e434099cd4f271'
DERIVED_SHA='22bacaf2fffe826888007288a03e952a5514b7eeb24a5f8ce647d386bcd533c0'
CHANGES=[
('Adds absolute target levels. No order submission.','Adds frozen absolute stops, targets and forecast deadlines; see engine_diff.patch. No order submission.'),
('def _run(m,ts,sig,stop,absolute_target,start,end,p,record):','def _run(m,ts,sig,stop,absolute_target,expiry,start,end,p,record):'),
('    bal=initial; q=0.;','    deadline=0; bal=initial; q=0.;'),
('elif i>eind and ts[i]-ts[eind]>=hold:','elif i>eind and (ts[i]-ts[eind]>=hold or ts[i]>=deadline):'),
('if s!=0 and np.isfinite(sf) and 0<sf<.95:','if s!=0 and np.isfinite(sf) and sf>0 and s*(op-sf)>0 and expiry[i-int(delay)]>ts[i]:'),
('                dist=ent0*sf','                dist=s*(ent0-sf)'),
('funding=0.;eind=i;estop=dist;st=ent-s*dist;target=candidate_target','funding=0.;eind=i;estop=dist;st=sf;target=candidate_target;deadline=expiry[i-int(delay)]'),
('def run(m,ts,signals,stops,absolute_target,cfg=Config(),start=0,end=None,record=False):','def run(m,ts,signals,stops,absolute_target,expiry,cfg=Config(),start=0,end=None,record=False):'),
('return _run(m,ts,signals,stops,absolute_target,start,end,p,record)','return _run(m,ts,signals,stops,absolute_target,expiry,start,end,p,record)')]

def build(root=ROOT):
    original=(root/'source/engine_v5_original.py').read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_SHA:raise ValueError('V5 source identity mismatch')
    text=original.decode('utf-8')
    for old,new in CHANGES:
        if text.count(old)!=1:raise ValueError('expected unique source patch match')
        text=text.replace(old,new)
    data=text.encode('utf-8')
    if hashlib.sha256(data).hexdigest()!=DERIVED_SHA:raise ValueError('derived engine identity mismatch')
    output=root/'source/engine.py'
    if output.exists() and output.read_bytes()!=data:raise ValueError('Existing engine modified; refusing silent overwrite')
    if not output.exists():output.write_bytes(data)
    patch=''.join(difflib.unified_diff(original.decode().splitlines(True),text.splitlines(True),fromfile='engine_v5_original.py',tofile='engine.py'))
    (root/'source/engine_diff.patch').write_text(patch)
    return {'original_sha256':ORIGINAL_SHA,'derived_sha256':DERIVED_SHA}
if __name__=='__main__':print(build())

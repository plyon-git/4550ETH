"""Verify actual generated evidence and assemble a credential-free release archive."""
from pathlib import Path
import argparse,hashlib,json,platform,sys,zipfile
import numpy as np
import pandas as pd
from research.data import sha256

EXPECTED_DATA={'ETHUSDT':'b6a9f20924ad42d8ea802404f5640356fc42c6301b98ed64ad161a576c71e46d','BTCUSDT':'2f6fc1e9ccb749e3e17793796d72ebd6c12a9c2f7d51e9c7e259cda8f97002a3','XRPUSDT':'43678daef70287657734cf3eb6b6915ffa5df0b24d90d289d8892ee1d5f70859'}
EXPECTED_RESULTS={'ETHUSDT':(1.2815084563120713,637),'BTCUSDT':(-.8863053916538508,910),'XRPUSDT':(-.9345895439886509,1378)}

def selected_files(root):
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if not p.is_file() or any(x in rel.parts for x in ('__pycache__','.pytest_cache','state','private_exports','private-exports','revisions','data','.venv')) or p.suffix in ('.pyc','.nbc','.nbi') or p.name.startswith('.env'):continue
        yield p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',required=True,type=Path);parser.add_argument('--zip-out',type=Path);parser.add_argument('--data-only',action='store_true');a=parser.parse_args();root=Path.cwd()
    identities={}
    for symbol,wanted in EXPECTED_DATA.items():
        path=a.data_root/symbol/'aligned_repaired.npz';actual=sha256(path)
        if actual!=wanted:raise ValueError('Unexpected market data identity: '+symbol)
        identities[symbol]={'sha256':actual,'bytes':path.stat().st_size}
    if a.data_only:print(json.dumps(identities,indent=2));return
    assessment=json.loads((root/'ASSESSMENT.json').read_text())
    if assessment['reported_cases']!=150:raise ValueError('Incomplete published finalist set')
    cases=pd.read_csv(root/'ALL_EVALUATION_CASES.csv')
    if len(cases)!=150:raise ValueError('Missing case rows')
    audits=[]
    for path in (root/'evidence_repaired').rglob('INDEPENDENT_AUDIT.json'):
        doc=json.loads(path.read_text())
        if not doc['passed'] or doc['minute_rows']!=1532160:raise ValueError('Failed or incomplete independent audit')
        trades=pd.read_csv(path.parent/'all_trades_UTC.csv')
        if len(trades)!=doc['trade_rows'] or trades.trade_id.duplicated().any():raise ValueError('Trade export incomplete')
        audits.append(doc)
    if len(audits)!=150:raise ValueError('Not every case has an audit')
    for symbol,(gain,trades) in EXPECTED_RESULTS.items():
        doc=json.loads((root/'evidence_repaired'/symbol/'DIRECTIONAL_PRIMARY'/'METRICS.json').read_text())
        np.testing.assert_allclose(doc['net_return'],gain,rtol=1e-7,atol=1e-7)
        if doc['trades']!=trades or doc['complete_weeks']!=152:raise ValueError('Published-source reproduction differs from independent local run')
    checks=root/'checks';checks.mkdir(exist_ok=True)
    verification={'source_replayed_on':platform.platform(),'python':sys.version.split()[0],'data':identities,'independently_audited_cases':len(audits),'trade_rows_across_distinct_simulations':sum(x['trade_rows'] for x in audits),'each_case_minutes':1532160,'max_open_close_equity_discrepancy':max(max(x['largest_open_error'],x['largest_close_error']) for x in audits),'local_vs_published_primary_results_match':True,'authenticated_exchange_orders_submitted':False,'target_met':assessment['passes']>0}
    (checks/'RELEASE_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
    manifest={str(p.relative_to(root)):{'sha256':sha256(p),'bytes':p.stat().st_size} for p in selected_files(root) if p.name!='RELEASE_MANIFEST.json'}
    (root/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if a.zip_out:
        a.zip_out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.zip_out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in selected_files(root):z.write(p,'execution_v4/'+str(p.relative_to(root)))
        with zipfile.ZipFile(a.zip_out) as z:
            if z.testzip():raise ValueError('Corrupt release ZIP')
            for name,rec in manifest.items():
                if hashlib.sha256(z.read('execution_v4/'+name)).hexdigest()!=rec['sha256']:raise ValueError('Packaged hash mismatch')
        print(json.dumps({'zip':str(a.zip_out),'sha256':sha256(a.zip_out),'bytes':a.zip_out.stat().st_size,'files_verified':len(manifest),'verification':verification},indent=2))
    else:print(json.dumps(verification,indent=2))
if __name__=='__main__':main()

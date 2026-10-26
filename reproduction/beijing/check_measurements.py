"""Check saved M outputs against one frozen input; never generate or route."""
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import sys
from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--methods',nargs='+',default=['SPRT','PrivTrace','DPStd','DPTraj-PM'])
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('Existing audit output is not overwritten')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    prepared=(ROOT/c['paths']['prepared']).resolve();identity=validate_dataset(prepared)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Dataset identity mismatch')
    source_hash=sha(prepared/'trajectories.pkl');results=[]
    base=(ROOT/c['paths']['output']).resolve()/c['batch']/'measurements'
    for method in a.methods:
        folder=base/method;meta=json.loads((folder/'measurement_manifest.json').read_text(encoding='utf-8'))
        if meta.get('input_sha256',meta.get('prepared_sha256'))!=source_hash:raise ValueError(method+': wrong input')
        if meta['epsilon']!=c['epsilon'] or meta['seed']!=c['seed'] or meta['public_slot_count']!=identity['count']:
            raise ValueError(method+': wrong configuration')
        data=folder/'measurement.pkl'
        if sha(data)!=meta['outputs']['measurement.pkl']:raise ValueError(method+': changed output')
        with data.open('rb') as handle:rows=pickle.load(handle)
        if len(rows)!=identity['count']:raise ValueError(method+': wrong slot count')
        results.append(dict(method=method,records=len(rows),input_sha256=source_hash,
            measurement_sha256=sha(data),elapsed_seconds=meta.get('elapsed_seconds'),status='VERIFIED'))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    report=dict(command=[sys.executable,*sys.argv],dataset=identity,methods=results)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

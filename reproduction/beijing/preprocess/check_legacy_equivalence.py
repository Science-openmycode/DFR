"""Compare a new standard package with the accepted legacy frozen corpus."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_contract import sha
from preprocess.framed_records import records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();started=time.perf_counter()
    if args.out.exists():raise FileExistsError(args.out)
    old=args.reference;new=args.package/'prepared'
    manifest=json.loads((old/'canonical_manifest.json').read_text(encoding='utf-8'))
    current=json.loads((new/'canonical_manifest.json').read_text(encoding='utf-8'))
    for key in ('dataset','trajectory_count','train_count','test_count','seed','network_sha256','network_sidecars','preprocessing'):
        if manifest[key]!=current[key]:raise ValueError('Legacy metadata differs: '+key)
    for name in ('source_indices.json','train_split.json','test_split.json','bbox.json'):
        if sha(old/name)!=manifest['artifacts'][name]:raise ValueError('Reference artifact changed: '+name)
        if json.loads((old/name).read_text())!=json.loads((new/name).read_text()):raise ValueError('Legacy membership differs: '+name)
    n=manifest['trajectory_count']
    for name in ('trajectories.pkl.gz','road_records.pkl.gz'):
        if sha(old/name)!=manifest['artifacts'][name]:raise ValueError('Reference artifact changed: '+name)
        count=0
        for index,(a,b) in enumerate(zip(records(old/name,n),records(new/name,n),strict=True)):
            equal=np.array_equal(a,b) if name.startswith('trajectories') else a==b
            if not equal:raise ValueError(f'Legacy values differ: {name} record {index}')
            count+=1
        if count!=n:raise ValueError('Legacy population differs')
    result=dict(status='LEGACY_FROZEN_VALUES_IDENTICAL',count=n,train_count=manifest['train_count'],test_count=manifest['test_count'],
        coordinates_exact=True,road_records_exact=True,source_ids_and_splits_exact=True,
        old_manifest_sha256=sha(old/'canonical_manifest.json'),new_manifest_sha256=sha(new/'canonical_manifest.json'),
        seconds=time.perf_counter()-started)
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()

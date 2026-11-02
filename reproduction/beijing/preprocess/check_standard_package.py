"""Compare every standard row to its compatibility views without whole-list loads."""
import argparse,gzip,json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from preprocess.dataset_contract import validate_dataset,sha
from preprocess.framed_records import records


def main():
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();base=a.package.resolve()
    if a.out.exists():raise FileExistsError(a.out)
    bundle=json.loads((base/'dataset.json').read_text(encoding='utf-8'));prepared=base/bundle['paths']['prepared']
    identity=validate_dataset(prepared,public_network=base/bundle['paths']['network'],verify_hashes=True);n=identity['count']
    indices=json.loads((prepared/'source_indices.json').read_text());train=set(json.loads((prepared/'train_split.json').read_text())['indices'])
    keys={'record_index','source_index','split','coordinates','road_ids','point_timestamps','start_ts','end_ts'}
    count=0
    with gzip.open(base/'records.jsonl.gz','rt',encoding='utf-8') as f:
        for i,(line,coords,road) in enumerate(zip(f,records(prepared/'trajectories.pkl',n),records(prepared/'road_records.pkl.gz',n),strict=True)):
            row=json.loads(line)
            if set(row)!=keys or row['record_index']!=i or row['source_index']!=indices[i]:raise ValueError('Record schema/order mismatch')
            if row['split']!=('train' if i in train else 'test'):raise ValueError('Split changed')
            if not np.array_equal(np.asarray(row['coordinates']),coords):raise ValueError('Coordinates changed')
            if row['road_ids']!=[int(e) for e in road['cpath']]:raise ValueError('Road sequence changed')
            if row['point_timestamps'] is not None:
                if len(row['point_timestamps'])!=len(coords):raise ValueError('Time alignment changed')
                if row['start_ts']!=row['point_timestamps'][0] or row['end_ts']!=row['point_timestamps'][-1]:raise ValueError('Time endpoints changed')
            count+=1
            if count%100000==0:print('STANDARD_VERIFY_PROGRESS',count,n,flush=True)
    if count!=n:raise ValueError('Standard population count changed')
    result=dict(status='STANDARD_PACKAGE_VERIFIED',count=count,train_count=identity['train_count'],test_count=identity['test_count'],record_keys=sorted(keys),records_sha256=sha(base/'records.jsonl.gz'))
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()

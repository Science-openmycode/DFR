"""Bind the fixed coordinate corpus to GeoLife time endpoints, without resegmentation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import time
import numpy as np

BBOX=(39.75,40.15,116.10,116.65)
REAL_SHA='6a160ca557fbd7bab97af489b56c931e73532c498c390e31965c0d61e53361fd'


def read_record(path):
    points=[]; first=last=None
    with Path(path).open(encoding='utf-8',errors='ignore') as source:
        for _ in range(6): next(source,None)
        for line in source:
            fields=line.strip().split(',')
            if len(fields)<2: continue
            try: lat,lon=float(fields[0]),float(fields[1])
            except ValueError: continue
            if BBOX[0]<=lat<=BBOX[1] and BBOX[2]<=lon<=BBOX[3]:
                points.append((lat,lon))
                if first is None: first=fields
                last=fields
    if len(points)<2: return None,None,None
    def timestamp(fields):
        try:
            return datetime.strptime(fields[5]+' '+fields[6],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
        except (IndexError,ValueError) as exc:
            raise ValueError(f'invalid endpoint timestamp: {path}') from exc
    return np.asarray(points,dtype=float),timestamp(first),timestamp(last)


def verify_record(observed,expected,index):
    if observed.shape!=expected.shape or not np.array_equal(observed,expected):
        raise ValueError(f'coordinate binding mismatch at record {index}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',required=True,type=Path)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--expected-sha256',help='Optional user-supplied reference checksum; no historical digest required')
    a=p.parse_args();start=time.time()
    if a.out.exists(): raise FileExistsError(a.out)
    with a.reference.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    if a.expected_sha256 and digest!=a.expected_sha256: raise ValueError('reference differs from the requested checksum')
    with a.reference.open('rb') as f: reference=pickle.load(f)
    files=sorted(a.source_dir.glob('*/Trajectory/*.plt'))
    eligible=[]
    # Stream raw data rather than holding a second 300 MB coordinate corpus.
    for path in files:
        coords,t0,t1=read_record(path)
        if coords is not None:
            eligible.append((path,t0,t1,hashlib.sha256(coords.tobytes()).hexdigest(),coords.shape))
        if len(eligible) and len(eligible)%2000==0: print('eligible',len(eligible),flush=True)
    if len(eligible)!=len(reference): raise ValueError('raw/reference record count differs')
    order=np.random.default_rng(20260713).permutation(len(eligible)); rows=[]
    for index,original in enumerate(order):
        path,t0,t1,h,shape=eligible[int(original)]; expected=np.asarray(reference[index],dtype=float)
        if expected.shape!=shape or hashlib.sha256(expected.tobytes()).hexdigest()!=h:
            raise ValueError(f'coordinate binding mismatch at record {index}')
        rows.append(dict(id=index+1,source=str(path.relative_to(a.source_dir)),start_ts=t0,end_ts=t1,
                         point_count=len(expected),coordinate_sha256=h))
    result=dict(status='complete',scope='private internal input binding; not a DP release',
                input_records=len(reference),source_files=len(files),reference_sha256=digest,
                permutation_seed=20260713,bbox=BBOX,all_coordinates_exact=True,
                time_policy='real first/last retained GeoLife timestamps; UTC parsing matches historical MTNet adapter',
                segmentation='one eligible PLT file; same bbox-filtered coordinate sequence as frozen input',
                elapsed_seconds=time.time()-start,records=rows)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf8') as f: json.dump(result,f,indent=2)
    print({k:v for k,v in result.items() if k!='records'},flush=True)


if __name__=='__main__': main()

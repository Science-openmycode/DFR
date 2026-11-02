"""Measure, without accepting or changing, a legacy coordinate difference."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from preprocess.framed_records import records

p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();start=time.perf_counter()
if a.out.exists():raise FileExistsError(a.out)
meta=json.loads((a.reference/'canonical_manifest.json').read_text());n=meta['trajectory_count']
maximum=0.;changed=0;points=0;examples=[];shapes=True;road_equal=True
for i,(old,new) in enumerate(zip(records(a.reference/'trajectories.pkl.gz',n),records(a.package/'prepared/trajectories.pkl.gz',n),strict=True)):
    if old.shape!=new.shape:shapes=False;continue
    delta=np.abs(np.asarray(old)-np.asarray(new));maximum=max(maximum,float(delta.max(initial=0)))
    if np.any(delta):
        changed+=1;points+=int(np.count_nonzero(np.any(delta!=0,axis=1)))
        if len(examples)<3:
            k=int(np.flatnonzero(np.any(delta!=0,axis=1))[0]);examples.append(dict(record=i,point=k,old=old[k].tolist(),new=new[k].tolist(),max_degrees=float(delta.max())))
for old,new in zip(records(a.reference/'road_records.pkl.gz',n),records(a.package/'prepared/road_records.pkl.gz',n),strict=True):
    if old!=new:road_equal=False
result=dict(status='MEASURED_NOT_ACCEPTED',count=n,coordinate_shapes_equal=shapes,changed_records=changed,changed_points=points,max_absolute_degrees=maximum,
    conservative_max_metres=maximum*111320*2**.5,road_records_exact=road_equal,examples=examples,seconds=time.perf_counter()-start)
a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)

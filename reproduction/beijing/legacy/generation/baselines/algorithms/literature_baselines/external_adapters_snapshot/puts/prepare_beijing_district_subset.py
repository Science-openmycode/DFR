"""Create a geographically contained Beijing subset for native PUTS auditing."""
from __future__ import annotations
import argparse
import json
import pickle
from pathlib import Path
import numpy as np

def max_jump_m(traj):
    a,b=np.radians(traj[:-1]),np.radians(traj[1:])
    d=b-a; h=np.sin(d[:,0]/2)**2+np.cos(a[:,0])*np.cos(b[:,0])*np.sin(d[:,1]/2)**2
    return float(np.max(6_371_000*2*np.arcsin(np.minimum(1,np.sqrt(h)))))

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--bbox',nargs=4,type=float,required=True);p.add_argument('--max-jump-m',type=float,default=None);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with a.input.open('rb') as h:data=[np.asarray(x,float) for x in pickle.load(h)]
    lo=np.array([a.bbox[0],a.bbox[2]]);hi=np.array([a.bbox[1],a.bbox[3]])
    kept=[x for x in data if len(x)>=2 and np.all((x>=lo)&(x<=hi)) and (a.max_jump_m is None or max_jump_m(x)<=a.max_jump_m)]
    if not kept:raise RuntimeError('no fully contained trajectories')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('wb') as h:pickle.dump(kept,h,pickle.HIGHEST_PROTOCOL)
    a.out.with_suffix('.json').write_text(json.dumps({'bbox':a.bbox,'max_jump_m':a.max_jump_m,'n_input':len(data),'n_kept':len(kept)},indent=2))
    print(f'kept {len(kept)}/{len(data)} trajectories -> {a.out}',flush=True)
if __name__=='__main__':main()

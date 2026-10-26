"""Generate the declared public number of native MTNet road-ID trajectories."""
import argparse
import json
import os
from pathlib import Path
import pickle
import random
import sys
import time

import numpy as np
import torch


def sha(path):
    import hashlib
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--public-slot-count',type=int,required=True)
    p.add_argument('--batch-size',type=int,default=256)
    a=p.parse_args()
    if a.public_slot_count<1 or a.batch_size<1:p.error('Counts must be positive public parameters')
    root=a.root.resolve();out=root/'native_release'
    if out.exists():raise FileExistsError(out)
    os.chdir(root/'official');sys.path.insert(0,str(root/'official'))
    from util import config
    config.CITY='beijing_roads_l20';config.DATA_BASE=str(root/'data')+os.sep;config.TRAJ_FIX_LEN=21
    if config.TCOST_MAX!=6000:raise ValueError('Public author time-scale changed')
    import mtnet
    lock=json.loads((root/'canonical_mtnet_source_lock.json').read_text(encoding='utf-8'))
    for name,digest in lock['files_sha256'].items():
        if sha(root/'official'/name)!=digest.lower():raise ValueError('MTNet source lock changed')
    random.seed(20260712);np.random.seed(20260712);torch.manual_seed(20260712)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(20260712)
    checkpoint=torch.load(root/'trained/model.pt',map_location=config.device,weights_only=False)
    model=mtnet.Model();model.load_state_dict(checkpoint['state_dict']);model.eval()
    original_step=model.step
    def step(x,t,h,c):return original_step(x,t.long(),h,c)
    model.step=step
    origins=np.load(root/'public_origin_ids.npy')
    if origins.ndim!=1 or len(origins)==0 or origins.min()<1 or origins.max()>=model.adj.shape[0]-1:
        raise ValueError('Invalid public origin edge domain')
    selected=np.random.default_rng(20260712).choice(origins,a.public_slot_count,replace=True)
    roads=[];started=time.perf_counter()
    with torch.no_grad():
        for offset in range(0,len(selected),a.batch_size):
            values=selected[offset:offset+a.batch_size]
            x=torch.as_tensor(values[:,None],dtype=torch.long,device=config.device)
            t=torch.zeros_like(x);cost=torch.zeros_like(x,dtype=torch.float)
            samples,_=model.sample(x,t,cost)
            for origin,suffix in zip(values,samples.cpu().tolist()):
                route=[int(origin)]
                for edge in suffix:
                    if int(edge)==0:break
                    route.append(int(edge))
                roads.append(route)
    if len(roads)!=a.public_slot_count:raise ValueError('Wrong native output count')
    out.mkdir()
    with (out/'routes.pkl').open('xb') as f:pickle.dump(roads,f,pickle.HIGHEST_PROTOCOL)
    manifest=dict(method='MTNet',native=True,generated_records=len(roads),public_slot_count=a.public_slot_count,
                  routes_sha256=sha(out/'routes.pkl'),model_sha256=sha(root/'trained/model.pt'),
                  public_origins_sha256=sha(root/'public_origin_ids.npy'),
                  preparation_manifest_sha256=sha(root/'full_preparation_manifest.json'),
                  conditions='Uniform public edge origin; fixed departure zero; public TCOST_MAX=6000',
                  private_input_access_during_generation=False,post_generation_matching=False,
                  epsilon_training=1.4,delta_training=1e-5,
                  privacy_scope='Prepared-aligned replacement-adjacency training; not certified end-to-end raw preprocessing',
                  seconds=time.perf_counter()-started)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('DONE_NATIVE_MTNET',len(roads),manifest['seconds'],flush=True)


if __name__=='__main__':main()

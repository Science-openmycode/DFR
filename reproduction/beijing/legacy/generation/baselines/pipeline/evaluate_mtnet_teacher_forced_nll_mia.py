"""White-box teacher-forced route-NLL membership screening for MTNet.

This is the target-model likelihood component required by LiRA/RMIA.  It does
not yet claim reference-model calibration: report it only as a preregistered
screening statistic, then add independently trained reference models for the
full likelihood-ratio attack.
"""
from __future__ import annotations

import argparse, csv, json, os, pickle, random, sys
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score

def boot(scores, labels, seed, rounds):
    rng=np.random.default_rng(seed); p=np.flatnonzero(labels==1); n=np.flatnonzero(labels==0); out=[]
    for _ in range(rounds):
        ix=np.r_[rng.choice(p,len(p),True),rng.choice(n,len(n),True)]
        out.append(float(roc_auc_score(labels[ix],scores[ix])))
    return float(np.quantile(out,.025)),float(np.quantile(out,.975))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidates',type=Path,required=True); ap.add_argument('--mtnet-root',type=Path,required=True)
    ap.add_argument('--data-parent',type=Path,required=True); ap.add_argument('--city',required=True); ap.add_argument('--model',type=Path,required=True)
    ap.add_argument('--max-route-edges',type=int,default=100); ap.add_argument('--mc-draws',type=int,default=16)
    ap.add_argument('--max-per-class',type=int,default=71); ap.add_argument('--bootstrap',type=int,default=5000); ap.add_argument('--seed',type=int,default=20260717); ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(); cp=a.candidates.resolve(); model_path=a.model.resolve(); parent=a.data_parent.resolve(); out=a.out.resolve()
    with cp.open('rb') as f: records=pickle.load(f)['records']
    rng=np.random.default_rng(a.seed); chosen=[]
    for lab in (0,1):
        rows=[x for x in records if int(x['label'])==lab]
        chosen += [rows[i] for i in rng.choice(len(rows),min(len(rows),a.max_per_class),False)]
    rng.shuffle(chosen)
    root=a.mtnet_root.resolve(); os.chdir(root); sys.path.insert(0,str(root))
    import torch
    from util import config
    import mtnet
    config.DATA_BASE=str(parent)+os.sep; config.CITY=a.city; config.TRAJ_FIX_LEN=a.max_route_edges+1
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(a.seed)
    model=mtnet.Model(); ckpt=torch.load(model_path,map_location=config.device); model.load_state_dict(ckpt['state_dict']); model.eval()
    official=model.step
    def compatible(xt,slot,hs,cs): return official(xt,slot.long(),hs,cs)
    model.step=compatible
    lengths=[0.0]
    with (parent/a.city/'edge_property.txt').open(encoding='utf8') as f:
        for line in f:
            fields=line.split(',',4); lengths.append(float(fields[1]))
    def score(item):
        route=[int(x) for x in item['route']][:a.max_route_edges]
        valid=len(route)-1
        x=route+[0]*(a.max_route_edges-len(route)); target=route[1:]+[0]*(a.max_route_edges-len(route)+1)
        weights=np.asarray([lengths[e] if e<len(lengths) else 0.0 for e in route],float); weights=np.maximum(weights,1.0); elapsed=np.r_[0.0,np.cumsum(weights[:-1])/weights.sum()*float(item['duration_seconds'])]
        start=(float(item['departure'])+8*3600)%config.T_LOOP; times=(start+np.r_[elapsed,np.zeros(a.max_route_edges-len(route))])%config.T_LOOP
        xt=torch.tensor([x],dtype=torch.long,device=config.device); dt=torch.tensor([times/config.TRANGE_BASE],dtype=torch.float32,device=config.device); yt=torch.tensor(target[:valid],dtype=torch.long,device=config.device)
        vals=[]
        with torch.no_grad():
            for _ in range(a.mc_draws):
                logp,_=model(xt,dt); logp=logp.view(1,a.max_route_edges,-1)[0,:valid]
                adjs=model.adj[xt[0,:valid]]; matches=(adjs==yt[:,None]).float().argmax(dim=1)
                vals.append(float(logp[torch.arange(valid,device=config.device),matches].mean().item()))
        return float(np.mean(vals))
    scores=np.asarray([score(x) for x in chosen]); labels=np.asarray([int(x['label']) for x in chosen]); low,high=boot(scores,labels,a.seed,a.bootstrap)
    row={'attack':'MTNet_teacher_forced_route_NLL_screen','auc':float(roc_auc_score(labels,scores)),'auc_bootstrap95_low':low,'auc_bootstrap95_high':high,'members':int((labels==1).sum()),'nonmembers':int((labels==0).sum()),'mc_draws':a.mc_draws,'scope':'target likelihood screening; not reference-calibrated LiRA/RMIA'}
    out.parent.mkdir(parents=True,exist_ok=True); out.with_suffix('.json').write_text(json.dumps({'threat_model':'white-box target logits; known candidate route, start edge, and departure time','result':row},indent=2),encoding='utf8')
    with out.with_suffix('.csv').open('w',newline='',encoding='utf8') as f: w=csv.DictWriter(f,fieldnames=row); w.writeheader(); w.writerow(row)
    print(json.dumps(row,indent=2),flush=True)
if __name__=='__main__': main()

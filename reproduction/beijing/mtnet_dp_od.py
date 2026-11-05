"""Portable entry for the independently trained MTNet + DP coarse24 OD variant.

Model epsilon 1.0 plus OD epsilon 0.4; delta 1e-5; replacement adjacency.
This is not an endpoint retrofit of an ordinary epsilon-1.4 MTNet model.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

from preprocess.dataset_config import load_config
from preprocess.dataset_contract import sha

ROOT=Path(__file__).resolve().parent

def engine(out,dataset):
    file=ROOT/'vendor/mtnet/dp_od_variant.py'
    spec=importlib.util.spec_from_file_location('portable_mtnet_dp_od',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.HERE=Path(out).resolve();module.DATASET=dataset
    return module

def binding(config,prepared,public_edges,population,device):
    c=load_config(config,ROOT);p=lambda key:(ROOT/c['paths'][key]).resolve()
    if c['epsilon']!=1.4:raise ValueError('This variant protocol is fixed at total epsilon=1.4 (1.0 + 0.4)')
    prepared=Path(prepared).resolve();mp=prepared/'full_preparation_manifest.json'
    meta=json.loads(mp.read_text('utf-8-sig'))
    n=c['slots'] if population=='full' else c['train_slots']
    scope='full_corpus' if population=='full' else 'strict_tstr'
    if meta['dataset_id']!=c['frozen_dataset_id'] or meta['input_count']!=n or meta['evaluation_scope']!=scope:
        raise ValueError('MTNet preparation city/population/scope differs; do not reuse a full model for train')
    if meta['paper_constraints']['max_route_edges']!=20:raise ValueError('Original L20 preprocessing required')
    if meta['real_roads_sha256']!=sha(p('real_routes')):raise ValueError('Prepared road population changed')
    if meta['input_sha256']!=sha(p('real') if population=='full' else p('train')):raise ValueError('Prepared selected population changed')
    indices=meta['selected_frozen_indices']
    if population=='full' and indices!=list(range(n)):raise ValueError('Full slots must cover the entire frozen population')
    if population=='train':
        train_file=p('prepared')/'train_split.json'
        if indices!=json.loads(train_file.read_text())['indices']:raise ValueError('Training split differs')
    author=prepared/'data/beijing_roads_l20'
    paths=[Path(config).resolve(),mp,p('real_routes'),p('cache') if 'cache' in c['paths'] else p('metric_cache'),Path(public_edges).resolve()]
    for name,h in meta['data_files_sha256'].items():
        file=author/name
        if sha(file)!=h.lower():raise ValueError('MTNet author input changed: '+name)
        paths.append(file)
    native=ROOT/'vendor/mtnet'
    helper=native/'train_native_mtnet_dpsgd_paper.py';lock=native/'canonical_mtnet_source_lock.json'
    paths.extend([helper,lock])
    for name,h in json.loads(lock.read_text())['files_sha256'].items():
        file=native/'official'/name
        if sha(file)!=h.lower():raise ValueError('Original MTNet source changed: '+name)
        paths.append(file)
    return dict(dataset_id=c['frozen_dataset_id'],dataset=c['dataset'],scope=population,public_slots=n,
                selected_indices=indices,roads=str(p('real_routes')),cache=str(p('metric_cache')),
                public_edges=str(Path(public_edges).resolve()),author_data=str(author),official=str(native/'official'),
                source_lock=str(lock),helper=str(helper),device=device,
                bindings={str(file):sha(file) for file in paths})

def guard_training(c):
    """Conservative admission only; never stop unrelated workloads."""
    import psutil
    import torch
    info=json.loads((Path(c['author_data'])/'native_input_manifest.json').read_text())
    # Embeddings dominate on large graphs. Include gradients, Adam and vmap buffers.
    model=max(1,info['edge_embedding_rows'])*160*4+8*1024**2
    need=model*10+512*1024**2
    if psutil.virtual_memory().available<need:raise MemoryError(f'Training requires at least {need/1024**3:.2f} GiB available RAM; do not stop other workloads')
    if shutil.disk_usage(Path(c['author_data'])).free<model*5+512*1024**2:raise OSError('Insufficient disk for independent checkpoint and release')
    if c['device']=='cuda':
        if not torch.cuda.is_available():raise RuntimeError('CUDA requested but not available')
        free,_=torch.cuda.mem_get_info()
        if free<need:raise MemoryError('Insufficient free CUDA memory for independent variant training')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','graph','check','probe','train','generate'])
    p.add_argument('--config',type=Path)
    p.add_argument('--mtnet-prepared',type=Path)
    p.add_argument('--public-edges',type=Path)
    p.add_argument('--population',choices=['full','train'],default='full')
    p.add_argument('--device',choices=['cuda','cpu'],default='cuda',help='Explicit CPU is allowed, never a silent fallback')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--resume',action='store_true',help='Resume the same private training checkpoint, not a fresh 30-epoch run')
    a=p.parse_args();start=time.perf_counter();out=a.out.resolve()
    if a.stage=='prepare':
        if a.resume:p.error('--resume is only for train')
        if not all([a.config,a.mtnet_prepared,a.public_edges]):p.error('prepare requires --config, --mtnet-prepared and --public-edges')
        if out.exists():raise FileExistsError('Choose a fresh independent variant directory')
        c=binding(a.config,a.mtnet_prepared,a.public_edges,a.population,a.device)
        out.mkdir(parents=True)
        (out/'workflow.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        if a.config or a.mtnet_prepared or a.public_edges:p.error('Later stages read the frozen workflow in --out; do not rebind inputs')
        c=json.loads((out/'workflow.json').read_text('utf-8'))
        if c['scope']!=a.population:raise ValueError('Wrong population; use separate full/train variant directories')
        if a.resume and a.stage!='train':p.error('--resume is only for train')
    module=engine(out,c['dataset_id'])
    if a.stage in ['probe','train']:guard_training(c)
    try:
        if a.stage in ['prepare','graph']:getattr(module,a.stage)(c)
        elif a.stage=='check':
            import numpy as np
            import psutil
            import torch
            module.verify(c)
            info=json.loads((Path(c['author_data'])/'native_input_manifest.json').read_text())
            required=info['edge_embedding_rows']*160*4*3+256*1024**2
            if psutil.virtual_memory().available<required:raise MemoryError('Insufficient RAM for model import/forward check')
            torch.set_num_threads(2)
            model,_,tc=module.model_and_helper(c)
            data=np.load(out/'private_prepared'/f"{c['scope']}.npz")
            if len(data['x']):
                x=torch.as_tensor(data['x'][:1],device=tc.device)
                dpt=torch.as_tensor(data['dpt'][:1],device=tc.device)
                y=torch.as_tensor(data['y'][:1],device=tc.device).reshape(-1)
                with torch.no_grad():
                    logits,times=model(x,dpt)
                    if not torch.isfinite(logits[torch.arange(len(y),device=tc.device),y]).all() or not torch.isfinite(times).all():
                        raise ValueError('Non-finite real-record model forward')
            module.dump(out/'private_model_check.json',dict(status='PASS',active_rows=int(len(data['x'])),parameter_count=sum(p.numel() for p in model.parameters()),training_updates=0,scope='private real-record forward check, not trained release'))
        elif a.stage in ['probe','train']:module.train(c,c['scope'],a.stage=='probe',a.resume)
        else:module.generate(c,c['scope'])
    except BaseException as error:
        (out/f'failed_{a.stage}_{time.time_ns()}.json').write_text(json.dumps(dict(status='FAILED',error=repr(error),seconds=time.perf_counter()-start)))
        raise
    receipt=dict(status='COMPLETE',stage=a.stage,population=c['scope'],dataset_id=c['dataset_id'],
                 seconds=time.perf_counter()-start,wrapper_sha256=sha(Path(__file__)),engine_sha256=sha(module.__file__),
                 internal_argv=[sys.executable,*sys.argv],command_kind='internal argv, not proof of documented outer command')
    (out/f'receipt_{a.stage}.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()

"""Isolated fixed-population MTNet + separately DP coarse OD experiment.

Private diagnostics/checkpoints are deliberately outside each release directory.
Author source and previous results remain immutable.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pickle
import secrets
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
DATASET = None  # Set by the portable wrapper from the frozen city configuration.


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def dump(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def load(p):
    with gzip.open(p, 'rb') as f: return pickle.load(f)


def save(p, value):
    with gzip.open(p, 'wb') as f: pickle.dump(value, f, pickle.HIGHEST_PROTOCOL)


def verify(c):
    if c['dataset_id'] != DATASET: raise ValueError('Wrong city binding')
    for p, h in c['bindings'].items():
        if sha(p) != h: raise ValueError('Changed bound input: ' + p)


def epsilon(sigma, steps=30, delta=1e-5):
    orders = np.concatenate((np.arange(1.1, 32, .1), np.arange(32, 513)))
    return float(np.min(steps * 2 * orders / sigma**2 + np.log(1 / delta) / (orders-1)))


def sigma_for_budget(target=1.):
    if not math.isfinite(target) or target<=epsilon(10000.):
        raise ValueError('Budget outside supported accountant calibration range')
    lo, hi = .01, 10000.
    for _ in range(100):
        mid = (lo + hi) / 2
        if epsilon(mid) > target: lo = mid
        else: hi = mid
    return hi


def tensor_row(route, stamps, adj):
    """Independent per-record transform with public constants only; None=zero."""
    if not 0 < len(route) <= 20 or len(stamps) != len(route)+1: return None
    if not all(math.isfinite(t) for t in stamps): return None
    if any(t < 0 or t >= 6000 for t in stamps[1:]): return None
    traj = list(route) + [0] * (21-len(route))
    # Match author's integer cumulative departure encoding, not private max.
    tdpt = [int(t) for t in stamps] + [0]*(21-len(route))
    tdpt[0] = (tdpt[0]+8*3600) % 604800
    for i in range(1, 22): tdpt[i] = (tdpt[i-1]+tdpt[i]) % 604800
    costs = list(stamps[1:]) + [0.]*(21-len(route))
    ys = []
    for x, y in zip(traj[:-1], traj[1:]):
        matches = np.flatnonzero(adj[x] == y)
        if len(matches) != 1: return None
        ys.append(int(matches[0]))
    return (traj[:-1], np.asarray(tdpt[1:-1])/1800,
            np.asarray(costs[1:])/6000., ys)


def prepare(c):
    """Align already prepared MTNet rows to full fixed-population slots."""
    verify(c)
    target = HERE/'private_prepared'
    target.mkdir(exist_ok=False)
    raw = load(c['roads'])
    indices = c['selected_indices']
    scope = c['scope']
    if len(indices) != c['public_slots'] or len(set(indices)) != len(indices):
        raise ValueError('Invalid fixed population')
    cache = load(c['cache']); labels = cache['labels24']; edges = cache['edge_nodes']
    author = Path(c['author_data'])
    adj = np.loadtxt(author/'edge_adj.txt', delimiter=',', dtype=np.int64, ndmin=2)
    adj = np.concatenate((np.full((1, adj.shape[1]), -1), adj, np.full((1, adj.shape[1]), -1)))
    adj = np.column_stack((adj, np.zeros(len(adj), dtype=np.int64)))
    adj[adj == -1] = len(adj)-1
    routes = [[int(x) for x in line.split()][:-1] for line in (author/'trajs_demo.csv').read_text().splitlines()]
    stamps = [[float(x) for x in line.split()] for line in (author/'tstamps_demo.csv').read_text().splitlines()]
    if len(routes) != len(stamps): raise ValueError('Timestamp row count mismatch')
    retained = [i for i in indices if raw[i]['accepted'] and 0 < len(raw[i]['cpath']) <= 20]
    if len(retained) != len(routes): raise ValueError('Prepared author records do not match selected population')
    selected = [retained[int(j)] for j in np.random.default_rng(20260711).permutation(len(retained))]
    tensors = {}
    for i, route, times in zip(selected, routes, stamps):
        if tuple(route) != tuple(raw[i]['cpath']): raise ValueError('Author row identity/order mismatch')
        row = tensor_row(route, times, adj)
        if row is not None: tensors[i] = row
    active = [i for i in indices if i in tensors]
    fields = [np.asarray([tensors[i][k] for i in active], dtype=np.int64 if k in (0,3) else np.float32).reshape((-1,20)) for k in range(4)]
    np.savez_compressed(target/(scope+'.npz'), x=fields[0], dpt=fields[1], cost=fields[2], y=fields[3], active_indices=active)
    hist = np.zeros((24,24))
    for i in indices:
        route = raw[i]['cpath']
        if not route: continue
        u,v = edges[route[0]][0], edges[route[-1]][1]
        hist[int(labels[u]), int(labels[v])] += 1
    od_budget=c.get('epsilon_od',.4)
    noisy = hist + np.random.default_rng().laplace(0., 2./od_budget, (24,24))
    release = HERE/('release_'+scope); release.mkdir(exist_ok=False)
    dump(release/'dp_od.json', dict(dataset_id=DATASET, population=scope, public_slots=len(indices),
        noisy_od=noisy.tolist(), epsilon_od=od_budget, sensitivity_l1=2., laplace_scale=2./od_budget,
        privacy_unit='one frozen road record, replacement adjacency', seed_policy='private OS entropy'))
    receipt = dict(public_slots=len(indices), active_private=len(active),
        training_npz_sha256=sha(target/(scope+'.npz')), dp_od_sha256=sha(release/'dp_od.json'))
    dump(target/'manifest.json', dict(dataset_id=DATASET, sources=c['bindings'], scopes={scope:receipt},
        normalization='public 6000, independent record transforms', private_diagnostic=True))
    print('PREPARED', scope, len(active), flush=True)


def model_and_helper(c):
    import torch
    sys.path.insert(0, c['official'])
    from util import config
    config.DATA_BASE = str(Path(c['author_data']).parent)+os.sep
    config.CITY = Path(c['author_data']).name
    config.TRAJ_FIX_LEN=21; config.TCOST_MAX=6000
    config.device = torch.device(c.get('device','cuda'))
    if config.device.type == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable; no silent fallback')
    lock = read(c['source_lock'])
    for name,h in lock['files_sha256'].items():
        assert sha(Path(c['official'])/name) == h.lower(), name
    import mtnet
    spec = importlib.util.spec_from_file_location('audited_training_helper', c['helper'])
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    helper.install_vmap_step_compatibility(mtnet, config)
    torch.manual_seed(20260712)
    model = mtnet.Model(device=config.device)
    return model, helper, config


def train(c, scope, probe=False, resume=False):
    import torch
    verify(c)
    torch.set_num_threads(2)
    model,helper,config = model_and_helper(c)
    if config.device.type not in ('cuda','cpu'): raise RuntimeError('Explicit cuda/cpu required')
    meta = read(HERE/'private_prepared/manifest.json')['scopes'][scope]
    npz = HERE/'private_prepared'/(scope+'.npz')
    assert sha(npz) == meta['training_npz_sha256']
    arrays = np.load(npz)
    x = torch.as_tensor(arrays['x'], device=config.device)
    dpt = torch.as_tensor(arrays['dpt'], device=config.device)
    cost = torch.as_tensor(arrays['cost'], device=config.device)
    y = torch.as_tensor(arrays['y'], device=config.device)
    private = HERE/('private_'+scope+('_probe' if probe else '_training'))
    private.mkdir(exist_ok=resume)
    optimizer = torch.optim.Adam(model.parameters(), lr=.001)
    n = meta['public_slots']; sigma = sigma_for_budget(c.get('epsilon_model',1.))
    protocol = dict(population=scope, public_slots=n, epsilon_model=c.get('epsilon_model',1.), delta=1e-5, epochs=30,
        fixed_population_zero_contribution=True, sensitivity_l2=2., clip_C=1., sigma=sigma,
        epsilon_bound=epsilon(sigma), normalization=6000, private_input_sha256=sha(npz),
        implementation_sha256=sha(__file__), source_bindings=c['bindings'])
    start_epoch = 0
    if resume:
        saved = torch.load(private/'checkpoint.pt', map_location=config.device, weights_only=False)
        assert saved['protocol'] == protocol
        model.load_state_dict(saved['model']); optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['cpu_rng'].cpu())
        if config.device.type=='cuda':torch.cuda.set_rng_state(saved['gpu_rng'].cpu())
        start_epoch = saved['next_epoch']
    else:
        # Public initial weights are fine. All gradient noise and later random
        # stochastic training draws instead use this non-released entropy.
        torch.manual_seed(secrets.randbits(63))
    params = dict(model.named_parameters()); buffers = dict(model.named_buffers())
    start = time.perf_counter()
    for epoch in range(start_epoch, 1 if probe else 30):
        began = time.perf_counter(); count = min(3,len(x)) if probe else len(x)
        def progress(done,total):
            if done % 50 == 0 or done == total:
                record = dict(epoch=epoch+1, active_done=done, active_total=total,
                    fixed_population=n, elapsed_seconds=time.perf_counter()-start)
                dump(private/'progress.json', record); print(json.dumps(record), flush=True)
        summed,_,_,_ = helper.vectorized_clipped_sum(model,params,buffers,x[:count],dpt[:count],cost[:count],y[:count],1.,1,progress,.1)
        optimizer.zero_grad(set_to_none=True)
        with torch.no_grad():
            for name,p in params.items():
                noise = torch.randn_like(p).mul_(sigma)
                p.grad = summed[name].add_(noise).div_(n)
                del noise
        optimizer.step(); del summed
        boundary=dict(protocol=protocol, model=model.state_dict(), optimizer=optimizer.state_dict(),
            next_epoch=epoch+1, cpu_rng=torch.get_rng_state(), gpu_rng=torch.cuda.get_rng_state() if config.device.type=='cuda' else None)
        tmp=private/'checkpoint.tmp'; torch.save(boundary,tmp); tmp.replace(private/'checkpoint.pt')
        dump(private/'progress.json', dict(epoch=epoch+1, total_epochs=1 if probe else 30,
            active_done=count, active_total=count, epoch_seconds=time.perf_counter()-began,
            elapsed_seconds=time.perf_counter()-start, gpu_peak_bytes=torch.cuda.max_memory_allocated() if config.device.type=='cuda' else 0))
        print('UPDATE_COMPLETE', epoch+1, time.perf_counter()-began, flush=True)
    if probe:
        dump(private/'probe_complete.json', dict(status='PASS', rows=count, public_denominator=n,
            seconds=time.perf_counter()-start, gpu_peak_bytes=torch.cuda.max_memory_allocated() if config.device.type=='cuda' else 0))
        return
    release=HERE/('release_'+scope)
    if (release/'model.pt').exists(): raise FileExistsError(release/'model.pt')
    torch.save(dict(state_dict=model.state_dict()),release/'model.pt')
    # No retained record counts, private RNG state, losses or checkpoints in release.
    dump(release/'training_manifest.json', dict(status='COMPLETE', dataset_id=DATASET,
        method='MTNet + DP OD (coarse24)', public_slots=n, population=scope,
        epsilon_model=c.get('epsilon_model',1.), epsilon_od=c.get('epsilon_od',.4), epsilon_total=c.get('epsilon_total',1.4), delta=1e-5,
        sigma=sigma, epsilon_model_bound=epsilon(sigma), updates=30,
        zero_contribution_slots=True, public_time_normalization=6000,
        adjacency='fixed frozen road population replacement; not raw GPS end-to-end',
        source_lock_sha256=sha(c['source_lock']), implementation_sha256=sha(__file__),
        model_sha256=sha(release/'model.pt'), dp_od_sha256=sha(release/'dp_od.json')))


def graph(c):
    """Public multi-source distance to each coarse destination region."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    verify(c); out=HERE/'public_graph';out.mkdir(exist_ok=False)
    cache=load(c['cache']); labels=cache['labels24']; edge_nodes=cache['edge_nodes']
    vertices=sorted(labels); vi={v:i for i,v in enumerate(vertices)}
    maximum=max(map(int,edge_nodes))+2
    u=np.full(maximum,-1,dtype=np.int32);v=u.copy();length=np.ones(maximum)
    with gzip.open(c['public_edges'],'rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line); eid=int(r['edge_id']); a,b=edge_nodes[eid]
            assert (str(a),str(b))==(r['u'],r['v'])
            u[eid],v[eid]=vi[a],vi[b];length[eid]=max(float(r['length_m']),.001)
    valid=np.flatnonzero(u>=0)
    if set(map(int,valid))!=set(map(int,edge_nodes)):raise ValueError('Public graph coverage differs from selected city')
    # Parallel public edges use minimum, never COO's sum of parallel lengths.
    pairs={}
    for e in valid:
        key=(int(v[e]),int(u[e]));pairs[key]=min(pairs.get(key,math.inf),length[e])
    rev=csr_matrix(([w for w in pairs.values()],([k[0] for k in pairs],[k[1] for k in pairs])),shape=(len(vertices),len(vertices)))
    zones=np.asarray([int(labels[n]) for n in vertices],dtype=np.int32)
    dist=np.lib.format.open_memmap(out/'distances.npy',mode='w+',dtype=np.float64,shape=(24,len(vertices)))
    for z in range(24):
        dist[z]=dijkstra(rev,directed=True,indices=np.flatnonzero(zones==z),min_only=True)
        dist.flush();print('PUBLIC_DISTANCES',z,flush=True)
    np.savez_compressed(out/'edges.npz',u=u,v=v,length=length,zones=zones,valid=valid)
    dump(out/'manifest.json',dict(status='COMPLETE', public_only=True, cache_sha256=sha(c['cache']),
        public_edges_sha256=sha(c['public_edges']), distances_sha256=sha(out/'distances.npy'),
        edges_sha256=sha(out/'edges.npz')))


def generate(c, scope):
    import torch
    torch.set_num_threads(2)
    # Only public resources, DP OD, and DP model are opened here; no raw roads.
    release=HERE/('release_'+scope); meta=read(release/'training_manifest.json')
    assert meta['status']=='COMPLETE' and sha(release/'model.pt')==meta['model_sha256']
    if (meta['dataset_id']!=DATASET or meta['population']!=scope or meta['public_slots']!=c['public_slots']
            or meta['epsilon_model']!=c.get('epsilon_model',1.) or meta['epsilon_od']!=c.get('epsilon_od',.4) or meta['updates']!=30
            or meta['epsilon_total']!=c.get('epsilon_total',1.4)):
        raise ValueError('Require this independent MTNet+DPOD model and population, not ordinary MTNet')
    assert sha(release/'dp_od.json')==meta['dp_od_sha256']
    gm=read(HERE/'public_graph/manifest.json')
    assert sha(HERE/'public_graph/distances.npy')==gm['distances_sha256']
    assert sha(HERE/'public_graph/edges.npz')==gm['edges_sha256']
    if gm['cache_sha256']!=c['bindings'][c['cache']] or gm['public_edges_sha256']!=c['bindings'][c['public_edges']]:
        raise ValueError('Public graph belongs to another workflow')
    model,_,config=model_and_helper(c)
    model.load_state_dict(torch.load(release/'model.pt',map_location=config.device,weights_only=False)['state_dict']);model.eval()
    torch.manual_seed(20261022);rng=np.random.default_rng(20261022)
    public=np.load(HERE/'public_graph/edges.npz');u,v,zones,valid=[public[k] for k in ['u','v','zones','valid']]
    dist=np.load(HERE/'public_graph/distances.npy',mmap_mode='r')
    prob=np.maximum(np.asarray(read(release/'dp_od.json')['noisy_od']),0).ravel()
    if not prob.sum():prob[:]=1.
    requests=rng.choice(576,meta['public_slots'],p=prob/prob.sum())
    roads=[[] for _ in requests];reasons=['unreachable_public_OD' for _ in requests]
    adj=model.adj.detach().cpu().numpy();start=time.perf_counter()
    with torch.no_grad():
        for dest in range(24):
            by_origin={o:valid[(zones[u[valid]]==o)&np.isfinite(dist[dest,v[valid]])] for o in range(24)}
            slots=[];origins=[]
            for s in np.flatnonzero(requests%24==dest):
                domain=by_origin[int(requests[s]//24)]
                if len(domain):slots.append(int(s));origins.append(int(rng.choice(domain)))
            for offset in range(0,len(slots),256):
                ss=slots[offset:offset+256];current=np.asarray(origins[offset:offset+256])
                for s,e in zip(ss,current):roads[s]=[int(e)]
                hs,cs=model.init_h(len(ss),config.device);departure=torch.zeros(len(ss),device=config.device)
                # Public strictly decreasing potential bounds steps by vertex count.
                for _ in range(len(zones)+1):
                    keep=np.asarray([zones[v[e]]!=dest for e in current],dtype=bool)
                    for j,flag in enumerate(keep):
                        if not flag:reasons[ss[j]]='accepted'
                    if not keep.any():break
                    ss=[s for s,k in zip(ss,keep) if k];current=current[keep]
                    mask=torch.as_tensor(keep,device=config.device)
                    hs=[h[mask] for h in hs];cs=[h[mask] for h in cs];departure=departure[mask]
                    xt=torch.as_tensor(current,device=config.device)
                    (logits,times),hs,cs=model.step(xt,(departure/1800).long(),hs,cs)
                    neighbors=adj[current];safe=np.clip(neighbors,0,len(v)-1)
                    allowed=(neighbors>0)&(neighbors<len(v))&(v[safe]>=0)
                    allowed &= dist[dest,np.maximum(v[safe],0)] < dist[dest,v[current]][:,None]
                    if not allowed.any(axis=1).all():raise ValueError('Public reachable route has no decreasing official adjacency')
                    logits=logits.masked_fill(~torch.as_tensor(allowed,device=config.device),float('-inf'))
                    choice=torch.softmax(logits,dim=1).multinomial(1).flatten()
                    batch=torch.arange(len(ss),device=config.device)
                    nxt=model.adj[xt][batch,choice]
                    departure=(departure+torch.sigmoid(times[batch,choice])*6000).remainder(604800)
                    current=nxt.cpu().numpy()
                    for s,e in zip(ss,current):roads[s].append(int(e))
                else:raise ValueError('Strict potential termination invariant failed')
            print('GENERATED_DESTINATION',scope,dest,'SLOTS',sum(r=='accepted' for r in reasons),flush=True)
    for s,route in enumerate(roads):
        if not route:continue
        assert reasons[s]=='accepted'
        assert zones[u[route[0]]]==requests[s]//24 and zones[v[route[-1]]]==requests[s]%24
        assert all(v[a]==u[b] for a,b in zip(route,route[1:]))
    out=release/'native_release';out.mkdir(exist_ok=False)
    with (out/'routes.pkl').open('xb') as f:pickle.dump(roads,f,pickle.HIGHEST_PROTOCOL)
    rows=[dict(source_index=i,cpath=route,accepted=bool(route),connected=bool(route),reason=reasons[i]) for i,route in enumerate(roads)]
    save(out/'synthetic_routes.pkl.gz',rows)
    np.save(out/'sampled_coarse_od.npy',np.column_stack((requests//24,requests%24)))
    dump(out/'manifest.json',dict(status='COMPLETE', method='MTNet + DP OD (coarse24)',
        dataset_id=DATASET, population=scope, records=len(roads), generated_records=len(roads),
        valid=sum(bool(r) for r in roads), epsilon_total=c.get('epsilon_total',1.4),delta=1e-5,
        model_sha256=sha(release/'model.pt'), training_manifest_sha256=sha(release/'training_manifest.json'),
        dp_od_sha256=sha(release/'dp_od.json'), public_graph_manifest_sha256=sha(HERE/'public_graph/manifest.json'),
        private_input_access_during_generation=False,post_generation_matching=False,
        decoding='DP coarse24 OD; neural weighted strictly public-distance-decreasing successors; no fallback',
        seconds=time.perf_counter()-start,outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()}))

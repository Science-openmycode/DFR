"""Generate same-DP-endpoint controls using the selected city's public graph.

Consumes saved research endpoint measurements, never original trajectories.
Random choice is uniform over outgoing distance-decreasing edges, not all paths.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np
from preprocess.dataset_config import load_config
from preprocess.dataset_contract import sha
from preprocess.dfr_author_roads import bind_author_domain
from tools.endpoint_control_core import replay, random_route
from tools.convert_native_node_pairs import resolve_pairs, convert

ROOT=Path(__file__).resolve().parent

def load(path):
    with gzip.open(path,'rb') as f:return pickle.load(f)

def save(path,value):
    with gzip.open(path,'wb',compresslevel=3) as f:pickle.dump(value,f,pickle.HIGHEST_PROTOCOL)

def check_boundary(route,s,d):
    return bool(route) and route[0]==s and route[-1]==d and all(a[1]==b[0] for a,b in zip(route,route[1:]))

def generate_routes(router,endpoints,seed,progress=None):
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    nodes=sorted({v for e in router.length for v in e});index={v:i for i,v in enumerate(nodes)}
    edges=list(router.length)
    reverse=csr_matrix(([router.length[e] for e in edges],
                        ([index[e[1]] for e in edges],[index[e[0]] for e in edges])),shape=(len(nodes),len(nodes)))
    groups=defaultdict(list)
    for i,(s,d) in enumerate(endpoints):
        if s not in router.length or d not in router.length:raise ValueError('Unknown endpoint edge')
        groups[d[0]].append(i)
    random=[() for _ in endpoints];shortest=[() for _ in endpoints];counts=Counter();done=0
    for goal,slots in groups.items():
        dist=dijkstra(reverse,indices=index[goal],directed=True)
        for slot in slots:
            s,d=endpoints[slot]
            random[slot]=random_route(router,dist,index,s,d,seed,slot)
            # Unreachable requests keep an empty slot, never a fake single-edge arrival.
            if random[slot]:
                shortest[slot]=tuple(router.path(s,d) or ()) if s!=d else (s,)
                if not check_boundary(shortest[slot],s,d):raise ValueError('Shortest path did not reach requested destination')
                if not check_boundary(random[slot],s,d):raise ValueError('Random path boundary/connectivity mismatch')
                counts['valid']+=1
            else:counts['unreachable']+=1
            done+=1
        if progress:progress(done,len(endpoints))
    return random,shortest,dict(counts)

def prepare(config,release,lineage,out,check_only=False):
    started=time.perf_counter();c=load_config(config,ROOT)
    path=lambda k:(ROOT/c['paths'][k]).resolve()
    release=Path(release).resolve();out=Path(out).resolve()
    if out.exists():raise FileExistsError('Choose a new control output directory')
    manifest_path=release/'manifest.json';manifest=json.loads(manifest_path.read_text('utf-8-sig'))
    audit=json.loads(Path(lineage).read_text('utf-8-sig'))
    if audit.get('status')!='DONE':raise ValueError('DFR source generation has not completed')
    if audit.get('epsilon')!=c['epsilon']:raise ValueError('Source DFR privacy budget differs')
    identity=audit.get('dataset',{})
    if identity.get('dataset_id')!=c['frozen_dataset_id']:raise ValueError('Source DFR belongs to another dataset')
    for key,field in [('network','network_sha256'),('metric_cache','edge_cache_sha256')]:
        if audit.get(field)!=sha(path(key)):raise ValueError('Source DFR public resource differs: '+key)
    if manifest.get('classification')!='RESEARCH_ONLY_REPRODUCIBLE_NOISE_DO_NOT_RELEASE':
        raise ValueError('Replay requires a reproducible research release, not formal/oracle output')
    seed=manifest.get('research_seed',manifest.get('seed',audit.get('seed')))
    if type(seed) is not int:raise ValueError('Replay requires the saved reproducible research seed')
    if seed!=c['seed'] or seed!=audit.get('seed') or manifest.get('fixed_output_slots')!=c['slots']:raise ValueError('DFR seed/full population differs from config')
    transcript=release/'dp_transcript.pkl.gz'
    expected=[v for k,v in manifest['outputs'].items() if Path(k.replace('\\','/')).name=='dp_transcript.pkl.gz']
    if len(expected)!=1 or sha(transcript)!=expected[0].lower():raise ValueError('Transcript binding mismatch')
    legacy=path('legacy')
    core_path=legacy/'generation/mtr_dfr/algorithm/run_minimal_strong_family.py'
    sys.path[:0]=[str(core_path.parent),str(legacy/'generation/mtr_dfr/dependencies'),str(legacy/'evaluation')]
    spec=importlib.util.spec_from_file_location('endpoint_control_dfr_core',core_path)
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    if audit.get('core_sha256')!=sha(core_path):raise ValueError('Source DFR core differs; do not silently replay another version')
    core.NETWORK=path('network')
    author=bind_author_domain(core,c,ROOT,path('network'))
    original_author=audit.get('public_author_domain',audit.get('author_road_resources'))
    if bool(author)!=bool(original_author):raise ValueError('Source DFR author-road domain differs')
    if author and any(author.get(k)!=original_author.get(k) for k in ['mode','manifest_sha256','mapping_sha256','exact_duplicate_road_aliases']):
        raise ValueError('Source DFR author-road resources differ')
    cache=load(path('metric_cache'))
    router=core.EdgeStateRouter(path('network'),cache['edge_nodes'],{None:{}},{None:{}},0.,0.)
    endpoints=replay(core,cache,router,load(transcript),c['slots'],seed)
    # Node namespaces join by verified shared edge IDs; never assume physical node IDs.
    required={tuple(e) for p in endpoints for e in p}
    resolve_pairs(cache['edge_nodes'],network=path('network'),required_pairs=required)
    report=dict(status='CHECKED_NOT_GENERATED',dataset=c['dataset'],dataset_id=c['frozen_dataset_id'],
                slots=len(endpoints),seed=seed,private_trajectory_access=False,additional_privacy_cost=0,
                endpoint_source='saved DFR DP transcript, same sampled requests; not real OD',
                random_rule='uniform outgoing distance-decreasing choice; not uniform over all paths',
                sources={str(p):sha(p) for p in [Path(config).resolve(),manifest_path,Path(lineage).resolve(),transcript,path('network'),path('metric_cache'),core_path,Path(__file__),ROOT/'tools/endpoint_control_core.py']},
                public_author_domain=author)
    if check_only:return report
    out.mkdir(parents=True)
    try:
        last=[-100,0.]
        def progress(n,total):
            now=time.perf_counter()
            if n==total or now-last[1]>=30:
                print(json.dumps(dict(processed=n,total=total,seconds=now-started)),flush=True);last[:]=[n,now]
        random,shortest,counts=generate_routes(router,endpoints,seed,progress)
        used={tuple(e) for routes in (random,shortest) for route in routes for e in route}
        pairs=resolve_pairs(cache['edge_nodes'],network=path('network'),required_pairs=used)
        save(out/'endpoints.pkl.gz',endpoints)
        for name,routes in [('SameEndpointRandom',random),('PublicShortest',shortest)]:
            folder=out/name;folder.mkdir()
            save(folder/'synthetic_routes.pkl.gz',convert(routes,pairs))
        report.update(status='COMPLETE',counts=counts,
                      outputs={str(p.relative_to(out)):sha(p) for p in out.rglob('*.pkl.gz')})
    except BaseException as e:
        report.update(status='FAILED',error=repr(e));raise
    finally:
        report['seconds']=time.perf_counter()-started
        (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','release','lineage','out']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--check-only',action='store_true');a=p.parse_args()
    print(json.dumps(prepare(a.config,a.release,a.lineage,a.out,a.check_only),ensure_ascii=False,indent=2))

if __name__=='__main__':main()

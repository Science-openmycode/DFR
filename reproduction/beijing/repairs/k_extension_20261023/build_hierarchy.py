"""Public-only nested endpoint partitions anchored at the frozen 384 map."""
import argparse
import collections
import gzip
import json
import math
import pickle
import sys
import time
from pathlib import Path
import numpy as np
from audit_existing import components, sha


def merge_hierarchy(base, coarse, edges, xy, targets):
    groups = {c:{n for n,v in base.items() if v==c} for c in sorted(set(base.values()))}
    parent = {c:coarse[next(iter(ns))] for c,ns in groups.items()}
    owner = dict(base)
    result = {len(groups):dict(owner)}
    while len(groups)>min(targets):
        centers={c:np.mean([xy[n] for n in ns], axis=0) for c,ns in groups.items()}
        pairs={tuple(sorted((owner[u],owner[v]))) for u,v in edges
               if owner[u]!=owner[v] and parent[owner[u]]==parent[owner[v]]}
        if not pairs:
            raise ValueError('Public coarse regions disconnected at cell level; cannot merge without a bridge')
        a,b=min(pairs,key=lambda pair:(float(np.sum((centers[pair[0]]-centers[pair[1]])**2)),pair))
        for n in groups[b]: owner[n]=a
        groups[a].update(groups.pop(b))
        if len(groups) in targets:
            remap={c:i for i,c in enumerate(sorted(groups))}
            result[len(groups)]={n:remap[c] for n,c in owner.items()}
    return result


def split_connected(ns, adjacency, xy):
    """Split a BFS tree at its most balanced edge; retain inherited islands."""
    remaining=set(ns)
    comps=[]
    while remaining:
        root=min(remaining)
        order=[root]; parent={root:None}; remaining.remove(root)
        for u in order:
            for v in sorted(adjacency[u]):
                if v in remaining:
                    remaining.remove(v); parent[v]=u; order.append(v)
        comps.append((order,parent))
    order,parent=max(comps,key=lambda x:(len(x[0]),-x[0][0]))
    if len(order)<2: raise ValueError('Cannot split a singleton main component')
    size={n:1 for n in order}
    for n in reversed(order[1:]):size[parent[n]]+=size[n]
    cut=min(order[1:],key=lambda n:(abs(len(order)-2*size[n]),n))
    side={order[0]:0}
    for n in order[1:]:side[n]=1 if n==cut else side[parent[n]]
    centers={s:np.mean([xy[n] for n in order if side[n]==s],axis=0) for s in (0,1)}
    for other,_ in comps:
        if other is order:continue
        center=np.mean([xy[n] for n in other],axis=0)
        s=min((0,1),key=lambda s:float(np.sum((center-centers[s])**2)))
        for n in other:side[n]=s
    assert set(side)==set(ns) and set(side.values())=={0,1}
    return side


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); started=time.perf_counter()
    if a.out.exists():raise FileExistsError(a.out)
    cfg=json.loads((a.root/'configs/beijing.json').read_text(encoding='utf-8'))
    with gzip.open(cfg['paths']['metric_cache'],'rb') as f:cache=pickle.load(f)
    frozen=json.loads((a.root/'partitions/partition384.json').read_text(encoding='utf-8'))
    assert frozen['metric_cache_sha256'].lower()==sha(cfg['paths']['metric_cache']).lower()
    assert frozen['network_sha256'].lower()==sha(cfg['paths']['network']).lower()
    base={int(n):int(c) for n,c in frozen['labels'].items()}
    edges=list(cache['edge_nodes'].values())
    import geopandas as gpd
    coords={}
    for row in gpd.read_file(cfg['paths']['network'])[['id','geometry']].itertuples(index=False):
        pair=cache['edge_nodes'].get(int(row.id))
        if pair is None or row.geometry is None:continue
        pts=list(row.geometry.coords)
        for n,point in zip(pair,(pts[0],pts[-1])):
            coords.setdefault(n,np.array([point[0]*math.cos(math.radians(39.95)),point[1]]))
    assert set(coords)==set(base)
    maps=merge_hierarchy(base,cache['labels24'],edges,coords,{24,48,96,192,384})
    adjacency={n:set() for n in base}
    for u,v in edges:
        if base[u]==base[v]:adjacency[u].add(v);adjacency[v].add(u)
    fine={}
    for c in range(384):
        ns={n for n,label in base.items() if label==c}
        fine.update({n:2*c+s for n,s in split_connected(ns,adjacency,coords).items()})
    maps[768]=fine
    sys.path.insert(0,str(a.root/'repairs/k_partition_20261020/algorithm'))
    from endpoint_partition import validate_partition
    reports={}
    for k,labels in sorted(maps.items()):
        validate_partition(cache,{str(n):c for n,c in labels.items()},k,8)
        quality=components(labels,edges)
        reports[k]=dict(disconnected_cells=sum(x['components']>1 for x in quality.values()),
                        nodes_outside_largest=sum(x['nodes']*(1-x['largest_fraction']) for x in quality.values()),
                        node_count_quantiles=np.quantile([x['nodes'] for x in quality.values()],[0,.25,.5,.75,1]).tolist(),cells=quality)
    for small,large in zip([24,48,96,192,384],[48,96,192,384,768]):
        parents=collections.defaultdict(set)
        for n,c in maps[large].items():parents[c].add(maps[small][n])
        assert all(len(v)==1 for v in parents.values()),(small,large)
    assert maps[384]==base
    a.out.mkdir(parents=True)
    for k,labels in sorted(maps.items()):
        payload={key:value for key,value in frozen.items() if key not in ('labels','k','construction','coarse_allocation')}
        payload.update(k=k,labels={str(n):c for n,c in sorted(labels.items())},
                       construction='Frozen384 anchor; successive adjacent centroid-distance merges within coarse24; 768 balanced BFS-tree edge split, inherited disconnected islands assigned by public centroid. Weak connectivity, not directed strong connectivity.',
                       anchor_sha256=sha(a.root/'partitions/partition384.json'),builder_sha256=sha(__file__))
        path=a.out/f'partition{k}.json';path.write_text(json.dumps(payload,sort_keys=True),encoding='utf-8')
        reports[k]['sha256']=sha(path)
    report=dict(status='PUBLIC_NESTED_HIERARCHY_VALIDATED',elapsed_seconds=time.perf_counter()-started,partitions=reports,
                network_sha256=frozen['network_sha256'],metric_cache_sha256=frozen['metric_cache_sha256'],source_sha256=sha(__file__))
    (a.out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:{key:v for key,v in d.items() if key!='cells'} for k,d in reports.items()}))


if __name__=='__main__':main()

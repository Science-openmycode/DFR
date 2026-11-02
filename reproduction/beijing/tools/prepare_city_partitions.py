"""Apply the preserved public nested K hierarchy to the selected city graph."""
import argparse
import gzip
import importlib.util
import json
import math
from pathlib import Path
import pickle
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_config import load_config
from preprocess.dataset_contract import sha

def prepare(config,out,ks):
    out=Path(out);started=time.perf_counter()
    if out.exists():raise FileExistsError(out)
    if not ks or set(ks)-{24,48,96,192,384,768}:raise ValueError('Use the registered public hierarchy K values')
    c=load_config(config,ROOT);path=lambda k:(ROOT/c['paths'][k]).resolve()
    with gzip.open(path('metric_cache'),'rb') as handle:cache=pickle.load(handle)
    source=ROOT/'repairs/k_extension_20261023/build_hierarchy.py'
    sys.path.insert(0,str(source.parent))
    try:
        spec=importlib.util.spec_from_file_location('preserved_city_hierarchy',source)
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    finally:sys.path.remove(str(source.parent))
    from repairs.k_partition_20261020.algorithm.endpoint_partition import validate_partition
    import geopandas as gpd
    frame=gpd.read_file(path('network')).to_crs(4326)
    base={int(n):int(v) for n,v in cache['labels384'].items()}
    edges=[tuple(map(int,pair)) for pair in cache['edge_nodes'].values()]
    scale=math.cos(math.radians((c['bbox'][0]+c['bbox'][1])/2))
    xy={}
    for row in frame[['id','geometry']].itertuples(index=False):
        pair=cache['edge_nodes'].get(int(row.id))
        if pair is None:raise ValueError('Public edge missing in metric cache')
        for node,point in zip(pair,(row.geometry.coords[0],row.geometry.coords[-1])):
            xy.setdefault(int(node),np.array([point[0]*scale,point[1]]))
    if set(xy)!=set(base):raise ValueError('Metric node domain differs from public geometry')
    maps=builder.merge_hierarchy(base,cache['labels24'],edges,xy,{24,48,96,192,384})
    if 768 in ks:
        adjacency={n:set() for n in base}
        for u,v in edges:
            if base[u]==base[v]:adjacency[u].add(v);adjacency[v].add(u)
        fine={}
        for cell in range(384):
            ns={n for n,label in base.items() if label==cell}
            fine.update({n:2*cell+s for n,s in builder.split_connected(ns,adjacency,xy).items()})
        maps[768]=fine
    for k in ks:validate_partition(cache,{str(n):v for n,v in maps[k].items()},k,8)
    assert maps[384]==base
    graph_sha,cache_sha=sha(path('network')),sha(path('metric_cache'))
    out.mkdir(parents=True)
    for k in ks:
        payload=dict(schema='dfr-public-endpoint-partition-v1',source='public-road-graph-only',k=k,
          labels={str(n):v for n,v in maps[k].items()},network_sha256=graph_sha,metric_cache_sha256=cache_sha,
          builder_sha256=sha(source),reference_latitude=(c['bbox'][0]+c['bbox'][1])/2,
          construction='Preserved merge_hierarchy and split_connected; fixed public384 anchor and coarse24; no trajectory input')
        (out/f'partition{k}.json').write_text(json.dumps(payload,sort_keys=True),encoding='utf-8')
    report=dict(status='PUBLIC_HIERARCHY_VALIDATED',ks=ks,network_sha256=graph_sha,metric_cache_sha256=cache_sha,
       builder_sha256=sha(source),seconds=time.perf_counter()-started,
       outputs={p.name:sha(p) for p in out.glob('partition*.json')})
    (out/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ks',nargs='+',type=int,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.config,a.out,a.ks),indent=2))
if __name__=='__main__':main()

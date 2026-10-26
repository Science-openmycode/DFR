"""Public edge/metric I/O adapter around the existing region support builder.

Does not generate trajectories, evaluate synthetic data, or modify algorithms.
"""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time

from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent

def legacy_dataset_key(dataset):
    return {'beijing':'geolife','san_francisco':'sf_taxi'}.get(dataset,dataset)

def sha(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def write_cache(path,value):
    with gzip.open(path,'wb',compresslevel=3) as handle:pickle.dump(value,handle,pickle.HIGHEST_PROTOCOL)

def physical_node_labels(regions,physical):
    votes=defaultdict(Counter)
    for edge,(source,target) in physical.items():
        first,second=regions[edge];votes[source][first]+=1;votes[target][second]+=1
    return {node:min(counts,key=lambda label:(-counts[label],label)) for node,counts in votes.items()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out-config',type=Path,required=True,help='New configuration with bound edge/metric resources')
    p.add_argument('--out-dir',type=Path,help='New public resource directory, default frozen dataset/public_resources')
    a=p.parse_args()
    if a.out_config.exists():p.error('Output config already exists')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    path=lambda key:(ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'))
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Dataset binding changed')
    out=(a.out_dir or path('prepared')/'public_resources').resolve()
    if out.exists() and any(out.iterdir()):p.error('Public resource output exists; inspect prior run before retry')
    begin=time.monotonic()
    legacy=path('legacy')/'evaluation'
    sys.path.insert(0,str(legacy));sys.path.insert(0,str(legacy/'evaluation'))
    from generation.common.runtime import dataset_config
    from evaluate_road_choice import _edge_endpoint_regions
    config=dataset_config(legacy_dataset_key(c['dataset']));config.update(bbox=c['bbox'],osm_cache=str(path('osm')))
    out.mkdir(exist_ok=True)
    import geopandas as gpd
    frame=gpd.read_file(path('network'))
    physical={int(row.id):(int(row.source),int(row.target)) for row in frame.itertuples()}
    if len(physical)!=len(frame):raise ValueError('Duplicate public physical edge IDs')
    # Region function is reused unchanged from the historical published pipeline.
    payload={};diagnostics={};canonical=None
    for resolution in (24,96,384):
        print(f'PUBLIC REGIONS {resolution}: START',flush=True)
        regions,edge_nodes,_,diagnostic=_edge_endpoint_regions(path('network'),config,resolution)
        if canonical is not None and edge_nodes!=canonical:raise ValueError('Canonical graph changed across resolutions')
        canonical=edge_nodes
        if set(regions)!=set(physical):raise ValueError('Region/physical edge coverage mismatch')
        payload[f'labels{resolution}']=physical_node_labels(regions,physical)
        diagnostics[str(resolution)]=diagnostic
        print(f'PUBLIC REGIONS {resolution}: DONE',flush=True)
    successors=defaultdict(set)
    for source,target in physical.values():successors[source].add(target)
    payload.update(classification='PUBLIC_GRAPH_DERIVED_SUPPORT_NO_TRAJECTORY_ROWS',
        edge_nodes=physical,outdegree={node:len(values) for node,values in successors.items()},portals={})
    metric=out/'metric_cache.pkl.gz';write_cache(metric,payload)
    if set(physical)!=set(canonical):raise ValueError('Physical/canonical edge identity coverage mismatch')
    edge=out/'edge_cache.pkl.gz';write_cache(edge,dict(edge_nodes=physical,classification='PUBLIC_PHYSICAL_GRAPH_NO_TRAJECTORIES'))
    manifest=dict(status='EDGE_METRIC_COMPLETE',network_sha256=sha(path('network')),osm_sha256=sha(path('osm')),
        region_implementation=str(legacy/'evaluation/evaluate_road_choice.py'),
        region_implementation_sha256=sha(legacy/'evaluation/evaluate_road_choice.py'),diagnostics=diagnostics,
        edges=len(physical),outputs={f.name:sha(f) for f in [metric,edge]},elapsed_seconds=time.monotonic()-begin,
        command=[sys.executable,*sys.argv],ubodt_status='NOT_BUILT',note='Use physical endpoints for all road metrics. Historical region assignments are joined by common edge ID only; no snapping/re-routing of trajectories.')
    (out/'resources_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    c['public_resources_status']='EDGE_METRIC_READY';c['road_reference_status']='FROZEN_EDGE_METRIC_READY'
    c['fmm_resources_status']='UBODT_PENDING'
    c['paths'].update(edge_cache=str(edge),metric_cache=str(metric),source_cache=str(metric))
    a.out_config.parent.mkdir(parents=True,exist_ok=True)
    a.out_config.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

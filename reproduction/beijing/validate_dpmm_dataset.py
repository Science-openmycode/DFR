"""Revalidate the preserved DPMM path accelerator on this actual input/graph."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import pickle
import random
import sys
import time
from types import SimpleNamespace

import numpy as np
from preprocess.dataset_contract import validate_dataset, sha
from preprocess.dpmm_population import population_input, validation_indices

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--optimizer',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--records',type=int,default=50)
    p.add_argument('--split',choices=('full','train'),default='full')
    p.add_argument('--public-network',type=Path)
    p.add_argument('--exact-records',type=int,help='Explicit validation-only sample count, at least 60')
    a=p.parse_args()
    if a.out.exists() or a.records<50:
        p.error('Require a new output and at least 50 actual comparisons')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    prepared=(ROOT/c['paths']['prepared']).resolve()
    identity=validate_dataset(prepared,public_network=a.public_network)
    if identity['dataset_id']!=c['frozen_dataset_id']:
        raise ValueError('Wrong frozen input')
    source,expected_count,expected_sha=population_input(prepared,identity,a.split)
    if sha(source)!=expected_sha:raise ValueError('Frozen selected population changed')
    osm=(ROOT/c['paths']['osm']).resolve()
    def load(name,file):
        spec=importlib.util.spec_from_file_location(name,file.resolve())
        m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
    adapter=load('new_dataset_frozen_dpmm',a.adapter)
    optimizer=load('new_dataset_fast_dpmm',a.optimizer)
    cfg=dict(bbox=tuple(c['bbox']),osm_cache=str(osm),zone_radius_m=25,
             utm_zone_number=50,utm_zone_letter='S',epsilon=c['epsilon'])
    print('BUILD_PUBLIC_DPMM_GRAPH',flush=True)
    base,official,_=adapter._build_matcher(cfg)
    graph=base.graph
    if any(not np.isfinite(d['length']) or d['length']<0 for _,_,d in graph.edges(data=True)):
        raise ValueError('Accelerator requires finite nonnegative graph weights')
    public=[]; nodes=list(graph); random_source=random.Random(731)
    for u in (nodes[0],nodes[len(nodes)//3],nodes[2*len(nodes)//3]):
        targets=list(graph.successors(u))+random_source.sample(nodes,min(8,len(nodes)))+[u,-1]
        old,new=SimpleNamespace(graph=graph),SimpleNamespace(graph=graph)
        adapter.install_semantic_path_cache(old);optimizer.install_semantic_path_cache(new)
        left=old.gen_path_list([u],targets);right=new.gen_path_list([u],targets)
        if left!=right or new.gen_path_list([u],targets)!=left:
            raise AssertionError('Public candidate paths differ')
        public.append(dict(source=int(u),paths_equal=True))
    with source.open('rb') as f: data=pickle.load(f)
    if len(data)!=expected_count:raise ValueError('Selected population count differs')
    indices=validation_indices(data,a.records,a.exact_records)
    if len(indices)<50:
        raise ValueError('Insufficient dataset for this full validation')
    slow,fast=copy.copy(base),copy.copy(base)
    adapter.install_semantic_path_cache(slow);optimizer.install_semantic_path_cache(fast)
    a.out.mkdir(parents=True)
    report=dict(passed=False,complete=False,tested_records=0,target_records=len(indices),
                input_count=len(data),adapter_sha256=sha(a.adapter),
                optimization_sha256=sha(a.optimizer),real_input_sha256=sha(source),
                public_osm_sha256=sha(osm),public_path_comparisons=public,
                graph_nodes=len(graph),graph_edges=graph.number_of_edges(),
                seed=20260714,public_parameters=cfg,rows=[],population=a.split,
                frozen_dataset_id=identity['dataset_id'],input_sha256=expected_sha)
    started=time.perf_counter()
    for index in indices:
        values=[]; times=[]
        for mm in (slow,fast):
            np.random.seed(20260714+index+1);random.seed(20260714+index+1)
            start=time.perf_counter()
            values.append(adapter.official_process_one(mm,official,data[index],'rdp',None))
            times.append(time.perf_counter()-start)
        old,new=values
        equal=(old is None and new is None) or (old is not None and new is not None and np.array_equal(old,new))
        row=dict(index=index,raw_points=len(data[index]),exact_output_equal=bool(equal),
                 reference_seconds=times[0],accelerated_seconds=times[1])
        report['rows'].append(row);report['tested_records']=len(report['rows'])
        report['passed']=all(r['exact_output_equal'] for r in report['rows'])
        report['complete']=len(report['rows'])==len(indices)
        report['seconds']=time.perf_counter()-started
        (a.out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
        if not equal:
            raise AssertionError('DPMM accelerated output differs; do not start generation')
    print('NEW_DATASET_VALIDATION_PASSED',flush=True)


if __name__=='__main__':
    main()

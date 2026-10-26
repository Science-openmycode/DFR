"""Feed the frozen road population to the preserved MTNet author-format adapter."""
import argparse
import csv
import gzip
import importlib.util
import json
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import time

import numpy as np

from preprocess.dataset_contract import validate_dataset, sha

ROOT=Path(__file__).resolve().parent


def load_original_adapter(name,filename):
    """Keep author source unchanged; bridge Windows Python <3.13 CSV C-long limits."""
    native_limit=csv.field_size_limit
    def compatible_limit(value=None):
        if value is None:return native_limit()
        try:return native_limit(value)
        except OverflowError:return native_limit(min(value,(1<<31)-1))
    csv.field_size_limit=compatible_limit
    try:
        spec=importlib.util.spec_from_file_location(name,filename)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    finally:
        csv.field_size_limit=native_limit


def select_population(source_indices, binding_records, roads, selected_indices):
    """Preserve frozen split order, and align timestamps/roads before author filters."""
    n=len(source_indices)
    if len(roads)!=n or len(set(source_indices))!=n:
        raise ValueError('Invalid frozen source/road alignment')
    if (not selected_indices or any(type(i) is not int or i<0 or i>=n for i in selected_indices)
            or len(set(selected_indices))!=len(selected_indices)):
        raise ValueError('Invalid selected frozen indices')
    records=[];selected_roads=[]
    for slot,index in enumerate(selected_indices,1):
        source=source_indices[index]
        if type(source) is not int or source<0 or source>=len(binding_records):
            raise ValueError('Invalid original timestamp source index')
        original=binding_records[source]
        if original['id']!=source+1 or not roads[index]['accepted']:
            raise ValueError('Timestamp order or accepted frozen road mismatch')
        records.append(dict(original,id=slot,original_source_index=source,
                            frozen_population_index=index))
        selected_roads.append(roads[index])
    return records,selected_roads


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--original-adapter-root',type=Path,required=True)
    p.add_argument('--time-binding',type=Path,required=True)
    p.add_argument('--raw-reference',type=Path,required=True,
                   help='Hash-only binding of the original timestamps; never an alternative training population')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-route-edges',type=int,default=20,help='Original MTNet public maximum, preserved by default')
    p.add_argument('--train-only',action='store_true',help='Use only the existing frozen training indices; never choose a new split')
    p.add_argument('--public-network',type=Path,help='Migrated public graph path; original graph and sidecar hashes remain mandatory')
    a=p.parse_args();started=time.perf_counter()
    if a.out.exists():raise FileExistsError(a.out)
    c=json.loads(a.config.read_text(encoding='utf-8'))
    def path(key):return (ROOT/c['paths'][key]).resolve()
    if a.public_network is not None and a.public_network.resolve()!=path('network'):
        raise ValueError('Migrated graph path must match the configuration')
    prepared=path('prepared');identity=validate_dataset(prepared,public_network=a.public_network)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong prepared dataset')
    binding=json.loads(a.time_binding.read_text(encoding='utf-8'))
    if binding['status']!='complete' or not binding['all_coordinates_exact'] or sha(a.raw_reference)!=binding['reference_sha256']:
        raise ValueError('Original timestamp binding is not verified')
    canonical=json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    if (canonical['original_source_sha256']!=binding['reference_sha256']
            or canonical['network_sha256']!=sha(path('network'))):
        raise ValueError('Timestamp source or public graph differs from frozen preprocessing')
    indices=json.loads((prepared/'source_indices.json').read_text(encoding='utf-8'))
    if len(indices)!=identity['count'] or len(set(indices))!=len(indices):raise ValueError('Invalid original source index mapping')
    selected_indices=list(range(identity['count']))
    split_binding={}
    if a.train_only:
        audit=json.loads(path('split_audit').read_text(encoding='utf-8'))
        if (audit.get('status')!='passed' or not audit.get('all_source_indices_used_once')
                or audit['full_sha256']!=sha(path('real'))
                or audit['train_sha256']!=sha(path('train'))
                or audit['test_sha256']!=sha(path('test'))):
            raise ValueError('No current verified disjoint split')
        selected_indices=json.loads((prepared/'train_split.json').read_text(encoding='utf-8'))['indices']
        if (len(selected_indices)!=c['train_slots'] or audit['train_count']!=len(selected_indices)
                or audit['test_count']!=identity['test_count']):
            raise ValueError('Wrong frozen training population')
        split_binding=dict(split_audit_sha256=sha(path('split_audit')),
                           train_sha256=audit['train_sha256'],test_sha256=audit['test_sha256'],
                           train_indices_sha256=sha(prepared/'train_split.json'))
    with gzip.open(path('real_routes'),'rb') as f:all_roads=pickle.load(f)
    records,roads=select_population(indices,binding['records'],all_roads,selected_indices)
    del all_roads
    root=a.original_adapter_root.resolve()
    original=load_original_adapter('mtnet_original_file_adapter',root/'prepare_beijing_nodp_fmm.py')
    original_pipeline=load_original_adapter('mtnet_original_pipeline_adapter',root/'prepare_mtnet_full_cloud.py')
    out=a.out.resolve();out.mkdir(parents=True)
    stage=out/'prepared';stage.mkdir()
    network=path('network')
    for suffix in ('.shp','.shx','.dbf','.prj','.cpg'):
        shutil.copy2(network.with_suffix(suffix),stage/('fmm_network'+suffix))
    # No matching: use the already frozen input road IDs as the author-format
    # preprocessing output. The original length/time filters are unchanged.
    matched=stage/'frozen_input_roads.csv'
    with matched.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(['id','cpath'])
        for slot,row in enumerate(roads,1):writer.writerow([slot,','.join(map(str,row['cpath']))])
    del roads
    import geopandas as gpd
    frame=gpd.read_file(network)
    lengths={int(row.id):float(row.length_m) for row in frame.itertuples()}
    del frame
    stats=original.parse_matches(matched,records,lengths,stage,a.max_route_edges)
    manifest=dict(dataset_id=identity['dataset_id'],input_count=len(records),
                  input_sha256=sha(path('train') if a.train_only else path('real')),
                  full_population_count=identity['count'],evaluation_scope='strict_tstr' if a.train_only else 'full_corpus',
                  selected_frozen_indices=selected_indices,split_binding=split_binding,
                  real_roads_sha256=sha(path('real_routes')),
                  selected_roads_csv_sha256=sha(matched),adapter_sha256=sha(Path(__file__)),
                  match=stats,paper_constraints=dict(max_route_edges=a.max_route_edges),
                  input_policy='Already frozen road dataset; no second matching or reference subset',
                  timestamp_policy='Original endpoint timestamps selected by frozen source_indices; coordinates were projected during approved preprocessing',
                  original_raw_reference_sha256=sha(a.raw_reference),time_binding_sha256=sha(a.time_binding),
                  original_format_adapter_sha256=sha(root/'prepare_beijing_nodp_fmm.py'),
                  end_to_end_raw_trajectory_DP_certified=False,
                  scope='Prepared-aligned baseline; unchanged original record filters counted explicitly')
    (stage/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    destination=out/'data/beijing_roads_l20'
    subprocess.run([sys.executable,str(root/'build_native_mtnet_inputs.py'),'--prepared',str(stage),
                    '--out',str(destination),'--demo-temporal',str(root/'official/data/demo/temporal_32.emb')],check=True)
    from collections import Counter
    counts=Counter()
    with (destination/'trajs_demo.csv').open() as routes,(destination/'tstamps_demo.csv').open() as times:
        for line,ts in zip(routes,times,strict=True):
            reason=original_pipeline.loader_reason([int(v) for v in line.split()],[float(v) for v in ts.split()],a.max_route_edges)
            counts[reason or 'trainable']+=1
    manifest.update(original_loader_counts=dict(counts),training_split_fraction=1.,
                    seconds=time.perf_counter()-started,
                    data_files_sha256={f.name:sha(f) for f in destination.iterdir() if f.is_file()})
    (out/'full_preparation_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    np.save(out/'public_origin_ids.npy',np.asarray(sorted(lengths),dtype=np.int64))
    print('PREPARED_MTNET',len(records),'input roads;',counts['trainable'],'original-loader training records',flush=True)


if __name__=='__main__':main()

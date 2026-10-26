"""Cloud-only fixed-corpus FMM preparation, retaining historical MTNet filters."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time
import numpy as np


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def validate_binding(meta,digest,coordinates):
    if meta.get('reference_sha256')!=digest:raise ValueError('reference hash mismatch')
    rows=meta.get('records',[])
    if meta.get('input_records')!=len(coordinates) or len(rows)!=len(coordinates):raise ValueError('input count mismatch')
    for index,(record,points) in enumerate(zip(rows,coordinates)):
        if record['id']!=index+1:raise ValueError('slot order mismatch')
        if record['point_count']!=len(points):raise ValueError('point count mismatch')
        if hashlib.sha256(np.asarray(points,dtype=float).tobytes()).hexdigest()!=record['coordinate_sha256']:
            raise ValueError('coordinate bytes mismatch')


def loader_reason(route,times,max_edges):
    # Author TRIM_STOP=True: remove the supplied terminal token before checking.
    if len(route)-1>max_edges+1:return 'over_L'
    if any(t>=6000 for t in times[1:]):return 'tcost_ge_6000'
    if any(math.isnan(t) for t in times):return 'nan_time'
    return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path)
    p.add_argument('--binding',required=True,type=Path)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--max-route-edges',default=20,type=int)
    p.add_argument('--workers',default=2,type=int)
    a=p.parse_args();root=a.root.resolve();out=root/'prepared';start=time.time()
    lock=root/'preparation.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    def status(stage,**extra):
        obj=dict(stage=stage,elapsed_seconds=time.time()-start,**extra)
        (root/'preparation_status.json').write_text(json.dumps(obj,indent=2))
        print(json.dumps(obj),flush=True)
    status('validating_all_coordinate_time_bindings')
    meta=json.loads(a.binding.read_text())
    with a.input.open('rb') as f:coordinates=pickle.load(f)
    validate_binding(meta,sha(a.input),coordinates)
    import geopandas as gpd
    from pyproj import Transformer
    network=out/'fmm_network.shp';gdf=gpd.read_file(network)
    lengths={int(row.id):float(row.length_m) for row in gdf.itertuples()}
    gps=out/'fixed_full_gps.csv'
    if gps.exists():raise FileExistsError(gps)
    transformer=Transformer.from_crs('EPSG:4326','EPSG:32650',always_xy=True)
    status('writing_full_gps',input_records=len(coordinates),input_sha256=sha(a.input))
    with gps.open('x',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(['id','x','y'])
        for rid,points in enumerate(coordinates,1):
            x,y=transformer.transform(points[:,1],points[:,0])
            writer.writerows((rid,f'{a:.3f}',f'{b:.3f}') for a,b in zip(x,y))
    del coordinates
    env=dict(os.environ,OMP_NUM_THREADS=str(a.workers),OPENBLAS_NUM_THREADS='1')
    binary=root/'fmm_source/build';ubodt=out/'ubodt.txt';matched=out/'fmm_matches.csv'
    commands=[
        [str(binary/'ubodt_gen'),'--network',str(network),'--network_id','id','--source','source','--target','target',
         '--delta','3000','--output',str(ubodt),'--use_omp'],
        [str(binary/'fmm'),'--ubodt',str(ubodt),'--network',str(network),'--network_id','id','--source','source',
         '--target','target','--gps',str(gps),'--gps_point','--gps_id','id','--gps_x','x','--gps_y','y',
         '--candidates','8','--radius','300','--error','50','--output',str(matched),'--output_fields','cpath','--use_omp']]
    for stage,command in zip(['building_public_ubodt','fmm_all_17123_inputs'],commands):
        status(stage,command=command)
        subprocess.run(command,cwd=root,env=env,check=True)
    spec=importlib.util.spec_from_file_location('historical_prep',root/'prepare_beijing_nodp_fmm.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    stats=module.parse_matches(matched,meta['records'],lengths,out,a.max_route_edges)
    manifest=dict(method='MTNet; original retained-only FMM input protocol applied to frozen full coordinate corpus',
                  raw_input_records=meta['input_records'],input_sha256=meta['reference_sha256'],binding_sha256=sha(a.binding),
                  input_scope='all frozen 17123 inputs processed; filtered count separately recorded',
                  paper_constraints=dict(FMM=True,directed_public_OSM=True,max_route_edges=a.max_route_edges,
                                         time_interpolation='linear by matched edge length from true endpoint times',split='all retained rows for training'),
                  match=stats,network_edges=len(lengths),commands=commands,
                  fmm=dict(candidates=8,radius_m=300,gps_error_m=50,ubodt_delta_m=3000,workers=a.workers),
                  time_binding='all retained input points match frozen coordinates exactly; no resegmentation',
                  privacy_scope='internal experiment; original retained-only preprocessing is not certified raw-trajectory DP',
                  files_sha256={f.name:sha(f) for f in out.glob('fmm_network.*')})
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2))
    native=root/'data/beijing_full_l20'
    subprocess.run([sys.executable,str(root/'build_native_mtnet_inputs.py'),'--prepared',str(out),'--out',str(native),
                    '--demo-temporal',str(root/'official/data/demo/temporal_32.emb')],check=True)
    counts=Counter();total=0
    with (native/'trajs_demo.csv').open() as routes,(native/'tstamps_demo.csv').open() as times:
        for line,ts in zip(routes,times,strict=True):
            total+=1;reason=loader_reason([int(v) for v in line.split()],[float(v) for v in ts.split()],a.max_route_edges)
            counts[reason or 'trainable']+=1
    manifest['original_loader_counts']=dict(counts);manifest['prepared_records']=total
    manifest['training_split_fraction']=1.;manifest['elapsed_seconds']=time.time()-start
    manifest['data_files_sha256']={f.name:sha(f) for f in native.iterdir() if f.is_file()}
    (root/'full_preparation_manifest.json').write_text(json.dumps(manifest,indent=2))
    np.save(root/'public_origin_ids.npy',np.asarray(sorted(lengths),dtype=np.int64))
    status('complete',input_records=meta['input_records'],prepared_records=total,trainable_records=counts['trainable'])


if __name__=='__main__':main()

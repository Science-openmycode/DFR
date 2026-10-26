"""Full-observation preprocessing experiment, not a certified road truth release."""
import argparse
import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import importlib.util
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[2]

def configure_csv_reader():
    # Complete long trajectories produce cpath/pgeom fields larger than 128 KiB.
    csv.field_size_limit(128*1024*1024)

def store_match_record(parsed, source_index, record):
    # Upstream empty MatchResult rows can carry default ID 0 rather than GPS ID.
    # They cannot identify a source; use the missing-ID fallback for failures.
    if not record.cpath:
        return
    if source_index in parsed:
        raise ValueError(f'Duplicate nonempty matcher result ID {source_index}')
    parsed[source_index]=record

def full_point_cap(rows):
    if not rows or any(len(row)<2 for row in rows):
        raise ValueError('Each source trajectory must have at least two observations')
    return max(len(row) for row in rows)

def rejection_reason(record, points_count, radius=200., coverage=.95):
    if not record.cpath:return 'NO_PATH'
    if not record.connected:return 'DISCONNECTED'
    if len(record.residual_m)!=points_count:return 'RESIDUAL_EVIDENCE_MISSING'
    if not np.isfinite(record.residual_m).all():return 'NONFINITE_RESIDUAL'
    if record.observation_share<coverage:return 'LOW_OBSERVATION_COVERAGE'
    if np.quantile(record.residual_m,.95)>radius:return 'GPS_ROAD_RESIDUAL_TOO_LARGE'
    if not record.accepted:return 'MATCHER_REJECTED'
    return 'ACCEPTED'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def dump(path,value):
    with gzip.open(path,'wb',compresslevel=3) as f:pickle.dump(value,f,pickle.HIGHEST_PROTOCOL)

def main():
    configure_csv_reader()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'results/fresh_repro_20260925/data/real_full_frozen.pkl')
    p.add_argument('--old-reference',type=Path,default=ROOT/'check/four_panel_completion_20261008/cloud_results/dpmm_full_archive/bundle_v3/real_routes.pkl.gz')
    p.add_argument('--network',type=Path,default=ROOT/'tmp_dfr_remote_verify_20261002_new/public_assets/beijing_network/network.shp')
    p.add_argument('--executable',type=Path,default=ROOT/'tmp_dfr_remote_verify_20261002_new/public_assets/matcher/stmatch.exe')
    p.add_argument('--ubodt',type=Path,help='Public shortest-path table when executable is FMM; omitted for STMatch')
    p.add_argument('--runtime',type=Path,default=ROOT/'results/fresh_repro_20260925/matcher_runtime_conda/Library/bin')
    p.add_argument('--matcher-module',type=Path,default=Path(__file__).with_name('road_route_io_fixed.py'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mode',choices=['probe','full'],required=True)
    p.add_argument('--indices',type=int,nargs='+',help='Explicit original indices for a diagnostic probe only')
    p.add_argument('--batch-size',type=int,default=128)
    p.add_argument('--threads',type=int,default=8)
    p.add_argument('--workers',type=int,default=1,help='Independent matching processes; total CPU teams = workers * threads')
    p.add_argument('--radius',type=float,default=200.)
    p.add_argument('--gps-error',type=float,default=50.)
    a=p.parse_args()
    if a.batch_size<1 or a.threads<1 or a.workers<1:p.error('batch size, workers and threads must be positive')
    if a.out.exists():p.error('New output directory required; existing results are not overwritten')
    a.out.mkdir(parents=True)
    os.environ['OMP_NUM_THREADS']=str(a.threads)
    os.environ['PYTHONUTF8']='1'
    started=time.time()
    with a.source.open('rb') as f: raw=pickle.load(f)
    with gzip.open(a.old_reference,'rb') as f: old=pickle.load(f)
    assert len(raw)==len(old)
    for index,row in enumerate(raw):
        array=np.asarray(row)
        if array.ndim!=2 or array.shape[1]!=2 or not np.isfinite(array).all():
            raise ValueError(f'Invalid source record {index}; do not silently filter')
    if a.mode=='probe':
        audit=json.loads(Path(__file__).with_name('input_audit.json').read_text(encoding='utf-8'))
        ids=a.indices or audit['probe_source_indices']
        if len(set(ids))!=len(ids) or any(i<0 or i>=len(raw) for i in ids):
            raise ValueError('Probe indices must be unique existing source indices')
    else:
        if a.indices:p.error('Full mode must include all source records')
        ids=list(range(len(raw)))
    spec=importlib.util.spec_from_file_location('full_point_legacy_matcher',a.matcher_module)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    files=[a.source,a.old_reference,a.network,a.executable,a.matcher_module]
    if a.ubodt:files.append(a.ubodt)
    bindings={str(path.resolve()):digest(path) for path in files}
    config=dict(mode=a.mode,source_records=len(raw),selected_records=len(ids),selected_indices=ids,
                input_bindings=bindings,radius_m=a.radius,gps_error_m=a.gps_error,threads=a.threads,workers=a.workers,
                downsampling=False,route_only=False,min_observation_share=.95,
                classification='PRIVATE_PREPROCESSING_DIAGNOSTIC_NOT_DP_RELEASE_NOT_CERTIFIED_TRUTH')
    (a.out/'input_manifest.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    final=[];reasons=Counter();transitions=Counter();by_start={}
    def run_chunk(start):
        chunk_ids=ids[start:start+a.batch_size]
        trajectories=[raw[index] for index in chunk_ids]
        cap=full_point_cap(trajectories)
        print(f'START {start}:{start+len(chunk_ids)}/{len(ids)} points={sum(len(r) for r in trajectories)} cap={cap} threads={a.threads}',flush=True)
        matched,invocation=module.run_fmm(trajectories,a.network,a.ubodt,a.executable,None,a.runtime,
            cap,a.radius,a.gps_error,8,.95,route_only=False)
        records=[]
        for index,trajectory,record in zip(chunk_ids,trajectories,matched):
            reason=rejection_reason(record,len(trajectory),a.radius)
            accepted=reason=='ACCEPTED'
            value=dict(source_index=index,source_points=len(trajectory),matcher_input_points=len(trajectory),
                       old_accepted=bool(old[index]['accepted']),cpath=record.cpath,opath=record.opath,
                       residual_m=record.residual_m,connected=record.connected,
                       observation_share=record.observation_share,accepted=accepted,reason=reason)
            records.append(value)
        chunk=a.out/f'chunk_{start:05d}.pkl.gz';dump(chunk,records)
        (a.out/f'chunk_{start:05d}.json').write_text(json.dumps(dict(start=start,stop=start+len(chunk_ids),
            output_sha256=digest(chunk),invocation=invocation),ensure_ascii=False,indent=2),encoding='utf-8')
        return start,records
    starts=list(range(0,len(ids),a.batch_size))
    with ThreadPoolExecutor(max_workers=a.workers) as executor:
        pending={executor.submit(run_chunk,start):start for start in starts}
        for future in as_completed(pending):
            start,records=future.result()
            by_start[start]=records
            for row in records:
                reasons[row['reason']]+=1
                transitions[f"old_{row['old_accepted']}_new_{row['accepted']}"]+=1
            progress=dict(completed=sum(len(r) for r in by_start.values()),total=len(ids),
                          reasons=dict(reasons),transitions=dict(transitions),elapsed_seconds=time.time()-started)
            (a.out/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(progress,ensure_ascii=False),flush=True)
    final=[record for start in starts for record in by_start[start]]
    for name,sha in bindings.items():assert digest(name)==sha,'Input changed during matching'
    target=a.out/'matched_full_observations.pkl.gz';dump(target,final)
    config.update(progress,output_sha256=digest(target),status='MATCHING_COMPLETE_QUALITY_REVIEW_PENDING')
    (a.out/'manifest.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print('MATCHING COMPLETE; quality review required before selecting reference or rerunning synthesis.',flush=True)

if __name__=='__main__':main()

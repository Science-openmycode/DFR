"""Build/review a common road corpus with per-record candidate fallback 8 -> 16.

Raw inputs and audit records are private research material, not DP releases.
"""
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import sys

import numpy as np
from scipy.stats import ks_2samp

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def load(path):
    with (gzip.open(path,'rb') if str(path).endswith('.gz') else open(path,'rb')) as f:return pickle.load(f)

def save(path,value):
    with (gzip.open(path,'wb',compresslevel=3) if str(path).endswith('.gz') else open(path,'wb')) as f:
        pickle.dump(value,f,pickle.HIGHEST_PROTOCOL)

def distance(coords):
    radians=np.radians(coords);delta=np.diff(radians,axis=0)
    h=np.sin(delta[:,0]/2)**2+np.cos(radians[:-1,0])*np.cos(radians[1:,0])*np.sin(delta[:,1]/2)**2
    return 12742017.6*np.arcsin(np.sqrt(np.clip(h,0,1)))

def choose_records(initial,retry):
    n=len(initial)
    if [r['source_index'] for r in initial]!=list(range(n)):raise ValueError('Initial IDs incomplete or duplicated')
    result=[dict(r,first_success_candidates=8 if r['accepted'] else None) for r in initial]
    ids=[r['source_index'] for r in retry]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate retry source IDs')
    for r in retry:
        i=r['source_index']
        if i<0 or i>=n or initial[i]['accepted']:raise ValueError('Retry must contain only failed-at-8 records')
        if r['reason']=='ACCEPTED':result[i]=dict(initial[i],**{k:r[k] for k in ['cpath','opath','residual_m','reason','accepted']},
            connected=True,observation_share=len(r['opath'])/initial[i]['source_points'],first_success_candidates=16)
    return result

def numerical_comparison(values,keep):
    values=np.asarray(values,dtype=float);keep=np.asarray(keep,dtype=bool)
    a=values[keep & np.isfinite(values)];b=values[~keep & np.isfinite(values)]
    if not len(a) or not len(b):return {'available':False}
    pooled=np.sqrt((a.var()+b.var())/2)
    full=values[np.isfinite(values)]
    return dict(available=True,retained_median=float(np.median(a)),excluded_median=float(np.median(b)),
        retained_p90=float(np.quantile(a,.9)),excluded_p90=float(np.quantile(b,.9)),
        retained_count=len(a),excluded_count=len(b),ks=float(ks_2samp(a,b).statistic),
        standardized_mean_difference=float((a.mean()-b.mean())/pooled) if pooled else 0.,
        retained_vs_full_ks=float(ks_2samp(a,full).statistic))

def categorical_comparison(values,keep):
    labels=np.asarray(values);a=labels[np.asarray(keep)];b=labels[~np.asarray(keep)]
    keys=np.unique(labels)
    if not len(a) or not len(b):return {'available':False}
    pa=np.array([(a==k).mean() for k in keys]);pb=np.array([(b==k).mean() for k in keys])
    full=np.array([(labels==k).mean() for k in keys])
    return dict(available=True,total_variation=float(np.abs(pa-pb).sum()/2),
        retained_vs_full_tv=float(np.abs(pa-full).sum()/2),
        categories=[dict(label=str(k),retained_share=float(x),excluded_share=float(y)) for k,x,y in zip(keys,pa,pb)])

def validate_records(records,network):
    edges={int(r.id):(int(r.source),int(r.target)) for r in network.itertuples()}
    for row in records:
        if not row['accepted']:continue
        path=row['cpath'];count=row['source_points']
        if not path or any(e not in edges for e in path):raise ValueError('Missing road ID')
        if any(edges[u][1]!=edges[v][0] for u,v in zip(path[:-1],path[1:])):raise ValueError('Disconnected road witness')
        if len(row['opath'])!=count or len(row['residual_m'])!=count:raise ValueError('Incomplete observation evidence')
        if not np.isfinite(row['residual_m']).all() or np.quantile(row['residual_m'],.95)>200:
            raise ValueError('Residual check failed')
        if any(e not in edges for e in row['opath']):raise ValueError('Invalid observation road ID')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True,help='Full original coordinate pickle, lat/lon per point')
    p.add_argument('--network',type=Path,required=True,help='Public directed segment shapefile')
    p.add_argument('--matcher-module',type=Path,required=True,help='Existing road_route_io_fixed.py, algorithm unchanged')
    p.add_argument('--executable',type=Path,help='STMatch executable; needed without reusable evidence')
    p.add_argument('--runtime',type=Path,help='Matcher DLL directory')
    p.add_argument('--base-matches',type=Path,help='Verified merged records at k=8')
    p.add_argument('--base-manifest',type=Path,help='Verified merged summary.json binding base data and inputs')
    p.add_argument('--retry-dir',type=Path,help='Completed k=16 directory; never k=32 or higher')
    p.add_argument('--timestamps',type=Path,required=True,help='Exactly aligned per-point original day-serial timestamps')
    p.add_argument('--timestamp-bindings',type=Path,required=True,help='CSV mapping original source IDs to coordinate SHA256')
    p.add_argument('--out',type=Path,required=True,help='New private audit/prepared output directory')
    p.add_argument('--dataset',default='beijing')
    p.add_argument('--bbox',nargs=4,type=float,required=True,metavar=('LAT_MIN','LAT_MAX','LON_MIN','LON_MAX'))
    p.add_argument('--threads',type=int,default=8)
    p.add_argument('--seed',type=int,default=20260713)
    p.add_argument('--review-only',action='store_true',help='Always stop after bias review, even if no flags')
    p.add_argument('--accept-reviewed-subset',help='yes accepts the restricted cohort; historical report digest remains optional')
    a=p.parse_args()
    if a.out.exists():p.error('Choose a new output; existing data are never overwritten')
    if a.threads<1:p.error('--threads must be positive')
    if not (a.bbox[0]<a.bbox[1] and a.bbox[2]<a.bbox[3]):p.error('Invalid public bbox')
    reuse=bool(a.base_matches or a.retry_dir or a.base_manifest)
    if reuse and not all([a.base_matches,a.base_manifest,a.retry_dir]):p.error('Reuse requires all three evidence arguments')
    if not reuse and not a.executable:p.error('Provide executable or reusable evidence')
    raw=load(a.source);timestamps=load(a.timestamps)
    if len(timestamps)!=len(raw):raise ValueError('Timestamp count mismatch')
    with a.timestamp_bindings.open(encoding='utf-8-sig',newline='') as f:bindings=list(csv.DictReader(f))
    if len(bindings)!=len(raw):raise ValueError('Raw metadata bindings incomplete')
    for i,(coords,days,binding) in enumerate(zip(raw,timestamps,bindings)):
        if int(binding['source_index'])!=i or len(coords)!=len(days):raise ValueError('Metadata alignment mismatch')
        value=np.ascontiguousarray(coords,dtype='<f8')
        if hashlib.sha256(len(value).to_bytes(8,'little')+value.tobytes()).hexdigest()!=binding['coordinate_sha256']:raise ValueError('Timestamp binding changed')
    os.environ['OMP_NUM_THREADS']=str(a.threads);os.environ['PYTHONUTF8']='1'
    sys.path.insert(0,str(a.matcher_module.resolve().parent))
    spec=importlib.util.spec_from_file_location('preprocessing_matcher',a.matcher_module)
    matcher=importlib.util.module_from_spec(spec);sys.modules[spec.name]=matcher;spec.loader.exec_module(matcher)
    import full_point_matching as checks
    checks.configure_csv_reader()
    a.out.mkdir(parents=True)
    run_record=dict(command=[sys.executable,*sys.argv],program_sha256=digest(Path(__file__)),
        inputs={str(f.resolve()):digest(f) for f in [a.source,a.network,a.matcher_module,a.timestamps,a.timestamp_bindings]},
        network_sidecars={str(f.resolve()):digest(f) for f in a.network.parent.glob(a.network.stem+'.*') if f.suffix.lower() in ['.shp','.shx','.dbf','.prj','.cpg']},
        policy=dict(candidates=[8,16],radius_m=200,gps_error_m=50,split_trajectories=False),
        status='RUNNING_PRIVATE_PREPROCESSING')
    (a.out/'preprocessing_run.json').write_text(json.dumps(run_record,ensure_ascii=False,indent=2),encoding='utf-8')
    if reuse:
        meta=json.loads(a.base_manifest.read_text(encoding='utf-8'))
        if digest(a.base_matches)!=meta['output_sha256']:raise ValueError('Base record hash mismatch')
        for name,h in meta['input_bindings'].items():
            if digest(name)!=h:raise ValueError('Evidence input changed: '+name)
        for path in [a.source,a.network,a.matcher_module]:
            if meta['input_bindings'].get(str(path.resolve()))!=digest(path):raise ValueError('Evidence belongs to another input')
        retry_meta=json.loads((a.retry_dir/'manifest.json').read_text(encoding='utf-8'))
        if retry_meta.get('candidates')!=16 or retry_meta.get('radius_m')!=200 or retry_meta.get('gps_error_m')!=50 or retry_meta.get('status')!='DIAGNOSTIC_COMPLETE_NOT_REFERENCE':
            raise ValueError('Require completed fixed-parameter k16 evidence')
        if retry_meta['input_bindings']!=meta['input_bindings']:raise ValueError('Retry provenance mismatch')
        retry=[]
        for chunk in sorted(a.retry_dir.glob('chunk_*.pkl.gz')):retry.extend(load(chunk))
        final_retry=load(a.retry_dir/'diagnostic_records.pkl.gz')
        if retry!=final_retry or sorted(r['source_index'] for r in retry)!=sorted(retry_meta['source_indices']):raise ValueError('Retry chunk or ID mismatch')
        records=choose_records(load(a.base_matches),retry)
        # Candidate gaps have no possible full match at unchanged radius. Confirm skipped failures against the public graph below.
    else:
        records=[];retry=[]
        for start in range(0,len(raw),32):
            batch=raw[start:start+32]
            found,inv=matcher.run_fmm(batch,a.network,None,a.executable,None,a.runtime,max(map(len,batch)),200,50,8,.95,route_only=False)
            for j,result in enumerate(found):
                i=start+j;reason=checks.rejection_reason(result,len(raw[i]))
                row=dict(source_index=i,source_points=len(raw[i]),matcher_input_points=len(raw[i]),
                         cpath=result.cpath,opath=result.opath,residual_m=result.residual_m,connected=result.connected,
                         observation_share=result.observation_share,accepted=reason=='ACCEPTED',reason=reason)
                records.append(row)
            save(a.out/f'k8_chunk_{start:05d}.pkl.gz',records[start:])
            (a.out/f'k8_chunk_{start:05d}.json').write_text(json.dumps(inv,indent=2),encoding='utf-8')
        for start in range(0,len(records),32):
            ids=[r['source_index'] for r in records[start:start+32] if not r['accepted']]
            if not ids:continue
            batch=[raw[i] for i in ids]
            found,inv=matcher.run_fmm(batch,a.network,None,a.executable,None,a.runtime,max(map(len,batch)),200,50,16,.95,route_only=False)
            chunk=[]
            for i,result in zip(ids,found):
                reason=checks.rejection_reason(result,len(raw[i]))
                chunk.append(dict(source_index=i,cpath=result.cpath,opath=result.opath,residual_m=result.residual_m,accepted=reason=='ACCEPTED',reason=reason))
            retry.extend(chunk);save(a.out/f'k16_chunk_{start:05d}.pkl.gz',chunk)
            (a.out/f'k16_chunk_{start:05d}.json').write_text(json.dumps(inv,indent=2),encoding='utf-8')
        records=choose_records(records,retry)
    if len(records)!=len(raw):raise ValueError('Matching count mismatch')
    import geopandas as gpd
    from pyproj import Transformer
    graph=gpd.read_file(a.network)
    validate_records(records,graph)
    keep=np.array([r['accepted'] for r in records],dtype=bool)
    numerical={k:[] for k in ['observation_count','gps_polyline_m','endpoint_distance_m','duration_s']}
    groups={k:[] for k in ['origin_grid_16','destination_grid_16','start_hour','start_month']}
    lo,hi,left,right=a.bbox
    def cell(point):
        y,x=point
        if not (lo<=y<=hi and left<=x<=right):return 'outside_bbox'
        return str(min(15,int((y-lo)/(hi-lo)*16))*16+min(15,int((x-left)/(right-left)*16)))
    import datetime
    for coords,days in zip(raw,timestamps):
        numerical['observation_count'].append(len(coords))
        numerical['gps_polyline_m'].append(float(distance(coords).sum()))
        numerical['endpoint_distance_m'].append(float(distance(np.asarray(coords)[[0,-1]]).sum()))
        numerical['duration_s'].append(float((days[-1]-days[0])*86400))
        dt=datetime.datetime(1899,12,30)+datetime.timedelta(days=float(days[0]))
        groups['origin_grid_16'].append(cell(coords[0]));groups['destination_grid_16'].append(cell(coords[-1]))
        groups['start_hour'].append(dt.hour);groups['start_month'].append(dt.month)
    comparisons={k:numerical_comparison(v,keep) for k,v in numerical.items()}
    categories={k:categorical_comparison(v,keep) for k,v in groups.items()}
    flags=[k for k,v in comparisons.items() if v.get('available') and (v['ks']>=.2 or abs(v['standardized_mean_difference'])>=.5)]
    flags.extend(k for k,v in categories.items() if v.get('available') and v['total_variation']>=.1)
    review=dict(source_count=len(raw),retained=int(keep.sum()),excluded=int((~keep).sum()),
        numerical=comparisons,categorical=categories,flags=flags,
        screening_rule='Review flag if KS>=0.20 or absolute SMD>=0.50; categorical TV>=0.10. Engineering safeguards, not proof of equivalence.',
        policy='k8 then k16 for failures only; radius=200m; gps_error=50m; no splitting; no raw deletion',
        decision='BLOCKED_SELECTION_DIFFERENCES' if flags else 'NO_SCREENING_FLAGS_NOT_PROOF_OF_EQUIVALENCE')
    (a.out/'selection_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    with (a.out/'selection.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['source_index','retained','first_success_candidates','reason'])
        writer.writerows((r['source_index'],r['accepted'],r['first_success_candidates'],r['reason']) for r in records)
    save(a.out/'reviewed_records.pkl.gz',records)
    print(json.dumps({k:review[k] for k in ['source_count','retained','excluded','flags','decision']},ensure_ascii=False),flush=True)
    acknowledged=bool(a.accept_reviewed_subset and (a.accept_reviewed_subset.lower()=='yes' or a.accept_reviewed_subset==digest(a.out/'selection_review.json')))
    if a.accept_reviewed_subset and not acknowledged:
        raise ValueError('Approval hash does not match the recomputed selection review')
    if (flags and not acknowledged) or a.review_only:
        run_record['status']='BLOCKED_SELECTION_DIFFERENCES' if flags else 'REVIEW_ONLY'
        (a.out/'preprocessing_run.json').write_text(json.dumps(run_record,ensure_ascii=False,indent=2),encoding='utf-8')
        print('NOT FROZEN: review required. No new synthesis or evaluation may use this as an approved dataset.',flush=True)
        if flags:raise SystemExit(2)
        return
    # Canonical coordinates are the observations projected onto their selected road segment, never a second routing pass.
    to_xy=Transformer.from_crs('EPSG:4326',graph.crs,always_xy=True)
    to_ll=Transformer.from_crs(graph.crs,'EPSG:4326',always_xy=True)
    geometries=dict(zip(graph['id'].astype(int),graph.geometry))
    import shapely
    prepared=a.out/'dataset';prepared.mkdir()
    coordinates=[];roads=[];source_ids=[]
    for r in records:
        if not r['accepted']:continue
        coords=np.asarray(raw[r['source_index']],dtype=np.float64)
        x,y=to_xy.transform(coords[:,1],coords[:,0])
        lines=np.asarray([geometries[e] for e in r['opath']],dtype=object)
        points=shapely.points(x,y)
        projected=shapely.line_interpolate_point(lines,shapely.line_locate_point(lines,points))
        lon,lat=to_ll.transform(shapely.get_x(projected),shapely.get_y(projected))
        coordinates.append(np.column_stack((lat,lon)));roads.append(r);source_ids.append(r['source_index'])
        if len(roads)%1000==0:print(f'PROJECTED {len(roads)}/{int(keep.sum())}',flush=True)
    save(prepared/'trajectories.pkl',coordinates);save(prepared/'trajectories.pkl.gz',coordinates)
    save(prepared/'road_records.pkl.gz',roads)
    ids=np.random.default_rng(a.seed).permutation(len(roads));ntrain=round(.8*len(roads))
    for name,indices in [('train',ids[:ntrain]),('test',ids[ntrain:])]:
        save(prepared/f'{name}.pkl',[coordinates[i] for i in indices])
        (prepared/f'{name}_split.json').write_text(json.dumps({'indices':indices.tolist(),'source_indices':[source_ids[i] for i in indices]}),encoding='utf-8')
    (prepared/'bbox.json').write_text(json.dumps({'bbox':a.bbox}),encoding='utf-8')
    (prepared/'source_indices.json').write_text(json.dumps(source_ids),encoding='utf-8')
    artifacts={f.name:digest(f) for f in prepared.iterdir() if f.is_file()}
    manifest=dict(schema='frozen-road-dataset-v1',dataset=a.dataset,status='FROZEN',trajectory_count=len(roads),
        train_count=ntrain,test_count=len(roads)-ntrain,seed=a.seed,artifacts=artifacts,
        preprocessing=dict(candidates=[8,16],radius_m=200,gps_error_m=50),
        network=str(a.network.resolve()),network_sha256=digest(a.network),
        network_sidecars={f.suffix:digest(f) for f in a.network.parent.glob(a.network.stem+'.*') if f.suffix.lower() in ['.shp','.shx','.dbf','.prj','.cpg']},
        original_source_sha256=digest(a.source),selection_review_sha256=digest(a.out/'selection_review.json'),
        coordinates='Projection of each original observation onto its matched public road segment; no additional route selection',
        evaluation_population='This dataset only; never the raw source count or algorithm-specific matched subset',
        release_note='Private prepared input and audit, not a DP synthetic release')
    manifest['selection_scope']=dict(accepted_review_sha256=a.accept_reviewed_subset,
        scope='Reliably road-reconstructable cohort under fixed public drivable graph and k8->k16',
        screening_flags=flags,unbiased_sample_claim=False)
    (prepared/'canonical_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    run_record['status']='FROZEN';run_record['dataset_manifest_sha256']=digest(prepared/'canonical_manifest.json')
    (a.out/'preprocessing_run.json').write_text(json.dumps(run_record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FROZEN: '+str(prepared),flush=True)

if __name__=='__main__':main()

"""Export a city-neutral record format from an approved frozen road dataset.

No matching, filtering, resplitting or invented timestamps. Legacy prepared files
are retained as a compatibility view, not a second independently selected corpus.
"""
import argparse
import csv
import gzip
import json
import math
from pathlib import Path
import pickle
import shutil
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_config import load_config
from preprocess.dataset_contract import validate_dataset,sha
from preprocess.mtnet_endpoints import load_endpoints
from preprocess.framed_records import records as iter_records


def load(path):
    with (gzip.open(path,'rb') if str(path).endswith('.gz') else open(path,'rb')) as f:
        return pickle.load(f)


def export(config, output):
    started=time.perf_counter();out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    c=load_config(config,ROOT)
    def path(key):return (ROOT/c['paths'][key]).resolve()
    prepared=path('prepared');network=path('network')
    identity=validate_dataset(prepared,public_network=network)
    meta=json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    n=identity['count']
    sources=json.loads((prepared/'source_indices.json').read_text(encoding='utf-8'))
    train=json.loads((prepared/'train_split.json').read_text(encoding='utf-8'))['indices']
    test=json.loads((prepared/'test_split.json').read_text(encoding='utf-8'))['indices']
    split={i:'train' for i in train};split.update({i:'test' for i in test})
    endpoints=None
    if c['paths'].get('time_endpoints'):
        endpoints=load_endpoints(path('time_endpoints'),sources,list(range(len(sources))))
    elif c['paths'].get('mtnet_time_binding'):
        b=json.loads(path('mtnet_time_binding').read_text(encoding='utf-8'))
        if b.get('status')!='complete':raise ValueError('Incomplete historical time input')
        if c['paths'].get('mtnet_raw_reference') and sha(path('mtnet_raw_reference'))!=b['reference_sha256']:
            raise ValueError('Historical time reference differs')
        endpoints=[]
        for source in sources:
            r=b['records'][source]
            if r['id']!=source+1:raise ValueError('Historical source order differs')
            endpoints.append(r)
    timestamp_path=prepared/'start_road_timestamps.pkl.gz'
    has_timestamps=timestamp_path.exists()
    out.mkdir(parents=True)
    (out/'prepared').mkdir();(out/'public').mkdir()
    # Existing consumers keep exactly the existing bytes and split membership.
    for name in set(meta['artifacts'])|{'canonical_manifest.json'}:
        shutil.copy2(prepared/name,out/'prepared'/name)
    for suffix in ('.shp','.shx','.dbf','.prj','.cpg'):
        p=network.with_suffix(suffix)
        if p.exists():shutil.copy2(p,out/'public'/('network'+suffix))
    if 'metric_cache' in c['paths']:shutil.copy2(path('metric_cache'),out/'public/metric_cache.pkl.gz')
    additional_paths={}
    for key,name in [('osm','public_ways.pkl'),('edge_cache','edge_cache.pkl.gz')]:
        if key in c['paths']:
            shutil.copy2(path(key),out/'public'/name)
            additional_paths[key]='public/'+name
    (out/'prepared/network_location.json').write_text(json.dumps({'relative_path':'../public/network.shp'}),encoding='utf-8')
    with gzip.open(out/'records.jsonl.gz','wt',encoding='utf-8') as stream,(out/'time_endpoints.csv').open('w',encoding='utf-8',newline='') as times:
        writer=csv.writer(times);writer.writerow(['record_index','source_index','start_ts','end_ts'])
        import itertools
        times_iter=iter_records(timestamp_path,n) if has_timestamps else itertools.repeat(None,n)
        row_count=0
        for i,(points,road,observed_times) in enumerate(zip(iter_records(prepared/'trajectories.pkl',n),iter_records(prepared/'road_records.pkl.gz',n),times_iter,strict=True)):
            points=np.asarray(points,dtype=float)
            if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():raise ValueError('Coordinates must be finite latitude/longitude pairs')
            if np.any(np.abs(points[:,0])>90) or np.any(np.abs(points[:,1])>180):raise ValueError('Coordinates are not WGS84 latitude/longitude')
            if not road.get('accepted') or not road.get('connected') or not road.get('cpath'):raise ValueError('Unaccepted or disconnected road record')
            t=None
            if has_timestamps:
                t=np.asarray(observed_times,dtype=float)
                if len(t)!=len(points) or not np.isfinite(t).all() or np.any(np.diff(t)<0):raise ValueError('Processed point time mismatch')
                t=t.tolist()
            start=end=None
            if endpoints is not None:
                start,end=float(endpoints[i]['start_ts']),float(endpoints[i]['end_ts'])
                if not math.isfinite(start) or not math.isfinite(end) or end<start:raise ValueError('Invalid endpoints')
                if t is not None and (start!=t[0] or end!=t[-1]):raise ValueError('Endpoint/point time disagreement')
                writer.writerow([i,sources[i],start,end])
            record=dict(record_index=i,source_index=sources[i],split=split[i],coordinates=points.tolist(),
                        road_ids=[int(e) for e in road['cpath']],point_timestamps=t,start_ts=start,end_ts=end)
            stream.write(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n')
            row_count+=1
            if row_count%100000==0:print('STANDARD_RECORDS_PROGRESS',row_count,n,flush=True)
    if row_count!=n:raise ValueError('Export population mismatch')
    bundle=dict(schema='road-experiment-bundle-v1',dataset=c['dataset'],record_schema='road-trajectory-record-v1',
                coordinate_order='latitude,longitude',coordinate_crs='EPSG:4326',
                coordinate_semantics=meta.get('coordinates','Frozen source coordinates; see original preprocessing'),
                timestamp_semantics=meta.get('time_semantics','Only original source endpoints available; no point times invented'),
                source_dataset_id=identity['dataset_id'],paths=dict(prepared='prepared',network='public/network.shp'),
                limitations=['Only the prepared road-corpus export is implemented here; raw ingestion remains an upstream adapter',
                             'Routing executables and algorithm-specific public resources are not constructed by this export'])
    if endpoints is not None:bundle['paths']['time_endpoints']='time_endpoints.csv'
    bundle['paths'].update(additional_paths)
    if 'metric_cache' in c['paths']:
        bundle['paths'].update(metric_cache='public/metric_cache.pkl.gz',source_cache='public/metric_cache.pkl.gz')
    if 'dfr_author_roads' in c:
        from preprocess.dfr_author_roads import load_author_domain
        load_author_domain(c['dfr_author_roads'],ROOT,network)
        original=(ROOT/c['dfr_author_roads']['manifest']).resolve()
        graph_meta=json.loads(original.read_text(encoding='utf-8'))
        # Copy the actual author mapping, never manufacture OSM attributes.
        for name in ('road_mapping.json','public_ways.pkl'):
            source=original.parent/name
            if sha(source)!=graph_meta['outputs'][name]:raise ValueError('Author graph changed: '+name)
            shutil.copy2(source,out/'public'/name)
        target=out/'public/author_graph_manifest.json';shutil.copy2(original,target)
        bundle['dfr_author_roads']=dict(manifest='public/author_graph_manifest.json',sha256=sha(target))
    for key in ('bbox','routing_crs'):
        if key in c:bundle[key]=c[key]
    (out/'dataset.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(status='STANDARD_RECORDS_EXPORTED',count=row_count,train_count=len(train),test_count=len(test),
                point_times_available=has_timestamps,endpoints_available=endpoints is not None,
                seconds=time.perf_counter()-started,files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'export_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('STANDARD_RECORDS_EXPORTED',report['count'],report['seconds'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();export(a.config,a.out)

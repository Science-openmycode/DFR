"""Collect new sweep artifacts with explicit bindings; never synthesize or evaluate."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import gzip
import pickle
try:
    from tools.k_diagnostics import endpoint_diagnostics,paired_summary
except ModuleNotFoundError:
    from k_diagnostics import endpoint_diagnostics,paired_summary

ROOT=Path(__file__).resolve().parents[1]


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def aggregate(rows,axis):
    groups={}
    for row in rows:groups.setdefault((row['stage'],row['metric'],row[axis]),[]).append(row)
    result=[]
    for (stage,metric,value),items in sorted(groups.items()):
        if len(items)!=5 or len({r['seed'] for r in items})!=5:raise ValueError('Expected five independent seeds')
        vals=[r['value'] for r in items if r['value'] is not None]
        result.append(dict(stage=stage,metric=metric,**{axis:value},n=len(vals),mean=statistics.mean(vals) if vals else None,sd=statistics.stdev(vals) if len(vals)>1 else None))
    return result


def collect(kind,plan,out,config=None):
    if out.exists():raise FileExistsError(out)
    cells=[c for c in json.loads(plan.read_text(encoding='utf-8'))['cells'] if c['kind']==kind]
    expected={'budget':35,'k':30,'endpoint_diagnostic':3}[kind]
    if len(cells)!=expected:raise ValueError('Incomplete design')
    rows=[];sources={};diagnostics=[]
    cfg=json.loads(Path(config).read_text(encoding='utf-8')) if config else None
    population=cfg['slots'] if cfg else 15730
    def input_path(key,default):
        return (ROOT/cfg['paths'][key]).resolve() if cfg else ROOT/default
    cache_path=input_path('metric_cache','resources/metric_cache/metric_cache.pkl.gz')
    real_path=input_path('real_routes','resources/dataset/road_records.pkl.gz')
    graph_path=input_path('network','resources/network/network.shp')
    def source_key(p):
        p=Path(p).resolve()
        return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
    def load(p):
        sources[source_key(p)]=sha(p)
        return json.loads(p.read_text(encoding='utf-8'))
    def verify_bindings(obj):
        if isinstance(obj,dict):
            if isinstance(obj.get('path'),str) and isinstance(obj.get('sha256'),str):
                if sha(obj['path']).lower()!=obj['sha256'].lower():raise ValueError('Changed bound input')
            for value in obj.values():verify_bindings(value)
        elif isinstance(obj,list):
            for value in obj:verify_bindings(value)
    if kind in ('k','endpoint_diagnostic'):
        sources[source_key(cache_path)]=sha(cache_path)
        sources[source_key(real_path)]=sha(real_path)
        with gzip.open(cache_path,'rb') as f:cache=pickle.load(f)
        with gzip.open(real_path,'rb') as f:records=pickle.load(f)
        if len(records)!=population:raise ValueError('Wrong private diagnostic population')
        real=[tuple(cache['edge_nodes'][int(e)] for e in r['cpath']) if r['accepted'] and r['cpath'] else () for r in records]
    for cell in cells:
        base=ROOT/cell['directory'];native=base/'native/MTR-DFR'
        post=ROOT/cell.get('post_directory',cell['directory'])
        lineage=load(native.with_name('MTR-DFR.private_audit')/'input_lineage.json')
        if lineage['status']!='DONE' or lineage['dataset']['count']!=population:raise ValueError('Incomplete generation')
        for name,digest in lineage['outputs'].items():
            if sha(native/name)!=digest:raise ValueError('Generation artifact changed')
        rep=load(post/'representation/route_manifest.json')
        if rep['records']!=population or rep['rematched'] is not False:raise ValueError('Wrong representation')
        if rep['output_sha256']!=sha(post/'representation/synthetic_routes.pkl.gz'):raise ValueError('Road output changed')
        raw=native/f'seed_{cell["seed"]}_length/road_routes.pkl.gz'
        if rep['native_sha256']!=sha(raw):raise ValueError('Native source changed')
        diagnostic=dict(k=cell['value'],seed=cell['seed'],diagnostic=kind=='endpoint_diagnostic',generation_seconds=lineage['elapsed_seconds'])
        for stage in ['road_scores','physical','coordinate_scores','road_tasks']:
            folder=post/stage;meta=load(folder/'manifest.json')
            verify_bindings(meta)
            if stage=='physical':
                file=folder/'results.csv'
                if sha(file)!=meta['results_sha256']:raise ValueError('Physical result changed')
                with file.open(encoding='utf-8-sig',newline='') as f:metrics=next(csv.DictReader(f))
                expected_inputs={'real_routes':real_path,'synthetic_routes':post/'representation/synthetic_routes.pkl.gz','edge_cache':cache_path,'network':graph_path}
                for name,p in expected_inputs.items():
                    if meta['inputs_sha256'][name]!=sha(p):raise ValueError('Physical input changed')
            else:
                file=folder/'metrics.json';payload=load(file);metrics=payload.get('metrics',payload)
                if stage=='coordinate_scores' and sha(file)!=meta['outputs']['metrics.json']:raise ValueError('Coordinate result changed')
                if stage=='road_tasks' and sha(file)!=meta['result_sha256']:raise ValueError('Road task changed')
                if stage=='road_tasks':
                    for name,digest in meta['inputs'].items():
                        if sha(name)!=digest:raise ValueError('Road task input changed')
            if stage=='road_scores':
                diagnostic.update({m:metrics[m] for m in ['BTF','RC-CPC','EdgeCPC','TurnCPC','FamilyCPC']})
            if stage=='coordinate_scores':
                diagnostic.update(OD_jsd=metrics['OD_jsd'],LengthJSD=metrics['path_length_jsd'])
            sources[source_key(file)]=sha(file)
            for metric,value in metrics.items():
                if isinstance(value,(dict,list,bool)) or metric=='method':continue
                try:v=float(value) if value is not None else None
                except (TypeError,ValueError):continue
                if v is not None and not math.isfinite(v):v=None
                rows.append(dict(run=cell['name'],**{'epsilon' if kind=='budget' else 'k':cell['value']},seed=cell['seed'],stage=stage,metric=metric,value=v,status='NA' if v is None else 'VALID'))
        if kind in ('k','endpoint_diagnostic'):
            partition=load(ROOT/cell.get('endpoint_partition',f'resources/endpoint_partitions/partition{cell["value"]}.json'))
            labels={int(n):int(v) for n,v in partition['labels'].items()}
            transcript_path=raw.parent/'dp_transcript.pkl.gz'
            sources[source_key(transcript_path)]=sha(transcript_path)
            with gzip.open(transcript_path,'rb') as f:transcript=pickle.load(f)
            metadata=load(raw.parent/'research_metadata.json')
            diagnostic.update(endpoint_diagnostics(real,labels,cell['value'],transcript,metadata))
            diagnostics.append(diagnostic)
    axis='epsilon' if kind=='budget' else 'k'
    result=dict(scope='Full-corpus research runs; not a joint DP release',runs=expected,rows=rows,
        seeds_per_epsilon=5 if kind=='budget' else None,
        aggregates=[] if kind=='endpoint_diagnostic' else aggregate(rows,axis),
        sources=sources,process_exit_evidence='Per-command terminal/log records remain separate; artifact acceptance does not invent exit codes')
    out.mkdir(parents=True)
    if diagnostics:
        (out/'endpoint_diagnostics.json').write_text(json.dumps({'classification':'PRIVATE_RESEARCH_EVALUATION_NOT_DP_RELEASE','rows':diagnostics,
            'paired_summary':paired_summary(diagnostics) if kind=='k' else {}},indent=2),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    with (out/'per_run.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'manifest.json').write_text(json.dumps({'inputs':sources,'summary_sha256':sha(out/'summary.json'),
        'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
        'collector_sha256':sha(__file__),'diagnostic_code_sha256':sha(Path(__file__).with_name('k_diagnostics.py'))},indent=2),encoding='utf-8')
    print(json.dumps({'runs':expected,'numeric_rows':len(rows),'out':str(out)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=['k','budget','endpoint_diagnostic'],required=True)
    p.add_argument('--plan',type=Path,default=ROOT/'supplement/sweeps/plan.json');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--config',type=Path,help='Current population/reference paths; defaults to the historical Beijing input layout')
    a=p.parse_args();collect(a.kind,a.plan,a.out,a.config)

"""Repackage verified source tables with the existing mean/sample-SD convention.

No synthesis, routing, private fitting or metric implementation is performed.
The plan explicitly names every existing source table; no newest-file search.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import math

METHOD_ROWS = {'DFR':'MTR-DFR','PrivTrace':'PrivTrace + MM2-MDP',
    'AdaTrace':'AdaTrace + MM2-MDP','DPTraj-PM':'DPTraj-PM + MM2-MDP',
    'MTNet':'MTNet','MTNet+DP-OD':'MTNet_DP_OD_coarse24'}
METRICS = {'Grid':('coordinate_scores','grid_density_jsd'),
    'Trip':('coordinate_scores','trip_error'),'Len':('coordinate_scores','path_length_jsd'),
    **{k:('road_scores',k) for k in ('RoadYield','BTF','FamilyCPC','ODPF384')},
    **{k:('applications',k) for k in ('MFPOrderedRouteOverlap','RepresentativeRealCoverage',
        'SelectedRoadMarginalOverlap','IncomingExitDistributionOverlap')}}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def collect(plan, out):
    plan=Path(plan).resolve(); runs=json.loads(plan.read_text(encoding='utf-8-sig'))
    groups={}; identities=set(); sources={}; seen=set()
    for run in runs:
        method=run['method']; eps=float(run['epsilon']); seed=str(run['seed'])
        key=(method,eps,seed)
        if method not in METHOD_ROWS or key in seen:raise ValueError('Unknown/duplicate run: '+str(key))
        seen.add(key)
        release=Path(run['release_manifest'])
        if not release.is_absolute():release=plan.parent/release
        lineage=json.loads(release.read_text(encoding='utf-8-sig'))
        budget=next((lineage[k] for k in ('epsilon_total','epsilon_training','epsilon') if k in lineage),None)
        if budget is None or not math.isclose(float(budget),eps,abs_tol=1e-12):raise ValueError('Release budget differs from plan')
        sources[str(release)]=sha(release)
        folder=Path(run['sources'])
        if not folder.is_absolute():folder=plan.parent/folder
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        table=folder/'matrix_sources.csv'
        if sha(table)!=m['outputs']['matrix_sources.csv']:raise ValueError('Changed source table')
        population=m.get('population') or {}
        identities.add((population.get('dataset_id'),population.get('count')))
        sources[str(folder/'manifest.json')]=sha(folder/'manifest.json')
        with table.open(encoding='utf-8-sig',newline='') as f:
            rows=[r for r in csv.DictReader(f) if r['row']==METHOD_ROWS[method]]
        by={r['column']:r for r in rows}
        if len(by)!=len(rows):raise ValueError('Duplicate metric rows')
        for metric,(stage,name) in METRICS.items():
            r=by[metric]
            if r['status'] not in ('VALID','ZERO') or r['value']=='':raise ValueError('Unscored/undefined value: '+str(key)+metric)
            for field in ('result','manifest'):
                if sha(r[field])!=r[field+'_sha256']:raise ValueError('Changed score source: '+r[field])
            value=float(r['value'])
            if not math.isfinite(value):raise ValueError('Non-finite metric')
            groups.setdefault((method,eps,stage,name),[]).append((seed,value))
    if len(identities)!=1 or any(x is None for x in next(iter(identities))):raise ValueError('Unbound or different populations')
    expected={(method,e,stage,name) for method in METHOD_ROWS for e in (.2,.4,.7,1.,1.4,2.,3.) for stage,name in METRICS.values()}
    if set(groups)!=expected:raise ValueError('Incomplete six-method/seven-budget matrix')
    rows=[]
    for (method,eps,stage,metric),values in groups.items():
        n=5 if method=='DFR' else 1
        if len(values)!=n or len({s for s,v in values})!=n:raise ValueError('Wrong replicate count')
        scores=[v for s,v in values]
        rows.append(dict(method=method,epsilon=eps,stage=stage,metric=metric,
            value=statistics.mean(scores),n=n,sd=statistics.stdev(scores) if n>1 else '',
            seeds=';'.join(s for s,v in values)))
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    with (out/'plot_data.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'manifest.json').write_text(json.dumps(dict(status='COMPLETE',plan_sha256=sha(plan),
        population=list(identities)[0],runs=len(seen),points=len(rows),sources=sources,
        plot_data_sha256=sha(out/'plot_data.csv'),metrics_recomputed=False),indent=2),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();collect(a.plan,a.out)

"""Evaluate saved coordinate/road datasets with the preserved complete evaluator."""
import argparse
import json
import os
import pickle
from pathlib import Path
import subprocess
import sys

from preprocess.dataset_contract import validate_dataset
from tools.stage_routed_coordinates import stage
from experiments.separate import resolve_saved_route
from tools.coordinate_resource_binding import coordinate_resources

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--method',required=True,choices=('SPRT','PrivTrace','DPStd','DPTraj-PM','MTR-DFR','MTNet'))
    p.add_argument('--router',required=True,choices=('Origin','Nearest','FMM','STMatch','MM2-MDP'))
    p.add_argument('--input',type=Path,help='Explicit route object if not in its default directory')
    p.add_argument('--out',type=Path)
    p.add_argument('--batch',help='Explicit output batch; avoids reusing another batch coordinate views')
    p.add_argument('--metric-protocol',choices=('legacy','audit-v2'),default='legacy',
                   help='audit-v2 fixes confirmed audit defects; isolated outputs, frozen jobs unchanged')
    a=p.parse_args();c=json.loads(a.config.read_text(encoding='utf-8'))
    if a.batch:
        if Path(a.batch).name != a.batch or a.batch in ('.','..'):
            p.error('batch must be a single directory name')
        c['batch']=a.batch
        c.pop('saved_route_inputs',None)
    def path(key):return (ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'),public_network=path('network'))
    if identity['dataset_id']!=c['frozen_dataset_id']:
        raise ValueError('Wrong real reference')
    base=path('output')/c['batch']
    measurement=base/'measurements'/a.method/'measurement.pkl'
    score_folder='coordinate_scores_audit_v2' if a.metric_protocol=='audit-v2' else 'coordinate_scores'
    out=(a.out or base/score_folder/a.method/a.router).resolve()
    if out.exists():raise FileExistsError(out)
    road=None
    score_cache=path('edge_cache')
    if a.method in ('MTR-DFR','MTNet'):
        if a.router != 'Origin':
            p.error('Native generators only have their own Original R; no rematching')
        from tools.stage_native_saved_coordinates import build
        road=resolve_saved_route(c, ROOT, base, a.method, a.router, a.input)
        view=base/'coordinate_views'/a.method/a.router
        if not view.exists():
            build(road,path('network'),path('edge_cache'),view)
        synthetic=view/'coordinates.pkl'
    elif a.router=='Origin':
        synthetic=(a.input or measurement).resolve()
    else:
        road=resolve_saved_route(c, ROOT, base, a.method, a.router, a.input)
        score_cache, stage_options=coordinate_resources(c,ROOT,a.router,road.parent/'route_manifest.json')
        view=base/'coordinate_views'/a.method/a.router
        if not view.exists():
            stage(road,road.parent/'route_manifest.json',path('network'),view,
                  measurement=measurement,edge_cache=score_cache,for_road_scoring=True,**stage_options)
        synthetic=view/'coordinates.pkl'
    command=[sys.executable,'-X','utf8',str(ROOT/'run.py'),'evaluate-cell',
             '--dataset',c['dataset'],'--m',a.method,'--r',a.router,'--synthetic',str(synthetic),
             '--real-reference',str(path('real')),'--prepared-data',str(path('prepared')),
             '--osm-cache',str(path('osm')),'--public-slot-count',str(c['slots']),
             '--evaluation-seed',str(c['evaluation_seed']),'--out-dir',str(out)]
    if road is not None:
        command+=['--road-routes',str(road),'--edge-cache',str(score_cache)]
    with synthetic.open('rb') as stream:
        arrays=pickle.load(stream)
    all_empty=bool(arrays) and not any(len(row)>=2 for row in arrays)
    del arrays
    if all_empty and a.metric_protocol=='legacy':
        command=[sys.executable,'-X','utf8',str(ROOT/'tools/evaluate_empty_coordinates.py'),
                 '--legacy',str(path('legacy')),'--real',str(path('real')),'--synthetic',str(synthetic),
                 '--out-dir',str(out),'--bbox',*map(str,c['bbox']),
                 '--evaluation-seed',str(c['evaluation_seed']),'--osm-cache',str(path('osm')),
                 '--public-slot-count',str(c['slots'])]
        if road is not None:
            command+=['--road-routes',str(road),'--edge-cache',str(score_cache)]
    if a.metric_protocol=='audit-v2':
        command=[sys.executable,'-X','utf8',str(ROOT/'evaluation/audit_v2_runner.py'),
                 '--stage','coordinates','--legacy',str(path('legacy')),'--',
                 '--real',str(path('real')),'--synthetic',str(synthetic),'--out-dir',str(out),
                 '--bbox',*map(str,c['bbox']),'--evaluation-seed',str(c['evaluation_seed']),
                 '--osm-cache',str(path('osm')),'--public-slot-count',str(c['slots'])]
        if road is not None:
            command+=['--road-routes',str(road),'--edge-cache',str(score_cache)]
    env=dict(os.environ,PYTHONUTF8='1',DFR_LEGACY_ROOT=str(path('legacy')),
             DFR_PRESERVE_EMPTY_SLOTS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    print('SCORING_SAVED_DATASET',a.method,a.router,flush=True)
    subprocess.run(command,cwd=ROOT,env=env,check=True)


if __name__=='__main__':
    main()

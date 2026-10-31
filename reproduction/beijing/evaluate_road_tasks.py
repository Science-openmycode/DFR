"""Actual road-choice NDCG and next-road tasks, not grid next-region proxies."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from preprocess.dataset_contract import validate_dataset, sha

ROOT=Path(__file__).resolve().parent


def verify_score_inputs(scored, expected_inputs):
    ledger=json.loads(Path(scored).read_text(encoding='utf-8'))
    for key,file in expected_inputs.items():
        if ledger['inputs'][key]['sha256']!=sha(file):
            raise ValueError('Road score input changed: '+key)
    return ledger


def road_task_records(raw, representation, metric_edges, source_edges=None, network=None):
    """Preserve legacy records, or deterministically represent verified native pairs.

    Source node numbers are never treated as metric-cache node numbers. Only
    the shared, explicitly bound edge IDs connect their two namespaces.
    """
    if representation == 'edge-records':
        if any(not isinstance(row,dict) for row in raw):
            raise ValueError('Expected explicit edge records')
        return raw
    if representation != 'node-pairs' or source_edges is None:
        raise ValueError('Native task input requires explicit node-pairs source binding')
    from tools.convert_native_node_pairs import convert, resolve_pairs
    used={tuple(map(int,pair)) for route in raw for pair in route}
    pairs=resolve_pairs(source_edges,metric_edges,network=network,required_pairs=used)
    return convert(raw,pairs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--method',required=True)
    p.add_argument('--router',required=True)
    p.add_argument('--input',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--score-manifest',type=Path,
                   help='Explicit prior road-score manifest, e.g. this ablation arm; all input hashes are verified')
    p.add_argument('--regions',type=int,choices=(24,96,384),default=384)
    p.add_argument('--real-query-fraction',type=float,default=.2,
                   help='Preserved last-20-percent retrospective query set, not unseen TSTR')
    p.add_argument('--mixture-weight',type=float,default=.5)
    a=p.parse_args()
    if not 0<a.real_query_fraction<=1 or not 0<a.mixture_weight<1:p.error('Invalid fraction/weight')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    def path(key):return (ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'),public_network=path('network'))
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen population')
    base=path('output')/c['batch']
    roads=(a.input or base/'routes'/a.method/a.router/'synthetic_routes.pkl.gz').resolve()
    out=(a.out or base/'road_tasks'/a.method/a.router).resolve()
    if out.exists():raise FileExistsError(out)
    scored=(a.score_manifest or base/'scores'/a.method/a.router/'manifest.json').resolve()
    score_binding=verify_score_inputs(scored,dict(real_routes=path('real_routes'),synthetic_routes=roads,
                                                 metric_cache=path('metric_cache')))
    legacy=path('legacy')/'evaluation'
    sys.path[:0]=[str(legacy),str(legacy/'evaluation')]
    from route_metric_core import load_pickle, normalize_routes, valid_routes
    from metric_suites.road_choice import public_crossing_options, matched_choice_trips, road_choice_fidelity, next_road_trip_scores
    started=time.perf_counter();cache=load_pickle(path('metric_cache'))
    edge_nodes={int(e):tuple(map(int,pair)) for e,pair in cache['edge_nodes'].items()}
    labels=cache['labels'+str(a.regions)]
    regions={e:(int(labels[u]),int(labels[v])) for e,(u,v) in edge_nodes.items()}
    options,contexts=public_crossing_options(regions,edge_nodes)
    real=load_pickle(path('real_routes'));synthetic=load_pickle(roads)
    representation=score_binding.get('representation','edge-records')
    source_edges=None
    if representation=='node-pairs':
        binding=score_binding['inputs']['source_cache']
        source=Path(binding['path'])
        if sha(source)!=binding['sha256']:raise ValueError('Native source cache changed')
        source_edges=load_pickle(source)['edge_nodes']
    if representation=='node-pairs':
        # Geometry proof must come from the same graph as the preceding score.
        verify_score_inputs(scored,dict(network=path('network')))
        for binding in score_binding['inputs'].get('network_sidecars',[]):
            selected=path('network').with_suffix(Path(binding['path']).suffix)
            if sha(selected)!=binding['sha256']:
                raise ValueError('Native public network sidecar changed')
    synthetic=road_task_records(synthetic,representation,edge_nodes,source_edges,path('network'))
    if len(real)!=c['slots'] or len(synthetic)!=c['slots'] or len(valid_routes(normalize_routes(real,cache)))!=c['slots']:
        raise ValueError('Do not change either full-population denominator')
    real_trips=matched_choice_trips(real,contexts,edge_nodes)
    synthetic_trips=matched_choice_trips(synthetic,contexts,edge_nodes)
    split=int(len(real_trips)*(1-a.real_query_fraction))
    query=real_trips[split:]
    fidelity=road_choice_fidelity(synthetic_trips,query,options)
    scores=next_road_trip_scores(synthetic_trips,query,options,mixture_weight=a.mixture_weight)
    evidence=len(valid_routes(normalize_routes(synthetic,cache)))/len(synthetic)
    accuracy=float(np.mean(scores['next_road_accuracy']));nll=float(np.mean(scores['next_road_nll']))
    result=dict(RoadEvidenceYield=evidence,
                **{'RC-NDCG':fidelity['road_choice_ndcg']*evidence},
                NextRoadAcc=accuracy*evidence,NextRoadNLL=nll-math.log(evidence) if evidence else None,
                conditional_road_choice_cpc=fidelity['road_choice_cpc'],
                conditional_rc_ndcg=fidelity['road_choice_ndcg'],
                conditional_next_road_accuracy=accuracy,conditional_next_road_nll=nll)
    out.mkdir(parents=True)
    payload=dict(metrics=result,metric_status={'NextRoadNLL':'VALID' if evidence else 'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE'},
                 scope='Retrospective road-law utility; full-corpus synthesis, fixed real query subset; not strict TSTR')
    (out/'metrics.json').write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    core=Path(sys.modules['metric_suites.road_choice'].__file__)
    manifest=dict(dataset_id=identity['dataset_id'],real_slots=len(real),synthetic_slots=len(synthetic),
                  real_query_start=split,real_query_count=len(query),quotient_regions=a.regions,
                  next_road_mixture_weight=a.mixture_weight,real_query_fraction=a.real_query_fraction,
                  failed_policy='All slots retained; conditional utilities multiplied by actual road yield; NLL penalized by -log(yield)',
                  source_representation=representation,representation_only=True,rematched=False,
                  representation_resolver_sha256=sha(ROOT/'tools/convert_native_node_pairs.py'),
                  inputs={str(f):sha(f) for f in (path('real_routes'),roads,path('metric_cache'),scored)},
                  metric_core=dict(path=str(core),sha256=sha(core)),
                  result_sha256=sha(out/'metrics.json'),command=[sys.executable,*sys.argv],seconds=time.perf_counter()-started)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('DONE_ROAD_TASKS',a.method,a.router,json.dumps(result),flush=True)


if __name__=='__main__':main()

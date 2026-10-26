"""Explicit undefined-distribution boundary for a release with no usable paths.

The preserved evaluator otherwise calls min() on an empty DTW candidate pool.
Only this all-empty boundary is adapted; no normal-case metric is changed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

UNDEFINED=('grid_density_jsd','trip_error','path_length_jsd',
           'conditional_nn_dtw_km','conditional_nn_frechet_km','road_segment_jsd')


def empty_statistics(real, synthetic, *args, **kwargs):
    if not synthetic or any(len(row)>=2 for row in synthetic):
        raise ValueError('Empty boundary must not handle an ordinary release')
    return {**{key:None for key in UNDEFINED},'directed_road_validity':0.,'route_compatible_yield':0.}


def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--legacy',type=Path,required=True)
    a,rest=p.parse_known_args()
    legacy=a.legacy.resolve()/'evaluation'
    sys.path[:0]=[str(legacy),str(legacy/'pipeline'),str(legacy/'analysis_scripts')]
    import evaluate_kdd_revised_statistics as stats
    stats.evaluate=empty_statistics
    file=legacy/'evaluation/evaluate_all.py'
    spec=importlib.util.spec_from_file_location('preserved_empty_boundary_evaluator',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sys.argv=[str(file),*rest]
    module.main()
    out=Path(rest[rest.index('--out-dir')+1])
    payload=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
    payload['metric_status']={key:{'status':'NA','reason':'No nonempty synthetic paths; empirical distribution/distance is undefined, not a uniform distribution'} for key in UNDEFINED}
    (out/'metrics.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    import hashlib
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    manifest['outputs']['metrics.json']=hashlib.sha256((out/'metrics.json').read_bytes()).hexdigest()
    manifest['empty_boundary_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['empty_boundary_policy']='All slots retained; undefined marginal distributions/distances are NA; no substitute paths'
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()

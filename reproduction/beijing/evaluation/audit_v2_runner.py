"""Versioned corrected evaluator. Frozen evaluator files remain unchanged."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation import audit_metric_fixes as fixes


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolve_forwarded_paths(argv, cwd=None):
    """Resolve caller paths before the legacy evaluator uses its own root."""
    base = Path.cwd() if cwd is None else Path(cwd)
    result = list(argv)
    for flag in ('--real','--synthetic','--out-dir','--osm-cache','--road-routes','--edge-cache'):
        if flag in result:
            index = result.index(flag)+1
            if index >= len(result) or result[index].startswith('--'):
                raise ValueError('Missing path value: '+flag)
            value = Path(result[index])
            result[index] = str((value if value.is_absolute() else base/value).resolve())
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=('coordinates',), required=True)
    p.add_argument('--legacy', type=Path, required=True)
    args, rest = p.parse_known_args()
    if rest[:1] == ['--']:
        rest = rest[1:]
    rest = resolve_forwarded_paths(rest)
    legacy = args.legacy.resolve() / 'evaluation'
    sys.path[:0] = [str(legacy), str(legacy/'pipeline'), str(legacy/'analysis_scripts')]
    import public_utils
    public_utils._coerce_traj_list = fixes.preserve_slots
    os.environ['DFR_PRESERVE_EMPTY_SLOTS'] = '1'
    paths = dict(coordinates=legacy/'evaluation/evaluate_all.py')
    bound = [Path(__file__), Path(fixes.__file__), legacy/'public_utils.py',
             legacy/'pipeline/evaluate_kdd_revised_statistics.py',
             paths[args.stage]]
    before = {str(f): digest(f) for f in set(bound)}
    module = load(paths[args.stage], 'audit_v2_'+args.stage)
    length_audit = {}
    if args.stage == 'coordinates':
        import evaluate_kdd_revised_statistics as stats
        original = stats.evaluate

        def evaluate(real, syn, *pos, **kw):
            if any(len(t) >= 2 for t in syn):
                metrics = original(real, syn, *pos, **kw)
            else:
                metrics = {k: None for k in ('grid_density_jsd','trip_error','path_length_jsd',
                    'conditional_nn_dtw_km','conditional_nn_frechet_km','road_segment_jsd')}
                metrics.update(directed_road_validity=0., route_compatible_yield=0.)
            length_audit.update(fixes.length_statistics(real, syn, stats))
            metrics['path_length_jsd'] = length_audit['path_length_jsd']
            return metrics

        stats.evaluate = evaluate
        original_object = module._score_published_road_object

        def object_score(metrics, *pos, **kw):
            source = original_object(metrics, *pos, **kw)
            fixes.dirvalid_fields(metrics, source)
            return source

        module._score_published_road_object = object_score
    out = Path(rest[rest.index('--out-dir')+1]).resolve()
    if out.exists():
        raise FileExistsError(out)
    command = [sys.executable, *sys.argv]
    sys.argv = [str(paths[args.stage]), *rest]
    module.main()
    if any(digest(f) != h for f, h in before.items()):
        raise RuntimeError('Evaluator source changed during scoring')
    record = dict(protocol=fixes.PROTOCOL, stage=args.stage, source_sha256=before,
                  command=command, forwarded_argv=[str(paths[args.stage]),*rest], length=length_audit,
                  retrieval_ties='prefix score then stable training record ID; never hidden suffix',
                  continuation_nll='alpha=1e-12 normalized on PUBLIC outgoing neighbors; no queries NA',
                  tstr_values='unchanged clipped relative retention, not raw accuracy',
                  road_sampling='unchanged max256; loss diagnostics remain separate')
    (out/'metric_revision.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    if args.stage == 'coordinates':
        file = out/'metrics.json'
        result = json.loads(file.read_text(encoding='utf-8'))
        result['protocol']['metric_revision'] = fixes.PROTOCOL
        result['protocol']['length_bins_km'] = length_audit['edges_km']
        result['metric_status'] = {k: dict(status='NA', reason='No road object or undefined distribution')
                                  for k,v in result['metrics'].items() if v is None}
        file.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
        manifest_file = out/'manifest.json'
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
        manifest['outputs']['metrics.json'] = digest(file)
        manifest['metric_revision'] = dict(protocol=fixes.PROTOCOL,
                                           manifest_sha256=digest(out/'metric_revision.json'))
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

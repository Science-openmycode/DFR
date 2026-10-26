"""Independent stage entrypoints; never schedule another stage implicitly."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd')


def resolve_saved_route(config, root, base, method, router, explicit=None):
    """Use an explicit saved-result binding; never guess the newest directory."""
    if explicit is not None:
        return Path(explicit).resolve()
    saved = config.get('saved_route_inputs', {}).get(method, {}).get(router)
    if saved:
        return (root / saved).resolve()
    return (base / 'routes' / method / router / 'synthetic_routes.pkl.gz').resolve()


def validate_matcher_binding(config, root, router):
    binding = config.get('matcher_compatibility')
    if binding and router in ('FMM', 'STMatch'):
        key = router.lower()
        executable = (root / config['paths'][key]).resolve()
        expected = binding.get(key + '_sha256')
        with executable.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('Matcher executable changed; bind a new configuration: ' + router)


def main(stage):
    p = argparse.ArgumentParser(description=f'Run only {stage}; reuse saved inputs for later stages.')
    p.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml', help='JSON configuration; relative paths are relative to project root')
    p.add_argument('--method', required=True, choices=METHODS if stage != 'evaluate' else None)
    p.add_argument('--out', type=Path, help='New output directory; existing data are not overwritten')
    p.add_argument('--dry-run', action='store_true', help='Print command without reading data or running experiments')
    if stage=='synthesize':
        p.add_argument('--train-only',action='store_true',help='Generate from the configured training split and bind test split lineage')
    if stage != 'synthesize':
        p.add_argument('--router', required=True, choices=('Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP'))
        p.add_argument('--input', type=Path, help='M output directory for routing; saved road file for evaluation')
    if stage == 'evaluate':
        p.add_argument('--representation', choices=('edge-records', 'edge-ids', 'node-pairs'), default='edge-records', help='Actual saved road representation, not inferred from method name')
        p.add_argument('--source-cache', type=Path, help='Source node namespace cache, required for node-pairs')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8'))
    if stage == 'route' and a.router == 'MM2-MDP' and c.get('mm2_resources_status') == 'UNBOUND':
        p.error('MM2 resources are not bound to this population; use its verified public-only configuration')
    if not a.dry_run and c.get('dataset_policy') == 'saved-dp-measurement-public-r-only':
        if stage != 'route':
            p.error('Public-only routing config cannot synthesize or evaluate')
        from preprocess.public_routing_contract import validate
        validate(c, ROOT, a.method, a.input)
    if not a.dry_run and stage == 'route':
        try:
            validate_matcher_binding(c, ROOT, a.router)
        except (ValueError, OSError) as error:
            p.error(str(error))
    if not a.dry_run and stage!='synthesize' and c.get('public_resources_status')=='PENDING':
        p.error('New public routing/metric resources are pending; do not reuse an old graph cache.')
    if (not a.dry_run
            and c.get('road_reference_status') == 'DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING'):
        p.error('Road reference is deprecated: complete full-observation road preprocessing '
                'and bind the new common reference before scoring this batch.')
    if not a.dry_run and c.get('dataset_policy')=='frozen-road-only':
        from preprocess.dataset_contract import validate_dataset
        try:
            identity=validate_dataset(ROOT/c['paths']['prepared'],
                                      public_network=(ROOT/c['paths']['network']).resolve())
            if identity['dataset_id']!=c.get('frozen_dataset_id'):
                raise ValueError('Configuration is not bound to this frozen dataset')
            if c['slots']!=identity['count'] or c['train_slots']!=identity['train_count']:
                raise ValueError('Experiment slot counts must match the prepared population')
            prepared=(ROOT/c['paths']['prepared']).resolve()
            for key,name in [('real','trajectories.pkl'),('metric_real_routes','road_records.pkl.gz'),('train','train.pkl'),('test','test.pkl')]:
                if (ROOT/c['paths'][key]).resolve()!=prepared/name:
                    raise ValueError('Input path is not from the common prepared population: '+key)
        except (ValueError,KeyError,OSError) as error:
            p.error(str(error))
    def path(key):
        return (ROOT / c['paths'][key]).resolve()
    base = path('output') / c['batch']
    measurement = base / 'measurements' / a.method
    prefix = [sys.executable, '-X', 'utf8']
    if stage == 'synthesize':
        out = a.out or (base/'measurements_train'/a.method if a.train_only else measurement)
        bbox=c.get('measurement_bbox',{}).get(a.method,c.get('bbox'))
        if bbox is None:
            # Preserve the original prepared-input interface when no override is declared.
            bbox_record=json.loads((path('prepared')/'bbox.json').read_text(encoding='utf-8-sig'))
            bbox=bbox_record['bbox'] if isinstance(bbox_record,dict) else bbox_record
        if not isinstance(bbox,(list,tuple)) or len(bbox)!=4:
            p.error('Measurement bbox must contain four public bounds')
        if a.train_only:
            command=prefix+[str(ROOT/'tools/generate_train_measurement.py'),'--method',a.method,
                '--data',str(path('train')),'--test',str(path('test')),'--slots',str(c['train_slots']),
                '--epsilon',str(c['epsilon']),'--seed',str(c['seed']),'--bbox',*map(str,bbox),
                '--osm',str(path('osm')),'--legacy',str(path('legacy')),'--out',str(out)]
        else:
            command = prefix + [str(ROOT / 'run.py'), 'synthesize-m', '--dataset', c['dataset'], '--m', a.method,
            '--prepared-data', str(path('prepared')), '--epsilon', str(c['epsilon']), '--seed', str(c['seed']),
            '--public-slot-count', str(c['slots']), '--osm-cache', str(path('osm')), '--out-dir', str(out),
            '--bbox', *map(str,bbox)]
    elif stage == 'route':
        out = a.out or base / 'routes' / a.method / a.router
        existing=c.get('routing_inputs',{}).get(a.method)
        route_input=a.input or ((ROOT/existing).resolve() if existing else measurement)
        command = prefix + [str(ROOT / 'run.py'), 'route-cell', '--dataset', c['dataset'], '--m', a.method,
            '--r', a.router, '--measurement', str(route_input), '--prepared-data', str(path('prepared')),
            '--edge-cache', str(path('edge_cache')), '--public-network', str(path('network')), '--out-dir', str(out)]
        if a.router in ('FMM', 'STMatch'):
            key = a.router.lower()
            command += ['--' + key + '-executable', str(path(key)), '--runtime-dir', str(path('runtime'))]
            if a.router == 'FMM':
                command += ['--ubodt', str(path('ubodt'))]
        if a.router == 'MM2-MDP':
            if 'mm2_edge_cache' in c['paths']:
                command[command.index('--edge-cache')+1] = str(path('mm2_edge_cache'))
            command += ['--mm2-executable', str(path('mm2')), '--mm2-network', str(path('mm2_network'))]
    else:
        if a.router == 'Origin' and a.method in METHODS:
            p.error('Coordinate Origin has no road witness. Use the coordinate evaluator, not road scoring.')
        out = a.out or base / 'scores' / a.method / a.router
        source = resolve_saved_route(c, ROOT, base, a.method, a.router, a.input)
        command = prefix + [str(ROOT / 'tools/evaluate_saved_roads.py'), '--real-routes', str(path('metric_real_routes')),
            '--synthetic-routes', str(source), '--metric-cache', str(path('metric_cache')), '--network', str(path('metric_network')),
            '--method', a.method, '--router', a.router, '--representation', a.representation, '--out', str(out)]
        if a.source_cache:
            command += ['--source-cache', str(a.source_cache)]
        if a.representation == 'node-pairs' and not a.source_cache:
            p.error('--representation node-pairs requires --source-cache')
    if a.dry_run:
        print(json.dumps({'command': command, 'output': str(out)}, ensure_ascii=False, indent=2))
        return
    env = dict(os.environ, PYTHONUTF8='1', DFR_LEGACY_ROOT=str(path('legacy')))
    if stage == 'route':
        env['OMP_NUM_THREADS'] = str(c.get('threads', 1))
    subprocess.run(command, cwd=ROOT, env=env, check=True)



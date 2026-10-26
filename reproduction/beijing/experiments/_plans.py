from pathlib import Path
import sys


def build(experiment, config, args, root):
    def path(key):
        if key == 'metric_network' and key not in config['paths']:
            key = 'network'
        return (root / config['paths'][key]).resolve()
    legacy = path('legacy')
    output = path('output') / config['batch']
    steps = []
    def add(name, script, flags, outputs, inputs=()):
        steps.append({'name': name, 'command': [sys.executable, '-X', 'utf8', str(script), *map(str, flags)],
                      'outputs': list(map(str, outputs)), 'inputs': list(map(str, [script, *inputs])),
                      'dependency_roots': list(map(str, [legacy / 'generation', legacy / 'evaluation', legacy / 'commands', legacy / 'config', root / 'algorithms']))})
    if experiment == 'main':
        methods = [args.method] if args.method else config['methods']
        routers = [args.only_router] if args.only_router else config['routers']
        routers = [r for r in routers if r not in args.exclude_router]
        if not routers:
            raise ValueError('No routers selected')
        if 'MM2-MDP' in routers and config.get('mm2_resources_status') == 'UNBOUND':
            raise ValueError('MM2 resources are not bound to this population; use its verified public-only configuration')
        for m in methods:
            measurement = output / 'measurements' / m
            bbox = config.get('measurement_bbox', {}).get(m, config['bbox'])
            add('generate_' + m, root / 'run.py', ['synthesize-m', '--dataset', config['dataset'], '--m', m, '--prepared-data', path('prepared'), '--epsilon', config['epsilon'], '--seed', config['seed'], '--public-slot-count', config['slots'], '--osm-cache', path('osm'), '--out-dir', measurement, '--bbox', *bbox],
                [measurement / 'measurement.pkl', measurement / 'measurement_manifest.json'], [path('prepared') / 'trajectories.pkl', path('prepared') / 'bbox.json', path('osm')])
            for r in routers:
                target = output / 'routes' / m / r
                cache = path('mm2_edge_cache') if r == 'MM2-MDP' and 'mm2_edge_cache' in config['paths'] else path('edge_cache')
                flags = ['route-cell', '--dataset', config['dataset'], '--m', m, '--r', r, '--measurement', measurement, '--prepared-data', path('prepared'), '--out-dir', target, '--edge-cache', cache, '--public-network', path('network')]
                inputs = [measurement / 'measurement.pkl', cache, path('network')]
                if r in ('FMM', 'STMatch'):
                    key = 'fmm' if r == 'FMM' else 'stmatch'
                    flags += ['--' + key + '-executable', path(key), '--runtime-dir', path('runtime')]
                    inputs += [path(key)]
                    if r == 'FMM':
                        flags += ['--ubodt', path('ubodt')]
                        inputs += [path('ubodt')]
                if r == 'MM2-MDP':
                    flags += ['--mm2-executable', path('mm2'), '--mm2-network', path('mm2_network')]
                    inputs += [path('mm2')]
                route_file = target / ('synthetic_coordinates.pkl' if r == 'Origin' else 'synthetic_routes.pkl.gz')
                add('route_' + m + '_' + r, root / 'run.py', flags, [route_file, target / 'route_manifest.json'], inputs)
                score = output / 'coordinate_scores_audit_v2' / m / r
                add('score_' + m + '_' + r, root / 'evaluate_coordinates.py',
                    ['--config', args.config.resolve(), '--batch', config['batch'], '--method', m, '--router', r,
                     '--input', route_file, '--metric-protocol', 'audit-v2', '--out', score],
                    [score/'metrics.json', score/'manifest.json'],
                    [route_file, path('real'), path('osm'), path('edge_cache'), path('prepared')/'bbox.json', args.config.resolve()])
                if r != 'Origin':
                    road_score = output / 'scores' / m / r
                    add('road_score_' + m + '_' + r, root/'tools/evaluate_saved_roads.py',
                        ['--real-routes', path('metric_real_routes'), '--synthetic-routes', route_file,
                         '--metric-cache', path('metric_cache'), '--network', path('metric_network'),
                         '--method', m, '--router', r, '--representation', 'edge-records', '--out', road_score],
                        [road_score/'metrics.json', road_score/'manifest.json'],
                        [route_file, path('metric_real_routes'), path('metric_cache'), path('metric_network')])
    elif experiment == 'ablation':
        target = output / 'ablation'
        if config.get('dataset_policy') == 'frozen-road-only':
            add('ablation', root/'run_dfr_ablation_frozen.py',
                ['--config', args.config.resolve(), '--out', target],
                [target/'results.csv', target/'manifest.json',
                 *(target/'arms'/(arm+'.pkl.gz') for arm in ('no-endpoint-measurement', 'endpoint-measurement-only', 'no-length-measurement', 'full'))],
                [args.config.resolve(), path('real_routes'), path('real'), path('metric_cache'), path('network')])
            return steps, output, legacy
        add('ablation', legacy / 'evaluation/run_ablation_experiment.py', ['--real-routes', path('real_routes'), '--real-source', path('real'), '--edge-cache', path('source_cache'), '--network', path('network'), '--population', config['population'], '--epsilon-total', config['epsilon'], '--public-slot-count', config['slots'], '--seed', config['seed'], '--length-aware', '--variants', 'no-endpoint-measurement', 'endpoint-measurement-only', 'no-length-measurement', 'full', '--out-dir', target], [target / 'results.csv', target / 'manifest.json', *(target / 'arms' / (arm + '.pkl.gz') for arm in ('no-endpoint-measurement', 'endpoint-measurement-only', 'no-length-measurement', 'full'))], [path('real_routes'), path('real'), path('source_cache'), path('network')])
    elif experiment in ('tstr', 'privacy_attack'):
        releases = config.get('tstr_releases' if experiment == 'tstr' else 'attack_releases', config.get('releases', {}))
        if config.get('frozen_dataset_id') and not releases:
            raise ValueError('Training-only releases are not bound; Register actual train-only releases and lineage before planning TSTR or attacks')
        if experiment == 'privacy_attack' and config.get('attack_resources_status') == 'UNBOUND':
            raise ValueError('Attack inputs are not bound to this population; old population inputs cannot be reused')
        flags = []
        inputs = []
        if experiment == 'tstr':
            for flag, key in [('train-real', 'train'), ('test-real', 'test'), ('split-audit', 'split_audit'), ('osm-cache', 'osm')]:
                flags += ['--' + flag, path(key)]
                inputs += [path(key)]
            flags += ['--require-synthesis-lineage', '--names', *releases]
        else:
            for flag, key in [('members', 'members'), ('nonmembers', 'nonmembers'), ('reference', 'reference'), ('attack-manifest', 'attack_manifest')]:
                flags += ['--' + flag, path(key)]
                inputs += [path(key)]
        for name, item in releases.items():
            source = (root / item['coordinates']).resolve()
            lineage = (root / item['lineage']).resolve()
            flags += ['--synthetic', source] if experiment == 'tstr' else ['--release', f'{name}={source}']
            flags += ['--synthesis-lineage', f'{name}={lineage}']
            inputs += [source, lineage]
        target = output / ('tstr_audit_v2' if experiment == 'tstr' else 'privacy')
        flags += ['--bbox', *config['bbox'], '--seed', config['evaluation_seed'], '--out-dir', target]
        script = 'run_tstr_experiment.py' if experiment == 'tstr' else 'run_privacy_experiment.py'
        if experiment == 'tstr':
            add(experiment, root/'evaluation/audit_v2_runner.py',
                ['--stage','tstr','--legacy',legacy,'--',*flags],
                [target/'results.csv',target/'manifest.json'],inputs)
        else:
            add(experiment, root/'evaluation/run_registered_attacks.py', ['--legacy', legacy, *flags], [target / 'results.csv', target / 'manifest.json'], inputs)
    else:
        raise ValueError(experiment)
    return steps, output, legacy

"""Missing-cell jobs use the saved measurements; no native release is rematched."""
import json
from pathlib import Path
import sys
from _table_catalog import ROOT


def jobs(step, batch, config_path=None):
    batch = Path(batch).resolve()
    config = json.loads(Path(config_path or ROOT / 'configs/beijing.yaml').read_text(encoding='utf-8'))
    def p(key):
        return (ROOT / config['paths'][key]).resolve()
    base = batch / 'routes'
    scores = batch / 'scores'
    output = []
    def add(name, script, flags, artifacts, inputs):
        if any(f.exists() for f in artifacts) and not all(f.is_file() for f in artifacts):
            raise ValueError(f'partial output for {name}; inspect before retrying')
        output.append({'name': name, 'command': [sys.executable, '-X', 'utf8', str(script), *map(str, flags)],
                       'inputs': list(map(str, [script, *inputs])), 'outputs': list(map(str, artifacts))})
    for m in ('PrivTrace', 'DPStd', 'DPTraj-PM', 'SPRT'):
        measurement = batch / 'measurements' / m
        route = base / m / 'MM2-MDP'
        roads = route / 'synthetic_routes.pkl.gz'
        if step == 'route':
            add('MM2_' + m, ROOT / 'run.py', ['route-cell', '--dataset', 'beijing', '--m', m, '--r', 'MM2-MDP', '--measurement', measurement, '--prepared-data', p('prepared'), '--public-network', p('network'), '--edge-cache', p('edge_cache'), '--mm2-executable', p('mm2'), '--mm2-network', p('mm2_network'), '--out-dir', route, '--seed', config['seed']], [roads, route / 'route_manifest.json'], [measurement / 'measurement.pkl', measurement / 'measurement_manifest.json', p('mm2'), p('network'), p('edge_cache')])
        elif step == 'score':
            target = scores / m / 'MM2-MDP'
            add('coordinate_' + m, ROOT / 'run.py', ['evaluate-cell', '--dataset', 'beijing', '--m', m, '--r', 'MM2-MDP', '--synthetic', roads, '--real-reference', p('real'), '--prepared-data', p('prepared'), '--osm-cache', p('osm'), '--edge-cache', p('edge_cache'), '--public-network', p('network'), '--public-slot-count', config['slots'], '--evaluation-seed', config['evaluation_seed'], '--out-dir', route / 'metrics'], [route / 'metrics/metrics.json', route / 'metrics/evaluation_manifest.json'], [roads, p('real'), p('osm')])
            add('road_' + m, ROOT / 'tools/evaluate_saved_roads.py', ['--real-routes', p('metric_real_routes'), '--synthetic-routes', roads, '--representation', 'edge-records', '--metric-cache', p('metric_cache'), '--network', p('metric_network'), '--method', m, '--router', 'MM2-MDP', '--out', target / 'road_metrics'], [target / 'road_metrics/metrics.json', target / 'road_metrics/manifest.json'], [roads, p('metric_real_routes'), p('metric_cache'), p('metric_network')])
            add('physical_' + m, p('legacy') / 'evaluation/run_physical_experiment.py', ['--real-routes', p('metric_real_routes'), '--synthetic-routes', roads, '--edge-cache', p('metric_cache'), '--network', p('metric_network'), '--method', m + ' + MM2-MDP', '--sampling-label', m + ' + MM2-MDP', '--cap-per-stratum', 20, '--out-dir', target / 'physical'], [target / 'physical/results.csv', target / 'physical/manifest.json'], [roads, p('metric_real_routes'), p('metric_cache')])
    return output

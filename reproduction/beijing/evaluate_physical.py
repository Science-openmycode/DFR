"""Score saved road objects with the unchanged full-OD physical evaluator."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from preprocess.dataset_contract import validate_dataset, sha

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--method', required=True)
    p.add_argument('--router', required=True)
    p.add_argument('--input', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--cap-per-stratum', type=int, default=20,
                   help='Preserved deterministic sequence sample cap in each full-OD stratum')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8'))
    def path(key): return (ROOT / c['paths'][key]).resolve()
    identity = validate_dataset(path('prepared'))
    if identity['dataset_id'] != c['frozen_dataset_id']:
        raise ValueError('Wrong frozen reference')
    base = path('output') / c['batch']
    routes = (a.input or base/'routes'/a.method/a.router/'synthetic_routes.pkl.gz').resolve()
    out = (a.out or base/'physical_scores'/a.method/a.router).resolve()
    if out.exists():
        raise FileExistsError(out)
    legacy = path('legacy')/'evaluation'
    sys.path.insert(0, str(legacy))
    from route_metric_core import load_pickle, normalize_routes, valid_routes
    cache = load_pickle(path('metric_cache'))
    real = normalize_routes(load_pickle(path('real_routes')), cache)
    synthetic = normalize_routes(load_pickle(routes), cache)
    if len(real) != c['slots'] or len(valid_routes(real)) != c['slots']:
        raise ValueError('The entire frozen real road population must be valid; no subset filtering')
    if len(synthetic) != c['slots']:
        raise ValueError('Synthetic slots differ from the declared public count')
    command = [sys.executable, '-X', 'utf8', str(legacy/'run_physical_experiment.py'),
               '--real-routes', str(path('real_routes')), '--synthetic-routes', str(routes),
               '--edge-cache', str(path('metric_cache')), '--network', str(path('network')),
               '--method', f'{a.method} + {a.router}', '--sampling-label', f'{a.method} + {a.router}',
               '--cap-per-stratum', str(a.cap_per_stratum), '--out-dir', str(out)]
    start = time.perf_counter()
    env = dict(os.environ, PYTHONUTF8='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    subprocess.run(command, env=env, check=True, cwd=ROOT)
    binding = dict(dataset_id=identity['dataset_id'], real_slots=len(real),
                   synthetic_slots=len(synthetic), valid_real_slots=len(valid_routes(real)),
                   synthetic_sha256=sha(routes), evaluator_sha256=sha(legacy/'run_physical_experiment.py'),
                   command=command, seconds=time.perf_counter()-start,
                   population='full-frozen-road-corpus',
                   sampling='Full OD masses; preserved deterministic within-stratum sequence cap, not a reduced real population')
    (out/'input_binding.json').write_text(json.dumps(binding, indent=2), encoding='utf-8')
    print('DONE_PHYSICAL', a.method, a.router, binding['seconds'], flush=True)


if __name__ == '__main__':
    main()

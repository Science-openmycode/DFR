"""Build the existing FMM lookup table on the explicitly bound public network."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--out-config', type=Path, required=True)
    p.add_argument('--delta-m', type=float, default=1500)
    p.add_argument('--threads', type=int, default=4)
    a = p.parse_args()
    if a.delta_m <= 0 or a.threads < 1:
        p.error('delta-m and threads must be positive')
    c = json.loads(a.config.read_text(encoding='utf-8'))
    if c.get('public_resources_status') != 'EDGE_METRIC_READY':
        p.error('prepare the bound edge/metric resources first')
    if a.out_dir.exists() or a.out_config.exists():
        p.error('output directory and configuration must be new')
    paths = c['paths']
    legacy = (ROOT / paths['legacy']).resolve() / 'evaluation'
    sys.path.insert(0, str(legacy))
    implementation = legacy / 'evaluation/prepare_road_evaluation_network.py'
    spec = importlib.util.spec_from_file_location('bound_ubodt_builder', implementation)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    network = (ROOT / paths['network']).resolve()
    binary = (ROOT / paths['fmm']).resolve().parent / 'ubodt_gen.exe'
    runtime = (ROOT / paths['runtime']).resolve()
    for required in (network, binary, runtime):
        if not required.exists():
            raise FileNotFoundError(required)
    a.out_dir.mkdir(parents=True)
    output = a.out_dir.resolve() / 'ubodt.txt'
    os.environ['OMP_NUM_THREADS'] = str(a.threads)
    started = time.perf_counter()
    print(f'UBODT START: delta={a.delta_m}m threads={a.threads}', flush=True)
    try:
        invocation = module._run_ubodt(network, output, binary, runtime, a.delta_m)
    except Exception as error:
        (a.out_dir / 'failure.json').write_text(json.dumps({'error': str(error), 'elapsed_seconds': time.perf_counter()-started}, indent=2), encoding='utf-8')
        raise
    manifest = {'network': str(network), 'network_sha256': digest(network),
                'output': str(output), 'output_sha256': digest(output),
                'delta_m': a.delta_m, 'threads': a.threads,
                'implementation_sha256': digest(implementation), 'invocation': invocation,
                'elapsed_seconds': time.perf_counter()-started, 'command': sys.argv}
    (a.out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    c['paths']['ubodt'] = str(output)
    c['fmm_resources_status'] = 'READY'
    c['ubodt_manifest'] = str((a.out_dir / 'manifest.json').resolve())
    a.out_config.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()

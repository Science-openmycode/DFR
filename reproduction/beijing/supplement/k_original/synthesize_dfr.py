"""Run the unchanged DFR core on an explicitly approved frozen road dataset."""
import argparse
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from preprocess.dataset_contract import validate_dataset, sha

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--length-aware', action='store_true')
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--endpoint-partition', type=Path,
                   help='hash-bound public map partition; use isolated K-capable core')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8'))
    prepared = (ROOT / c['paths']['prepared']).resolve()
    network = (ROOT/c['paths']['network']).resolve()
    identity = validate_dataset(prepared, public_network=network)
    if identity['dataset_id'] != c.get('frozen_dataset_id') or identity['count'] != c['slots']:
        raise ValueError('DFR must use the same frozen population and public slot count')
    data_manifest = json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    if sha(network) != data_manifest['network_sha256']:
        raise ValueError('DFR public graph differs from the prepared roads')
    legacy = (ROOT/c['paths']['legacy']).resolve()
    sys.path[:0] = [str(legacy/'generation/mtr_dfr/dependencies'),
                   str(legacy/'generation/mtr_dfr/algorithm'), str(legacy/'evaluation')]
    partition_binding = None
    if a.endpoint_partition is None:
        core = importlib.import_module('run_minimal_strong_family')
    else:
        isolated = ROOT/'repairs/k_partition_20261020/algorithm'
        sys.path.insert(0, str(isolated))
        spec = importlib.util.spec_from_file_location(
            'dfr_k_partition_core', isolated/'run_minimal_strong_family.py')
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
    core.EDGE_CACHE = (ROOT/c['paths']['metric_cache']).resolve()
    core.REAL_MATCHED = prepared/'road_records.pkl.gz'
    core.NETWORK = network
    core.POPULATION_SCOPE = 'full-corpus'
    if a.endpoint_partition is not None:
        import gzip
        import pickle
        from endpoint_partition import load_partition
        with gzip.open(core.EDGE_CACHE, 'rb') as handle:
            public_cache = pickle.load(handle)
        _, _, partition_binding = load_partition(
            a.endpoint_partition, public_cache, network=network,
            metric_cache=core.EDGE_CACHE, selected=core.SELECTED_CELLS_PER_ROLE)
    # The frozen core validates every road record against this physical graph.
    # No rematching or new selection is performed by this input adapter.
    out = (a.out or (ROOT/c['paths']['output']/c['batch']/'native/MTR-DFR')).resolve()
    audit = out.with_name(out.name+'.private_audit')
    if out.exists() or audit.exists():
        raise FileExistsError('Choose new native output/audit directories')
    binding = {'classification': 'PRIVATE_FROZEN_DATASET_GENERATION_AUDIT',
               'dataset': identity, 'canonical_manifest_sha256': sha(prepared/'canonical_manifest.json'),
               'input_sha256': sha(prepared/'trajectories.pkl'),
               'real_roads_sha256': sha(core.REAL_MATCHED), 'network_sha256': sha(network),
               'edge_cache_sha256': sha(core.EDGE_CACHE), 'epsilon':c['epsilon'],
               'seed':c['seed'], 'length_aware':a.length_aware,
               'core_source':str(core.__file__), 'core_sha256':sha(core.__file__),
               'command':[sys.executable,*sys.argv]}
    if partition_binding is not None:
        binding['public_endpoint_partition'] = partition_binding
    if a.check_only:
        print(json.dumps({'status':'INPUT_AND_IMPORT_CHECKED_NOT_GENERATED', **binding}, indent=2))
        return
    os.environ['OMP_NUM_THREADS'] = str(c.get('threads',1))
    started = time.perf_counter()
    sys.argv = [core.__file__, '--out-dir',str(out), '--seed',str(c['seed']),
                '--public-slot-count',str(c['slots']), '--epsilon-total',str(c['epsilon'])]
    if a.length_aware:
        sys.argv.append('--length-aware')
    if a.endpoint_partition is not None:
        sys.argv.extend(['--endpoint-partition', str(a.endpoint_partition.resolve())])
    audit.mkdir(parents=True)
    try:
        core.main()
        outputs = {str(f.relative_to(out)): sha(f) for f in out.rglob('*') if f.is_file()}
        binding.update(status='DONE', outputs=outputs)
    except BaseException as error:
        binding.update(status='FAILED', error=str(error))
        raise
    finally:
        binding['elapsed_seconds'] = time.perf_counter()-started
        (audit/'input_lineage.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':'DONE', 'output':str(out), 'elapsed_seconds':binding['elapsed_seconds']}, indent=2))


if __name__ == '__main__':
    main()

"""Run the unchanged DFR core on an explicitly approved frozen road dataset."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time

from preprocess.dataset_contract import validate_dataset, sha

ROOT = Path(__file__).resolve().parent


def validate_endpoint_support(cache_path):
    """Check the unchanged core's fixed public endpoint domain before sampling."""
    import gzip
    import pickle
    with gzip.open(cache_path,'rb') as stream:cache=pickle.load(stream)
    fine=cache['labels384'];coarse=cache['labels24']
    for role in (0,1):
        nodes={edge[role] for edge in cache['edge_nodes'].values()}
        supported={int(fine[node]) for node in nodes if node in fine}
        missing=set(range(384))-supported
        if missing:
            raise ValueError(f'DFR requires all 384 public endpoint cells for role {role}; missing {len(missing)} cells')
        if any(node not in fine or node not in coarse or not 0<=int(fine[node])<384
               or not 0<=int(coarse[node])<24 for node in nodes):
            raise ValueError('Invalid DFR public endpoint region binding')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--length-aware', action='store_true')
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8'))
    prepared = (ROOT / c['paths']['prepared']).resolve()
    identity = validate_dataset(prepared)
    if identity['dataset_id'] != c.get('frozen_dataset_id') or identity['count'] != c['slots']:
        raise ValueError('DFR must use the same frozen population and public slot count')
    data_manifest = json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    network = (ROOT/c['paths']['network']).resolve()
    if sha(network) != data_manifest['network_sha256']:
        raise ValueError('DFR public graph differs from the prepared roads')
    legacy = (ROOT/c['paths']['legacy']).resolve()
    sys.path[:0] = [str(legacy/'generation/mtr_dfr/dependencies'),
                   str(legacy/'generation/mtr_dfr/algorithm'), str(legacy/'evaluation')]
    core = importlib.import_module('run_minimal_strong_family')
    core.EDGE_CACHE = (ROOT/c['paths']['metric_cache']).resolve()
    validate_endpoint_support(core.EDGE_CACHE)
    core.REAL_MATCHED = prepared/'road_records.pkl.gz'
    core.NETWORK = network
    core.POPULATION_SCOPE = 'full-corpus'
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
    if a.check_only:
        print(json.dumps({'status':'INPUT_AND_IMPORT_CHECKED_NOT_GENERATED', **binding}, indent=2))
        return
    os.environ['OMP_NUM_THREADS'] = str(c.get('threads',1))
    started = time.perf_counter()
    sys.argv = [core.__file__, '--out-dir',str(out), '--seed',str(c['seed']),
                '--public-slot-count',str(c['slots']), '--epsilon-total',str(c['epsilon'])]
    if a.length_aware:
        sys.argv.append('--length-aware')
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

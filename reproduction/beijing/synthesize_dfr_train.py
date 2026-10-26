"""Train-only DFR release using the same immutable prepared split and DFR core."""
import argparse
import gzip
import importlib
import json
from pathlib import Path
import pickle
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
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8'))
    def path(key): return (ROOT/c['paths'][key]).resolve()
    prepared = path('prepared')
    identity = validate_dataset(prepared)
    if identity['dataset_id'] != c['frozen_dataset_id']:
        raise ValueError('Wrong frozen dataset')
    audit = json.loads(path('split_audit').read_text(encoding='utf-8'))
    if audit['status'] != 'passed' or not audit['all_source_indices_used_once']:
        raise ValueError('No verified disjoint split')
    if audit['train_sha256'] != sha(path('train')) or audit['test_sha256'] != sha(path('test')):
        raise ValueError('Split input changed')
    train = json.loads((prepared/'train_split.json').read_text(encoding='utf-8'))['indices']
    test = json.loads((prepared/'test_split.json').read_text(encoding='utf-8'))['indices']
    if len(train) != c['train_slots'] or set(train) & set(test):
        raise ValueError('Invalid frozen training indices')
    out = (a.out or path('output')/c['batch']/'native_train/MTR-DFR').resolve()
    if out.exists():
        raise FileExistsError(out)
    if sha(path('network')) != json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))['network_sha256']:
        raise ValueError('Different public graph')
    legacy = path('legacy')
    sys.path[:0] = [str(legacy/'generation/mtr_dfr/dependencies'),
                   str(legacy/'generation/mtr_dfr/algorithm'),str(legacy/'evaluation')]
    core = importlib.import_module('run_minimal_strong_family')
    print('VERIFIED_TRAIN_ONLY_DFR_INPUT',len(train),flush=True)
    if a.check_only:
        return
    out.mkdir(parents=True)
    inputs = out/'private_inputs'
    inputs.mkdir()
    # This is an index selection of the frozen road input, never another matcher.
    # Test records are not passed to the generator or used for any parameter choice.
    with gzip.open(prepared/'road_records.pkl.gz','rb') as f:
        records = pickle.load(f)
    selected = [records[i] for i in train]
    del records
    roads = inputs/'train_road_records.pkl.gz'
    with gzip.open(roads,'wb') as f:
        pickle.dump(selected,f,pickle.HIGHEST_PROTOCOL)
    del selected
    core.REAL_MATCHED = roads
    core.EDGE_CACHE = path('metric_cache')
    core.NETWORK = path('network')
    core.POPULATION_SCOPE = 'full-corpus'
    sys.argv = [core.__file__,'--out-dir',str(out/'release'),'--seed',str(c['seed']),
                '--public-slot-count',str(c['train_slots']),'--epsilon-total',str(c['epsilon'])]
    if a.length_aware:
        sys.argv.append('--length-aware')
    started = time.perf_counter()
    record = dict(schema='executed_train_only_generation_v1',status='running',
                  generator='Unchanged MTR-DFR core',input_policy='train_only_explicit_generator_input',
                  train_sha256=sha(path('train')),test_sha256=sha(path('test')),
                  train_roads_sha256=sha(roads),source_sha256=sha(core.__file__),
                  adapter_sha256=sha(Path(__file__)),dataset_id=identity['dataset_id'],
                  public_slot_count=c['train_slots'],epsilon=c['epsilon'],outputs={})
    lineage = out/'lineage.json'
    try:
        core.main()
        for file in (out/'release').rglob('*'):
            if file.is_file(): record['outputs'][str(file.relative_to(out))] = sha(file)
        record.update(status='passed',returncode=0)
    except BaseException as error:
        record.update(status='failed',returncode=1,error=str(error))
        raise
    finally:
        record['seconds'] = time.perf_counter()-started
        lineage.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('DONE_TRAIN_ONLY_DFR',record['seconds'],flush=True)


if __name__ == '__main__':
    main()

"""Select training slots from frozen per-record public map matching; no rerouting.

Private research preprocessing only. Requires a passed indexed-coordinate split
audit. The source matching must be recordwise on a fixed public graph; selection
does not make a corpus-adaptive matcher train-only. Preserves failed slots.
"""
import argparse
import gzip
import hashlib
import json
import pickle
import time
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def select(*, full_routes, matching_manifest, split_manifest, split_audit, train_real, out_dir):
    start = time.perf_counter()
    paths = {name: Path(value).resolve() for name, value in locals().copy().items() if name != 'start'}
    output = paths.pop('out_dir')
    if output.exists():
        raise FileExistsError(output)
    bindings = {name: {'path': str(path), 'sha256': sha(path)} for name, path in paths.items()}
    match, split, audit = [json.loads(paths[k].read_text(encoding='utf-8-sig'))
                           for k in ('matching_manifest', 'split_manifest', 'split_audit')]
    if (audit.get('schema') != 'verified_disjoint_split_v1' or audit.get('status') != 'passed'
            or audit.get('all_source_indices_used_once') is not True
            or audit.get('manifest_sha256') != bindings['split_manifest']['sha256']
            or audit.get('train_sha256') != bindings['train_real']['sha256']):
        raise ValueError('split audit does not bind the supplied training file and indices')
    if (match.get('classification') != 'COMMON_MAP_MATCH_CACHE_NO_SYNTHESIS'
            or match.get('input_sha256') != audit.get('full_sha256')
            or match.get('output_sha256') != bindings['full_routes']['sha256']
            or not match.get('network_sha256')):
        raise ValueError('full matching source/output/network binding mismatch')
    with gzip.open(paths['full_routes'], 'rb') as handle:
        rows = pickle.load(handle)
    train, test = split['train_indices'], split['test_indices']
    n = len(rows)
    if (match.get('record_count') != n or split.get('total_count') != n
            or not train or not test or len(train) != audit.get('train_count')
            or len(test) != audit.get('test_count')
            or any(type(i) is not int or not 0 <= i < n for i in train + test)
            or len(train + test) != n or len(set(train + test)) != n):
        raise ValueError('invalid or overlapping source slot indices')
    selected = [rows[i] for i in train]
    output.mkdir(parents=True, exist_ok=False)
    route_file = output / 'train_routes.pkl.gz'
    with gzip.open(route_file, 'wb') as handle:
        pickle.dump(selected, handle, protocol=pickle.HIGHEST_PROTOCOL)
    record = {
        'classification': 'COMMON_MAP_MATCH_CACHE_NO_SYNTHESIS',
        'evidence_scope': 'PRIVATE_RESEARCH_PREPROCESSING_NOT_A_DP_RELEASE',
        'derivation': 'index selection of frozen recordwise public matching, not a fresh matcher invocation',
        'recordwise_precondition': 'fixed public graph and per-record matching; not corpus-adaptive',
        'input': str(paths['train_real']), 'input_sha256': bindings['train_real']['sha256'],
        'output': str(route_file), 'output_sha256': sha(route_file), 'record_count': len(selected),
        'network_sha256': match['network_sha256'], 'parameters': match.get('parameters', {}),
        'bindings': bindings, 'selected_source_indices': train,
        'rematched': False, 'failed_slots_preserved': True,
        'elapsed_seconds': time.perf_counter() - start,
    }
    (output / 'train_routes.manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('full-routes', 'matching-manifest', 'split-manifest', 'split-audit', 'train-real', 'out-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = select(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ('record_count', 'output', 'output_sha256', 'elapsed_seconds')}, indent=2))


if __name__ == '__main__':
    main()

"""Fail-closed identity checks for the only approved experiment population."""
import hashlib
import json
from pathlib import Path

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def validate_dataset(directory, public_network=None):
    root=Path(directory).resolve()
    manifest=root/'canonical_manifest.json'
    meta=json.loads(manifest.read_text(encoding='utf-8'))
    if meta.get('schema')!='frozen-road-dataset-v1' or meta.get('status')!='FROZEN':
        raise ValueError('Only an approved frozen road dataset can be used')
    n=meta['trajectory_count']
    if not isinstance(n,int) or n<2 or meta['train_count']+meta['test_count']!=n:
        raise ValueError('Inconsistent population counts')
    required={'trajectories.pkl','trajectories.pkl.gz','road_records.pkl.gz','train.pkl','test.pkl',
              'train_split.json','test_split.json','source_indices.json','bbox.json'}
    if not required.issubset(meta.get('artifacts',{})):raise ValueError('Missing dataset artifacts')
    for name,digest in meta['artifacts'].items():
        path=(root/name).resolve()
        if path.parent!=root:raise ValueError('Artifact path escapes dataset')
        if sha(path)!=digest:raise ValueError('Dataset artifact changed: '+name)
    # A migration may rebind the path, never the graph bytes or dataset identity.
    # Keep the canonical manifest bytes (and dataset identity) unchanged on migration.
    # A separately recorded relative location is usable only after the original
    # graph and all sidecar hashes below have been checked.
    location = root/'network_location.json'
    if public_network is not None:
        network = Path(public_network)
    elif location.exists():
        relative = json.loads(location.read_text(encoding='utf-8'))['relative_path']
        if Path(relative).is_absolute():
            raise ValueError('Migrated network location must be relative')
        network = (root/relative).resolve()
    else:
        network = Path(meta['network'])
    if sha(network)!=meta['network_sha256']:raise ValueError('Public road graph changed')
    for name,digest in meta.get('network_sidecars',{}).items():
        if sha(network.with_suffix(name))!=digest:raise ValueError('Public network sidecar changed')
    ids=json.loads((root/'source_indices.json').read_text(encoding='utf-8'))
    train=json.loads((root/'train_split.json').read_text(encoding='utf-8'))['indices']
    test=json.loads((root/'test_split.json').read_text(encoding='utf-8'))['indices']
    if len(ids)!=n or len(set(ids))!=n:raise ValueError('Source identity mismatch')
    if len(train)!=meta['train_count'] or len(test)!=meta['test_count'] or sorted(train+test)!=list(range(n)):
        raise ValueError('Training/test split overlaps or misses records')
    return dict(dataset_id=sha(manifest),count=n,train_count=len(train),test_count=len(test))

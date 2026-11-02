"""Read, never rewrite, pre-role-schema road review evidence."""
import csv
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import numpy as np


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    with (gzip.open(path, 'rb') if str(path).endswith('.gz') else open(path, 'rb')) as f:
        return pickle.load(f)


def frozen_coordinates(directory):
    manifest=json.loads((directory/'dataset/canonical_manifest.json').read_text(encoding='utf-8'))
    path=directory/'dataset/trajectories.pkl.gz'
    if digest(path)!=manifest['artifacts']['trajectories.pkl.gz']:
        raise ValueError('Historical frozen coordinates changed')
    return load(path)


def preserve_frozen_projection(recomputed, frozen):
    """Keep the approved representation, only after a machine-roundoff guard."""
    a=np.asarray(recomputed,dtype=float);b=np.asarray(frozen,dtype=float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Historical projection shape/values changed')
    delta=np.abs(a-b)
    if np.any(delta>8*np.spacing(np.abs(b))):
        raise ValueError('Reprojection differs beyond floating-point roundoff')
    return b,float(delta.max(initial=0))


def validate_historical_review(directory, previous, args, raw, timestamps, bindings):
    """Prove semantic equality after relocation/recompression, with original proofs."""
    argv = previous['command']
    def option(name):
        if argv.count('--'+name) != 1:
            raise ValueError('Historical command lacks unique '+name)
        return argv[argv.index('--'+name)+1]
    if option('dataset') != args.dataset:
        raise ValueError('Historical city differs')
    start = argv.index('--bbox')+1
    if list(map(float, argv[start:start+4])) != args.bbox:
        raise ValueError('Historical public bounds differ')
    checked = {}
    for role in ('source', 'network', 'matcher-module', 'timestamps', 'timestamp-bindings'):
        original = option(role)
        expected = previous['inputs'].get(original)
        if not expected:
            raise ValueError('Historical input has no binding: '+role)
        path = Path(original)
        if not path.is_file():
            # Portable copies retain their historical hash; no metadata is rewritten.
            suffix = '.pkl.gz' if original.endswith('.pkl.gz') else Path(original).suffix
            path = directory/'legacy_inputs'/(role+suffix)
        if digest(path) != expected:
            raise ValueError('Historical input changed: '+role)
        checked[role] = path
    for role in ('network', 'matcher-module'):
        current = args.network if role == 'network' else args.matcher_module
        if digest(current) != digest(checked[role]):
            raise ValueError('Historical resource differs: '+role)
    for role, current in (('source', raw), ('timestamps', timestamps)):
        old = load(checked[role])
        if len(old) != len(current) or any(not np.array_equal(a,b) for a,b in zip(old,current)):
            raise ValueError('Historical values differ: '+role)
        del old
    with checked['timestamp-bindings'].open(encoding='utf-8-sig', newline='') as f:
        old_bindings = list(csv.DictReader(f))
    def normalized(rows):
        result=[]
        for row in rows:
            row=dict(row)
            if 'plt_file' in row:
                parts=row['plt_file'].replace('\\','/').split('/')
                tail=parts[-3:]
                if len(tail)!=3 or tail[1]!='Trajectory' or not tail[0].isdigit() or not tail[2].endswith('.plt'):
                    raise ValueError('Invalid historical PLT source identity')
                row['plt_file']='/'.join(tail)
            result.append(row)
        return result
    if normalized(old_bindings) != normalized(bindings):
        raise ValueError('Historical source bindings differ')
    manifest_path = directory/'dataset/canonical_manifest.json'
    if digest(manifest_path) != previous['dataset_manifest_sha256']:
        raise ValueError('Historical frozen manifest changed')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if digest(directory/'selection_review.json') != manifest['selection_review_sha256']:
        raise ValueError('Historical accepted selection changed')
    frozen = directory/'dataset/road_records.pkl.gz'
    if digest(frozen) != manifest['artifacts']['road_records.pkl.gz']:
        raise ValueError('Historical accepted road records changed')
    records = load(directory/'reviewed_records.pkl.gz')
    if [r for r in records if r['accepted']] != load(frozen):
        raise ValueError('Historical reviewed roads differ from accepted frozen roads')
    return records, dict(schema='historical-review-semantic-import-v1',
        original_manifest_sha256=digest(manifest_path), original_run_sha256=digest(directory/'preprocessing_run.json'),
        checked_source_records=len(raw), coordinates_equal=True, observation_times_equal=True,
        source_bindings_equal=True, accepted_road_records_equal=True,
        matching_executed=False)

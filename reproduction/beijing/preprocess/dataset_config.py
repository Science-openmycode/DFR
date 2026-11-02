"""Resolve city data through one portable bundle; preserve legacy configs exactly."""
import json
from pathlib import Path

from .dataset_contract import sha


def load_config(filename, legacy_root):
    filename = Path(filename).resolve()
    config = json.loads(filename.read_text(encoding='utf-8-sig'))
    if 'dataset_bundle' not in config:
        return config  # Historical paths remain relative to the original entry root.
    bundle_path = (filename.parent / config['dataset_bundle']).resolve()
    bundle = json.loads(bundle_path.read_text(encoding='utf-8-sig'))
    if bundle.get('schema') != 'road-experiment-bundle-v1':
        raise ValueError('Unsupported dataset bundle schema')
    paths = bundle.get('paths', {})
    required = {'prepared', 'network'}
    if not required.issubset(paths):
        raise ValueError('Bundle requires prepared and network paths')
    resolved = {}
    for key, value in paths.items():
        if not isinstance(value, str) or not value:
            raise ValueError('Invalid bundle path: '+key)
        resolved[key] = str((bundle_path.parent / value).resolve())
    prepared = Path(resolved['prepared'])
    canonical = prepared / 'canonical_manifest.json'
    meta = json.loads(canonical.read_text(encoding='utf-8-sig'))
    if meta.get('schema') != 'frozen-road-dataset-v1' or meta.get('status') != 'FROZEN':
        raise ValueError('Bundle must reference a prepared frozen dataset')
    dataset = bundle.get('dataset')
    if not isinstance(dataset, str) or not dataset or meta.get('dataset', dataset) != dataset:
        raise ValueError('Bundle city differs from prepared data')
    counts = [meta.get(k) for k in ('trajectory_count', 'train_count', 'test_count')]
    if any(type(n) is not int or n < 1 for n in counts) or counts[1]+counts[2] != counts[0]:
        raise ValueError('Invalid bundle population counts')
    additions = dict(prepared=resolved['prepared'], real=str(prepared/'trajectories.pkl'),
                     metric_network=resolved['network'],
                     real_routes=str(prepared/'road_records.pkl.gz'),
                     metric_real_routes=str(prepared/'road_records.pkl.gz'),
                     train=str(prepared/'train.pkl'), test=str(prepared/'test.pkl'))
    additions.update(resolved)
    old_paths = config.setdefault('paths', {})
    for key, value in additions.items():
        if key in old_paths and (Path(legacy_root)/old_paths[key]).resolve() != Path(value):
            raise ValueError('Conflicting data path in experiment config: '+key)
        old_paths[key] = value
    values = dict(dataset=dataset, slots=counts[0], train_slots=counts[1], test_slots=counts[2],
                  frozen_dataset_id=sha(canonical))
    for key, value in values.items():
        if key in config and config[key] != value:
            raise ValueError('Conflicting dataset field: '+key)
        config[key] = value
    for key in ('bbox', 'routing_crs'):
        if key in bundle:
            if key in config and config[key] != bundle[key]:
                raise ValueError('Conflicting public resource field: '+key)
            config[key] = bundle[key]
    if 'dfr_author_roads' in bundle:
        value=dict(bundle['dfr_author_roads'])
        value['manifest']=str((bundle_path.parent/value['manifest']).resolve())
        if 'dfr_author_roads' in config:
            original=dict(config['dfr_author_roads'])
            original['manifest']=str((Path(legacy_root)/original['manifest']).resolve())
            if original!=value:raise ValueError('Conflicting public author-road binding')
        config['dfr_author_roads']=value
    return config

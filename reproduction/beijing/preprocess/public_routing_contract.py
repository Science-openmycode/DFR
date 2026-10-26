"""Verify saved M/public-resource bindings without opening private trajectories."""
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate(config, root, method, override=None):
    if config.get('dataset_policy') != 'saved-dp-measurement-public-r-only':
        raise ValueError('Wrong public-only R policy')
    contract = config['public_routing_contract']
    if (contract.get('schema') != 'verified-measurement-public-routing-v1'
            or contract.get('dataset_id') != config['frozen_dataset_id']
            or contract.get('slots') != config['slots']
            or any(key in config['paths'] for key in ('real','train','test','real_routes','prepared_private'))):
        raise ValueError('Public routing contract mismatched or contains private input paths')
    binding = contract['measurements'][method]
    directory = Path(override) if override else root / config['routing_inputs'][method]
    directory = directory.resolve()
    for name in ('measurement.pkl','measurement_manifest.json'):
        if sha(directory/name) != binding[name]:
            raise ValueError('Saved M changed: ' + name)
    meta = json.loads((directory/'measurement_manifest.json').read_text(encoding='utf-8'))
    input_sha = meta.get('input_sha256', meta.get('prepared_sha256'))
    count = meta.get('public_slot_count')
    if input_sha is None or count is None:
        proof_path = directory/'lineage.json'
        if sha(proof_path) != binding.get('lineage.json'):
            raise ValueError('Legacy train M requires bound execution lineage')
        proof = json.loads(proof_path.read_text(encoding='utf-8'))
        if (proof.get('schema') != 'executed_train_only_generation_v1'
                or proof.get('status') != 'passed' or proof.get('returncode') != 0
                or proof.get('input_policy') != 'train_only_explicit_generator_input'
                or proof.get('outputs',{}).get('measurement.pkl') != binding['measurement.pkl']):
            raise ValueError('Incomplete legacy train execution proof')
        input_sha, count = proof['train_sha256'], binding['records']
    if (meta.get('status', 'VALID' if meta.get('kind')=='measurement' else None) != 'VALID' or meta.get('M') != method
            or count != config['slots']
            or input_sha != contract['population_input_sha256']
            or meta.get('epsilon') != config['epsilon']
            or meta.get('outputs',{}).get('measurement.pkl') != binding['measurement.pkl']):
        raise ValueError('M provenance does not match frozen population')
    for name, expected in contract['public_files'].items():
        if sha(root/name) != expected:
            raise ValueError('Public routing resource changed: ' + name)
    return directory

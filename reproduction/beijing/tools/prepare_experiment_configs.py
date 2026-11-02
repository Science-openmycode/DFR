"""Bind checked-in experiment configurations to prepared data; never write commands.

README command documents are repository files. This step writes JSON inputs only,
preserving each experiment's algorithm options and the documented output layout.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocess.dataset_contract import validate_dataset
DOCS = ['reproduction_checked_20261024/COMMANDS_CN.md', 'REPRODUCE_DFR_LENGTH_20261024_CN.md',
        'REPRODUCE_NATIVE_BASELINES_20261024_CN.md', 'REPRODUCE_NATIVE_SCORES_20261024_CN.md',
        'REPRODUCE_NEW_MATRIX_CN.md',
        'supplement/sweeps/k_COMMANDS_CN.md', 'supplement/sweeps/budget_COMMANDS_CN.md',
        'supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md']
IDENTITY = ['dataset', 'dataset_policy', 'frozen_dataset_id', 'slots', 'train_slots', 'test_slots',
            'population', 'population_status', 'bbox', 'public_resources_status', 'road_reference_status',
            'fmm_resources_status', 'mm2_resources_status', 'matcher_compatibility',
            'dataset_bundle', 'routing_crs', 'mm2_city_binding', 'dfr_author_roads']


def prepare(config, out, root=ROOT):
    root = Path(root).resolve()
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Choose a new configuration directory: '+str(out))
    if not out.is_relative_to(root):
        raise ValueError('Configuration directory must be inside this checkout')
    prefix = out.relative_to(root).as_posix()
    # A user may choose another directory and update the existing --config
    # references consistently. No generated runbook is needed for renaming.
    source = Path(config).resolve()
    base = json.loads(source.read_text(encoding='utf-8-sig'))
    if base.get('dataset_bundle'):
        base['dataset_bundle'] = str((source.parent/base['dataset_bundle']).resolve())
    identity = validate_dataset(root/base['paths']['prepared'], root/base['paths']['network'])
    if identity['dataset_id'] != base['frozen_dataset_id']:
        raise ValueError('Prepared dataset differs from selected configuration')
    templates = set()
    for doc in [*DOCS, 'SUPPLEMENT_COMMANDS_CN.md']:
        text = (root/doc).read_text(encoding='utf-8-sig')
        templates.update(re.findall(r'--config configs/experiments/([\w./-]+\.json)', text))
        if prefix != 'configs/experiments':
            templates.update(re.findall(r'--config '+re.escape(prefix)+r'/([\w./-]+\.json)', text))
    if not templates:
        raise ValueError('No checked-in experiment configurations referenced')
    # Produced by prepare_attack_inputs.py after the training releases exist.
    templates.discard('attack_ready.json')
    payloads = {}
    for name in sorted(templates):
        template = root/name
        if not template.is_file():
            raise FileNotFoundError(template)
        value = json.loads(template.read_text(encoding='utf-8-sig'))
        for key in IDENTITY:
            if key in base:
                value[key] = copy.deepcopy(base[key])
        if base['dataset'] != 'beijing' and 'measurement_bbox' in value:
            value['measurement_bbox'] = {key:copy.deepcopy(base['bbox']) for key in value['measurement_bbox']}
        output = value.get('paths', {}).get('output', 'results')
        value.setdefault('paths', {}).update(copy.deepcopy(base['paths']))
        if 'mm2_edge_cache' in value['paths']:
            value['paths']['mm2_edge_cache'] = base['paths']['metric_cache']
        # --out in the existing command documents controls the result folder.
        # Do not silently add a second batch prefix to that folder.
        value['paths']['output'] = output
        for key in ('routing_inputs', 'releases', 'train_releases', 'attack_releases', 'saved_route_inputs'):
            value[key] = {}
        value['attack_resources_status'] = 'UNBOUND'
        payloads[name] = value
    plan = json.loads((root/'supplement/sweeps/plan.json').read_text(encoding='utf-8-sig'))
    for cell in plan['cells']:
        cell['config'] = prefix+'/'+cell['config']
        for step in cell.get('steps', []):
            step['command'] = re.sub(r'--config ([\w./-]+\.json)', r'--config '+prefix+r'/\1', step['command'])
    # Release paths are exactly those in the checked-in command documents.
    releases = {}
    for method in ('SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd'):
        parent = 'results/reproduction_checked_20261024'
        for router in ('Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP'):
            coordinates = (f'{parent}/measurements_train/{method}/measurement.pkl' if router == 'Origin'
                           else f'{parent}/coordinate_views_train/{method}/{router}/coordinates.pkl')
            releases[method+' + '+router] = dict(coordinates=coordinates, lineage=f'{parent}/measurements_train/{method}/lineage.json')
    native = 'results/reproduction_native_20261024/train'
    releases['DPMM'] = dict(coordinates=f'{native}/DPMM_view/coordinates.pkl', lineage=f'{native}/DPMM_view/lineage.json')
    releases['MTNet'] = dict(coordinates=f'{native}/MTNet_view/coordinates.pkl', lineage=f'{native}/MTNet_deployment/lineage.json')
    dfr = 'results/reproduction_dfr_length_20261024'
    releases['MTR-DFR'] = dict(coordinates=f'{dfr}/train_view/MTR-DFR/coordinates.pkl', lineage=f'{dfr}/native_train/MTR-DFR/lineage.json')
    out.mkdir(parents=True)
    for name, value in payloads.items():
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, value in [('sweeps_plan.json', plan), ('training_releases.json', releases)]:
        (out/name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    result = dict(status='CONFIGURATIONS_PREPARED_NOT_EXECUTED', dataset=base['dataset'],
                  dataset_id=identity['dataset_id'], configurations=len(payloads),
                  command_documents_written=0, source_config=str(source))
    (out/'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.config, a.out), indent=2))


if __name__ == '__main__':
    main()

"""Explicit sources for the current Beijing batch; no recursive best-file search."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.table_collection import sha256

COORD = {'grid_density_jsd': 'Grid', 'trip_error': 'Trip', 'path_length_jsd': 'Len',
         'directed_road_validity': 'DirValid', 'witness_valid': 'WitnessValid'}
ROAD = ['RoadYield', 'DemandFid', 'BTF', 'RC-CPC', 'EdgeCPC', 'TurnCPC', 'FamilyCPC',
        'EdgeRecall', 'EdgePrecision', 'EdgeF1', 'TurnRecall', 'TurnPrecision', 'TurnF1',
        'EdgeIoU', 'TurnIoU', 'BranchCPC', 'ExitAcc', 'ODPF96', 'ODPF384',
        'TotalLengthRetention', 'BackboneLengthRetention', 'ClosedLengthRetention',
        'ClosedSegmentRetention', 'RepeatedEdgeRetention']
PHYSICAL = ['RoadRecovery', 'RoadSupport', 'TurnRecovery', 'TurnSupport', 'BackboneRecovery', 'BackboneSupport']
ROAD_TASKS = {name: name for name in ('RC-NDCG', 'NextRoadAcc', 'NextRoadNLL')}
TASKS = {'Next-cell Hit@1': 'NextCellHit1', 'Next-cell MRR': 'NextCellMRR',
         'Destination Hit@5': 'DestinationHit5', 'Destination MRR': 'DestinationMRR',
         'Road continuation Hit@1': 'RoadContinuationHit1', 'Road continuation MRR': 'RoadContinuationMRR',
         'Route retrieval NDCG@5': 'RouteRetrievalNDCG5'}


def prepare(batch, config_path=None):
    batch = Path(batch).resolve()
    config = json.loads(Path(config_path or ROOT / 'configs/beijing.yaml').read_text(encoding='utf-8'))
    base = batch / 'coordinate_scores_audit_v2'
    scores = batch / 'scores'
    follow = batch / 'simple_followup_20261013'
    sources, missing = [], []
    cache = {}
    def current_directory(*candidates):
        present = [p for p in candidates if (p / 'manifest.json').is_file()]
        if len(present) > 1:
            raise ValueError(f'ambiguous current sources; use explicit table_sources: {present}')
        return present[0] if present else candidates[0]
    def pin(path, expected=None):
        # Relocate by content identity, never by a same-name file or by editing
        # the original manifest's recorded execution paths.
        location = config.get('table_artifact_locations', {}).get(expected)
        if location is not None:
            path = ROOT / location
        path = Path(path).resolve()
        key = str(path)
        if key not in cache:
            cache[key] = sha256(path)
        if expected and cache[key] != expected:
            raise ValueError(f'published manifest hash mismatch: {path}')
        return dict(path=key, sha256=cache[key])
    def add(row, path, manifest, columns, protocol, kind='json', key='', select=None, scope='full'):
        if not path.is_file() or not manifest.is_file():
            missing.append({'row': row, 'columns': list(columns.values()), 'path': str(path)})
            return
        meta = json.loads(manifest.read_text(encoding='utf-8-sig'))
        if protocol == 'coordinate-evaluator-v1':
            if meta.get('schema_version') != 1 or meta.get('kind') != 'evaluation':
                raise ValueError(f'unsupported coordinate evaluation schema: {manifest}')
        elif protocol == 'metric-audit-v2-20261016':
            if meta.get('metric_revision', {}).get('protocol') != protocol:
                raise ValueError(f'source protocol mismatch: {manifest}')
            if meta.get('inputs', {}).get('real', {}).get('count') != config['slots']:
                raise ValueError(f'coordinate population mismatch: {manifest}')
        elif protocol == 'retrospective-road-tasks-v1':
            if (meta.get('dataset_id') != config['frozen_dataset_id'] or
                    meta.get('real_slots') != config['slots'] or
                    meta.get('synthetic_slots') != config['slots']):
                raise ValueError(f'road-task population mismatch: {manifest}')
            if 'evaluate_road_tasks.py' not in meta.get('command', []):
                raise ValueError(f'road-task entry not evidenced: {manifest}')
        elif meta.get('protocol', meta.get('schema_version')) != protocol:
            raise ValueError(f'source protocol mismatch: {manifest}')
        bindings = [pin(manifest)]
        input_meta = meta
        if manifest.name == 'evaluation_manifest.json':
            inner = manifest.with_name('manifest.json')
            bindings.append(pin(inner, meta['outputs']['manifest.json']))
            input_meta = json.loads(inner.read_text(encoding='utf-8-sig'))
        expected = meta.get('outputs', {}).get(path.name)
        if isinstance(expected, dict):
            expected = expected.get('sha256')
        if not expected:
            expected = next((v.get('sha256') for v in meta.get('outputs', {}).values() if isinstance(v, dict) and Path(v.get('path', '')).name == path.name), None)
        if kind == 'csv':
            expected = expected or meta.get('results_sha256')
        if protocol == 'retrospective-road-tasks-v1':
            expected = meta.get('result_sha256')
        if not expected:
            raise ValueError(f'missing source output hash: {manifest} -> {path.name}')
        for label, value in input_meta.get('inputs', {}).items():
            if protocol == 'retrospective-road-tasks-v1' and isinstance(value, str):
                bindings.append(pin(label, value))
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, dict) and 'path' in item and 'sha256' in item:
                    bindings.append(pin(item['path'], item['sha256']))
        if 'metric_core' in meta:
            bindings.append(pin(meta['metric_core']['path'], meta['metric_core']['sha256']))
        if protocol == 'full_od_ordered_physical_mass_v1':
            method, router = manifest.parent.parent.name, manifest.parent.name
            road_manifest = current_directory(scores / method / router,
                batch / 'road_scores' / method / router) / 'manifest.json'
            bindings.append(pin(road_manifest))
            road_inputs = json.loads(road_manifest.read_text(encoding='utf-8'))['inputs']
            for label, expected_hash in meta['inputs_sha256'].items():
                identity = road_inputs['metric_cache' if label == 'edge_cache' else label]
                bindings.append(pin(identity['path'], expected_hash))
        if scope == 'tstr' and 'scoring_inputs_sha256' in meta:
            if not meta.get('synthesis_lineage_verified') or not meta.get('disjoint_split_verified'):
                raise ValueError('TSTR source lacks verified lineage/split')
            split = meta['split_binding']
            if (split['disjoint_split']['train_count'], split['disjoint_split']['test_count']) != (12584, 3146):
                raise ValueError('TSTR split population mismatch')
            required = {split['train_sha256'], split['test_sha256'],
                        split['disjoint_split']['record_sha256']}
            name = select['Pipeline']
            if name != 'Real-train':
                required.update((split['synthetic'][name],
                                 split['synthesis_lineage'][name]['record_sha256']))
            recorded = meta['scoring_inputs_sha256']
            if not required.issubset(set(recorded.values())):
                raise ValueError('TSTR scoring inputs omit required split/release/lineage binding')
            for input_path, expected_hash in recorded.items():
                bindings.append(pin(input_path, expected_hash))
        elif scope == 'tstr':
            if not meta.get('synthesis_lineage_verified') or not meta.get('disjoint_split_verified'):
                raise ValueError('TSTR source lacks verified lineage/split')
            for part in ('train', 'test'):
                bindings.append(pin(ROOT / config['paths'][part], meta['split_binding'][part + '_sha256']))
            name = select['Pipeline']
            if name != 'Real-train':
                method, _, router = name.partition(' + ')
                release = config['releases'][method]
                coordinate_path = (batch / 'tstr_matrix/routes' / method / router / 'view/coordinates.pkl'
                                   if router and router != 'Origin' else ROOT / release['coordinates'])
                bindings.append(pin(coordinate_path, meta['split_binding']['synthetic'][name]))
                bindings.append(pin(ROOT / release['lineage'], meta['split_binding']['synthesis_lineage'][name]['record_sha256']))
        sources.append(dict(**pin(path, expected), row=row, columns=columns, protocol=protocol,
                            format=kind, key=key, select=select, scope=scope, bindings=bindings,
                            status_manifest=str(manifest.resolve())))
    # Explicit bindings support current independent outputs without guessing a
    # historical directory or searching for a similarly named result.
    if 'table_sources' in config:
        for item in config['table_sources']:
            add(item['row'], batch / item['path'], batch / item['manifest'],
                item['columns'], item['protocol'], kind=item.get('format', 'json'),
                key=item.get('key', ''), select=item.get('select'),
                scope=item.get('scope', 'full'))
        return {'classification': 'LOCAL_RESEARCH_TABLE_NOT_A_DP_RELEASE',
                'batch': str(batch), 'sources': sources, 'unavailable_sources': missing}
    for m in ('PrivTrace', 'DPStd', 'DPTraj-PM', 'SPRT'):
        for r in ('Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP'):
            row = f'{m} + {r}'
            coord = current_directory(base / m / r, batch / 'remote_scores_1314' / m / r)
            add(row, coord / 'metrics.json', coord / 'manifest.json', COORD, 'metric-audit-v2-20261016', key='metrics')
            if r != 'Origin':
                road = current_directory(scores / m / r, batch / 'road_scores' / m / r)
                add(row, road / 'metrics.json', road / 'manifest.json', dict(zip(ROAD, ROAD)), 'saved-road-evaluation-v1')
                physical = batch / 'physical_scores' / m / r
                add(row, physical / 'results.csv', physical / 'manifest.json', dict(zip(PHYSICAL, PHYSICAL)), 'full_od_ordered_physical_mass_v1', kind='csv', select={'method': row})
                tasks = batch / 'road_tasks' / m / r
                add(row, tasks / 'metrics.json', tasks / 'manifest.json', ROAD_TASKS, 'retrospective-road-tasks-v1', key='metrics')
    for m in ('DPMM', 'MTNet', 'MTR-DFR'):
        coord = current_directory(base / m / 'Origin', batch / 'remote_scores_1314' / m / 'Origin')
        add(m, coord / 'metrics.json', coord / 'manifest.json', COORD, 'metric-audit-v2-20261016', key='metrics')
        road = current_directory(scores / m / 'Origin', batch / 'road_scores' / m / 'Origin')
        add(m, road / 'metrics.json', road / 'manifest.json', dict(zip(ROAD, ROAD)), 'saved-road-evaluation-v1')
        physical = batch / 'physical_scores' / m / 'Origin'
        add(m, physical / 'results.csv', physical / 'manifest.json', dict(zip(PHYSICAL, PHYSICAL)), 'full_od_ordered_physical_mass_v1', kind='csv', select={'method': m})
        tasks = batch / 'road_tasks' / m / 'Origin'
        add(m, tasks / 'metrics.json', tasks / 'manifest.json', ROAD_TASKS, 'retrospective-road-tasks-v1', key='metrics')
    task_dir = batch / 'tstr_matrix/evaluation'
    if (task_dir / 'manifest.json').is_file():
        names = json.loads((task_dir / 'manifest.json').read_text(encoding='utf-8'))['pipelines']
    else:
        task_dir = follow / 'tstr_results'
        names = ('SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd', 'MTR-DFR', 'Real-train')
    for name in names:
        row = 'Real-train [TSTR reference]' if name == 'Real-train' else name if name == 'MTR-DFR' or ' + ' in name else name + ' + Origin'
        add(row, task_dir / 'results.csv', task_dir / 'manifest.json', TASKS, 'train_test_bound_task_scoring_v2', kind='csv', select={'Pipeline': name}, scope='tstr')
    return {'classification': 'LOCAL_RESEARCH_TABLE_NOT_A_DP_RELEASE', 'batch': str(batch),
            'sources': sources, 'unavailable_sources': missing}

"""Deployment-specific plan checks without private external source paths."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('delivery_current_plans', ROOT/'experiments/_plans.py')
plans = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plans)


def setup():
    config_path = ROOT/'configs/beijing.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    args = SimpleNamespace(config=config_path, method='DPStd', only_router=None, exclude_router=[])
    return config, args


def test_current_generation_and_score_protocol():
    c, a = setup()
    steps, _, _ = plans.build('main', c, a, ROOT)
    command = steps[0]['command']
    assert list(map(float, command[command.index('--bbox')+1:])) == c['measurement_bbox']['DPStd']
    coordinates = [s for s in steps if Path(s['command'][3]).name == 'evaluate_coordinates.py']
    assert len(coordinates) == len(c['routers'])
    for step in coordinates:
        command = step['command']
        assert command[command.index('--metric-protocol')+1] == 'audit-v2'
        assert '--batch' in command and '--input' in command
    assert not any('evaluate-cell' in s['command'] for s in steps)


def test_frozen_ablation_and_registered_tstr():
    c, a = setup()
    steps, _, _ = plans.build('ablation', c, a, ROOT)
    assert Path(steps[0]['command'][3]).name == 'run_dfr_ablation_frozen.py'
    with pytest.raises(ValueError, match='Register actual'):
        plans.build('tstr', c, a, ROOT)
    c['tstr_releases'] = {'example': {'coordinates': 'example.pkl', 'lineage': 'example.json'}}
    steps, _, _ = plans.build('tstr', c, a, ROOT)
    assert Path(steps[0]['command'][3]).name == 'audit_v2_runner.py'


def test_mm2_namespace_and_unbound_rejection():
    c, a = setup()
    a.only_router = 'MM2-MDP'
    c['paths']['mm2_edge_cache'] = 'resources/mm2/specific_cache.pkl.gz'
    steps, _, _ = plans.build('main', c, a, ROOT)
    route = next(s for s in steps if s['name'].startswith('route_'))['command']
    assert route[route.index('--edge-cache')+1] == str((ROOT/c['paths']['mm2_edge_cache']).resolve())
    c['mm2_resources_status'] = 'UNBOUND'
    with pytest.raises(ValueError, match='MM2'):
        plans.build('main', c, a, ROOT)

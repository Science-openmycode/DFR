import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def preview(script, *args):
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / script), *args, '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)['command']


def test_synthesis_does_not_route_or_evaluate():
    command = preview('synthesize.py', '--method', 'SPRT')
    assert 'synthesize-m' in command
    assert '--r' not in command and '--real-reference' not in command


def test_route_uses_explicit_existing_measurement_without_real_input(tmp_path):
    command = preview('route.py', '--method', 'SPRT', '--router', 'FMM', '--input', str(tmp_path / 'existing'))
    assert 'route-cell' in command
    assert command[command.index('--measurement') + 1] == str(tmp_path / 'existing')
    assert 'synthesize-m' not in command and '--real-reference' not in command


def test_evaluation_uses_only_saved_roads(tmp_path):
    command = preview('evaluate.py', '--method', 'SPRT', '--router', 'FMM', '--input', str(tmp_path / 'roads.pkl.gz'))
    assert command[command.index('--synthetic-routes') + 1] == str(tmp_path / 'roads.pkl.gz')
    assert command[3].endswith('evaluate_saved_roads.py')
    assert 'route-cell' not in command and 'synthesize-m' not in command


def test_scoring_uses_region_metric_cache_not_router_connectivity_cache():
    command = preview('evaluate.py', '--method', 'SPRT', '--router', 'STMatch')
    cache = Path(command[command.index('--metric-cache') + 1])
    config = json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    assert cache == (ROOT/config['paths']['metric_cache']).resolve()
    assert cache != (ROOT/config['paths']['edge_cache']).resolve()
    reference = Path(command[command.index('--real-routes') + 1])
    assert reference == (ROOT/config['paths']['metric_real_routes']).resolve()


def test_native_method_cannot_be_rematched():
    result = subprocess.run([sys.executable, str(ROOT / 'route.py'), '--method', 'MTR-DFR', '--router', 'FMM', '--dry-run'], capture_output=True)
    assert result.returncode != 0

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_simple_entrypoint_help():
    result = subprocess.run([sys.executable, str(ROOT / 'experiments/ablation.py'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '--config' in result.stdout


def load_runner():
    spec = importlib.util.spec_from_file_location('simple_runner', ROOT / 'experiments/_runner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completed_step_is_reused_and_modified_output_is_rejected(tmp_path):
    runner = load_runner()
    output = tmp_path / 'value.txt'
    command = [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("done")', str(output)]
    step = {'name': 'write', 'command': command, 'outputs': [str(output)]}
    runner.execute([step], tmp_path / 'logs', ROOT)
    first = output.stat().st_mtime_ns
    runner.execute([step], tmp_path / 'logs', ROOT)
    assert output.stat().st_mtime_ns == first
    output.write_text('changed')
    import pytest
    with pytest.raises(RuntimeError, match='changed'):
        runner.execute([step], tmp_path / 'logs', ROOT)


def test_failure_stops_next_step(tmp_path):
    runner = load_runner()
    marker = tmp_path / 'never.txt'
    steps = [
        {'name': 'fail', 'command': [sys.executable, '-c', 'raise SystemExit(7)'], 'outputs': []},
        {'name': 'never', 'command': [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(marker)], 'outputs': [str(marker)]},
    ]
    import pytest
    with pytest.raises(subprocess.CalledProcessError):
        runner.execute(steps, tmp_path / 'logs', ROOT)
    assert not marker.exists()
    assert json.loads((tmp_path / 'logs/fail.json').read_text(encoding='utf-8'))['exit_code'] == 7


def test_main_dry_run_is_read_only_and_mm2_last():
    result = subprocess.run([sys.executable, str(ROOT / 'experiments/main.py'), '--config', str(ROOT / 'configs/beijing.yaml'), '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    routes = [s for s in plan if 'route-cell' in s['command']]
    assert len(routes) == 16
    assert all('MM2-MDP' not in s['command'] for s in routes)
    assert sum('synthesize-m' in s['command'] for s in plan) == 4


def test_all_planned_scripts_import_and_show_help():
    # --help verifies imports, not argument compatibility or numeric results.
    for experiment in ('main', 'ablation', 'tstr', 'privacy_attack'):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / f'experiments/{experiment}.py'), '--dry-run'], capture_output=True, text=True, encoding='utf-8')
        if experiment in ('privacy_attack', 'tstr'):
            assert result.returncode != 0
            assert 'not bound' in result.stderr
            continue
        assert result.returncode == 0, result.stderr
        for step in json.loads(result.stdout):
            parsed = subprocess.run([*step['command'], '--help'], capture_output=True, text=True, encoding='utf-8')
            assert parsed.returncode == 0, (step['name'], parsed.stderr)


def test_unregistered_output_is_not_overwritten(tmp_path):
    import pytest
    runner = load_runner()
    output = tmp_path / 'existing.txt'
    output.write_text('keep')
    with pytest.raises(RuntimeError, match='unregistered'):
        runner.execute([{'name': 'existing', 'command': [sys.executable, '-c', 'raise SystemExit(0)'], 'outputs': [str(output)]}], tmp_path / 'logs', ROOT)
    assert output.read_text() == 'keep'


def test_reproduce_help_and_plot_dry_run():
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'reproduce.py'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'experiments/plot.py'), '--experiment', 'tstr', '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    steps = json.loads(result.stdout)
    assert '--data-root' in steps[0]['command']
    assert '--figure' in steps[0]['command']


def test_changed_dependency_rejects_reuse(tmp_path):
    import pytest
    runner = load_runner()
    dependency = tmp_path / 'code'
    dependency.mkdir()
    script = dependency / 'algorithm.py'
    script.write_text('version = 1')
    output = tmp_path / 'output'
    step = {'name': 'run', 'command': [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(output)], 'outputs': [str(output)], 'dependency_roots': [str(dependency)]}
    runner.execute([step], tmp_path / 'logs', ROOT)
    script.write_text('version = 2')
    with pytest.raises(RuntimeError, match='changed'):
        runner.execute([step], tmp_path / 'logs', ROOT)


def test_configured_seed_and_bbox_are_bound(tmp_path):
    config = json.loads((ROOT / 'configs/beijing.yaml').read_text(encoding='utf-8'))
    config['evaluation_seed'] = 98765
    config_file = tmp_path / 'config.json'
    config_file.write_text(json.dumps(config))
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'experiments/main.py'), '--config', str(config_file), '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    for step in json.loads(result.stdout):
        if 'evaluate-cell' in step['command']:
            assert step['command'][step['command'].index('--evaluation-seed') + 1] == '98765'
        if 'synthesize-m' in step['command']:
            assert any(Path(p).name == 'bbox.json' for p in step['inputs'])


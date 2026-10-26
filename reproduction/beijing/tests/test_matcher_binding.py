import importlib.util
import json
from pathlib import Path
import sys

import pytest


def fixture_args(tmp_path, monkeypatch):
    file = Path(__file__).resolve().parents[1] / 'bind_matcher.py'
    spec = importlib.util.spec_from_file_location('tested_matcher_binding', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, new = tmp_path / 'old', tmp_path / 'new'
    for root in (old, new):
        (root / 'src/util').mkdir(parents=True)
        (root / 'src/util/util.cpp').write_text('old', encoding='utf-8')
        (root / 'src/algorithm.cpp').write_text('unchanged', encoding='utf-8')
        (root / 'src/io').mkdir()
        (root / 'src/io/mm_writer.cpp').write_text('old writer', encoding='utf-8')
    (new / 'src/util/util.cpp').write_text('large-file compatibility', encoding='utf-8')
    (new / 'src/io/mm_writer.cpp').write_text('preserve input slot IDs', encoding='utf-8')
    binary = tmp_path / 'fmm.exe'
    binary.write_bytes(b'test fixture, not executable')
    config, output = tmp_path / 'config.json', tmp_path / 'out.json'
    config.write_text(json.dumps({'paths': {'real': 'frozen-real', 'network': 'same-network'}, 'epsilon': 1.4}), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['bind_matcher.py', '--config', str(config), '--fmm', str(binary), '--stmatch', str(binary), '--source', str(new), '--original-source', str(old), '--out-config', str(output), '--threads', '4'])
    return module, new, output


def test_binding_preserves_input_and_budget(tmp_path, monkeypatch):
    module, _, output = fixture_args(tmp_path, monkeypatch)
    module.main()
    config = json.loads(output.read_text(encoding='utf-8'))
    assert config['paths']['real'] == 'frozen-real'
    assert config['paths']['network'] == 'same-network'
    assert config['epsilon'] == 1.4
    assert config['threads'] == 4
    assert config['matcher_compatibility']['changed_files'] == ['src/io/mm_writer.cpp', 'src/util/util.cpp']


def test_binding_rejects_algorithm_change(tmp_path, monkeypatch):
    module, source, output = fixture_args(tmp_path, monkeypatch)
    (source / 'src/algorithm.cpp').write_text('changed algorithm', encoding='utf-8')
    with pytest.raises(ValueError, match='Unexpected source changes'):
        module.main()
    assert not output.exists()


def test_changed_binary_is_rejected(tmp_path):
    import hashlib
    from experiments.separate import validate_matcher_binding
    binary = tmp_path / 'fmm.exe'
    binary.write_bytes(b'original')
    config = {'paths': {'fmm': str(binary)}, 'matcher_compatibility': {
        'fmm_sha256': hashlib.sha256(b'original').hexdigest()}}
    validate_matcher_binding(config, tmp_path, 'FMM')
    binary.write_bytes(b'rebuilt')
    with pytest.raises(ValueError, match='Matcher executable changed'):
        validate_matcher_binding(config, tmp_path, 'FMM')

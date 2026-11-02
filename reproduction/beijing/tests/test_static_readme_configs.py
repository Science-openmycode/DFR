import hashlib
import json
from pathlib import Path
import re
import shutil

import pytest
from tools import prepare_experiment_configs as binding

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('city', ['beijing', 'porto'])
def test_prepare_configs_does_not_generate_or_change_command_documents(tmp_path, monkeypatch, city):
    for directory in ['configs', 'supplement/sweeps', 'reproduction_checked_20261024']:
        shutil.copytree(ROOT/directory, tmp_path/directory,
                        ignore=shutil.ignore_patterns('experiments'))
    docs = [*binding.DOCS, 'SUPPLEMENT_COMMANDS_CN.md']
    for doc in docs:
        target = tmp_path/doc
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/doc, target)
    snapshots = {doc:hashlib.sha256((tmp_path/doc).read_bytes()).hexdigest() for doc in docs}
    base = json.loads((ROOT/'configs/beijing.json').read_text())
    base.update(dataset=city, frozen_dataset_id='selected-input', slots=10, train_slots=8, test_slots=2,
                bbox=[40., 42., -9., -7.] if city == 'porto' else base['bbox'])
    base['paths'].update(prepared=str(tmp_path/'prepared'), network=str(tmp_path/'public/network.shp'))
    source = tmp_path/'selected.json'
    source.write_text(json.dumps(base))
    monkeypatch.setattr(binding, 'validate_dataset', lambda *a, **kw:{'dataset_id':'selected-input'})
    out = tmp_path/'configs/experiments'
    result = binding.prepare(source, out, tmp_path)
    assert result['command_documents_written'] == 0
    assert not (tmp_path/'plans').exists()
    for doc, digest in snapshots.items():
        assert hashlib.sha256((tmp_path/doc).read_bytes()).hexdigest() == digest
    for doc in docs:
        for config in re.findall(r'--config (configs/experiments/[\w./-]+\.json)', (tmp_path/doc).read_text(encoding='utf-8')):
            if config.endswith('/attack_ready.json'):
                continue
            assert (tmp_path/config).is_file(), config
            value = json.loads((tmp_path/config).read_text())
            assert (value['dataset'], value['slots'], value['train_slots']) == (city, 10, 8)
            assert value['paths']['network'] == base['paths']['network']
            if 'mm2_edge_cache' in value['paths']:
                assert value['paths']['mm2_edge_cache'] == base['paths']['metric_cache']
    for cell in json.loads((out/'sweeps_plan.json').read_text())['cells']:
        value = json.loads((tmp_path/cell['config']).read_text())
        assert (Path(value['paths']['output'])/value['batch']).as_posix() == cell['directory']
        original = json.loads((ROOT/cell['config'].removeprefix('configs/experiments/')).read_text())
        for key in ['seed', 'epsilon', 'k']:
            assert value.get(key) == original.get(key)
    if city == 'porto':
        value = json.loads((out/'reproduction_checked_20261024/config.json').read_text())
        assert value['measurement_bbox']['DPStd'] == base['bbox']
    with pytest.raises(FileExistsError):
        binding.prepare(source, out, tmp_path)
    custom = tmp_path/'configs/user_named_run'
    binding.prepare(source, custom, tmp_path)
    assert (custom/'configs/beijing.json').is_file()
    assert not any(custom.rglob('*.md'))


def test_readme_references_repository_documents_not_generated_documents():
    for filename in ['README.md', 'README_CN.md']:
        text = (ROOT.parents[1]/filename).read_text(encoding='utf-8')
        assert 'write_batch_commands.py' not in text
        assert 'plans/local_new/commands' not in text
        for target in re.findall(r'\]\((reproduction/beijing/[^)]+)\)', text):
            assert (ROOT.parents[1]/target).exists(), target
    for doc in binding.DOCS:
        text = (ROOT/doc).read_text(encoding='utf-8')
        assert 'configs/experiments/' in text
        assert '--expected-slots 15730' not in text
    native = (ROOT/'REPRODUCE_NATIVE_BASELINES_20261024_CN.md').read_text(encoding='utf-8')
    assert 'vendor/dpmm/evidence/' not in native
    assert '--time-binding resources/' not in native


def test_native_source_nodes_use_explicit_edge_join():
    import geopandas as gpd
    from shapely.geometry import LineString
    from tools.convert_native_node_pairs import source_pairs, convert
    frame = gpd.GeoDataFrame(dict(id=[7], source=[1], target=[2]),
                             geometry=[LineString([(0, 0), (1, 1)])])
    pairs = source_pairs({'edge_nodes':{7:(100, 200)}}, frame)
    assert convert([[(100, 200)], []], pairs)[0]['cpath'] == [7]
    assert (1, 2) not in pairs
    with pytest.raises(ValueError, match='absent'):
        source_pairs({'edge_nodes':{8:(100, 200)}}, frame)

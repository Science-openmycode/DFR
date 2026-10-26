import importlib.util
import hashlib
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fresh_runbook',ROOT/'tools/prepare_reproduction_runbook.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def fixture(tmp_path):
    config={'dataset_policy':'frozen-road-only','frozen_dataset_id':'fixture','batch':'old','paths':{}}
    for key in ('prepared','network','edge_cache','metric_cache','mm2','mm2_network','fmm','stmatch','ubodt','runtime','legacy','mm2_edge_cache'):
        file=tmp_path/'resources'/key
        file.parent.mkdir(exist_ok=True)
        file.write_bytes(b'fixture')
        config['paths'][key]=file.relative_to(tmp_path).as_posix()
    config['paths']['output']='results'
    config['saved_route_inputs']={'must':'not be reused'}
    file=tmp_path/'config.json';file.write_text(json.dumps(config))
    return file


def test_fresh_runbook_complete_scope_and_verbatim_lines(tmp_path):
    source=fixture(tmp_path)
    report=mod.prepare(source,'fresh',tmp_path/'runbook',root=tmp_path)
    assert report['status']=='PLAN_NOT_EXECUTED'
    assert len(report['steps'])==116
    assert report['document_sha256'] == hashlib.sha256((tmp_path/'runbook/COMMANDS_CN.md').read_bytes()).hexdigest()
    lines=(tmp_path/'runbook/COMMANDS_CN.md').read_text(encoding='utf-8').splitlines()
    ids=set()
    for step in report['steps']:
        assert lines[step['document_line']-1]==step['command']
        assert set(step['depends_on']) <= ids
        assert step['id'] not in ids
        ids.add(step['id'])
        assert 'runbook/config.json' in step['command']
        assert all('results/fresh' in p.replace('\\','/') for p in step['outputs'])
    config=json.loads((tmp_path/'runbook/config.json').read_text())
    assert config['saved_route_inputs']=={}
    assert not (tmp_path/'results').exists()
    with pytest.raises(FileExistsError):mod.prepare(source,'fresh',tmp_path/'runbook',root=tmp_path)


def test_no_old_batch_or_external_resource(tmp_path):
    source=fixture(tmp_path)
    (tmp_path/'results/occupied').mkdir(parents=True)
    with pytest.raises(FileExistsError):mod.prepare(source,'occupied',tmp_path/'a',root=tmp_path)
    config=json.loads(source.read_text());config['paths']['runtime']='../external'
    source.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='escapes'):mod.prepare(source,'new',tmp_path/'b',root=tmp_path)
    assert not (tmp_path/'b').exists()


def test_no_inferred_mm2_namespace(tmp_path):
    source=fixture(tmp_path)
    config=json.loads(source.read_text());del config['paths']['mm2_edge_cache']
    source.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='explicitly'):mod.prepare(source,'new',tmp_path/'a',root=tmp_path)

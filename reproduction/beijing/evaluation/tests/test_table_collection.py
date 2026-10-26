import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location('table_collection', ROOT / 'evaluation/table_collection.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fixture(tmp_path):
    path = tmp_path / 'metrics.json'
    path.write_text(json.dumps({'metrics': {'grid': 0.0, 'btf': 0.4}}))
    import hashlib
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'format': 'json', 'key': 'metrics', 'row': 'SPRT + Origin', 'scope': 'full', 'protocol': 'fixture-v1', 'columns': {'grid': 'Grid', 'btf': 'BTF'}, 'bindings': []}


def test_zero_is_observed_missing_is_not_zero(tmp_path):
    source = fixture(tmp_path)
    spec = {'rows': ['SPRT + Origin', 'MTR-DFR'], 'columns': ['Grid', 'BTF']}
    rows = module().collect(spec, [source])
    assert rows[0]['value'] == 0.0 and rows[0]['status'] == 'ZERO'
    assert rows[1]['value'] == 0.4
    assert rows[2]['value'] == '' and rows[2]['status'] == 'MISSING'


def test_modified_input_binding_is_rejected(tmp_path):
    source = fixture(tmp_path)
    source['bindings'] = [{'path': source['path'], 'sha256': '0' * 64}]
    with pytest.raises(ValueError, match='hash'):
        module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])


def test_mixed_metric_definitions_are_rejected(tmp_path):
    first = fixture(tmp_path)
    other = dict(first, row='MTR-DFR', protocol='different-metric')
    with pytest.raises(ValueError, match='protocol'):
        module().collect({'rows': ['SPRT + Origin', 'MTR-DFR'], 'columns': ['Grid']}, [first, other])


def test_duplicate_cell_is_rejected(tmp_path):
    source = fixture(tmp_path)
    with pytest.raises(ValueError, match='duplicate'):
        module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source, source])


def test_tstr_values_cannot_enter_full_corpus_columns(tmp_path):
    source = dict(fixture(tmp_path), scope='tstr')
    with pytest.raises(ValueError, match='scope'):
        module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])


def test_route_plan_reuses_measurements_and_never_rematches_native():
    import subprocess
    import sys
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'experiments/table.py'), 'route', '--dry-run'], capture_output=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    jobs = json.loads(run.stdout)
    assert len(jobs) == 4
    assert all('route-cell' in job['command'] for job in jobs)
    assert all('MM2-MDP' in job['command'] for job in jobs)
    assert all('MTR-DFR' not in job['command'] for job in jobs)


def test_null_metric_remains_missing(tmp_path):
    source = fixture(tmp_path)
    path = Path(source['path'])
    path.write_text(json.dumps({'metrics': {'grid': None, 'btf': .4}}))
    import hashlib
    source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])
    assert rows[0]['status'] == 'MISSING'
    assert rows[0]['value'] == ''


def test_plans_use_current_config_resources_not_historical_bundle(tmp_path):
    import subprocess
    import sys
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['paths']['output']=str(tmp_path/'results')
    config['batch']='isolated-current-batch'
    config_path=tmp_path/'config.json'
    config_path.write_text(json.dumps(config),encoding='utf-8')
    expected_batch=tmp_path/'results'/config['batch']
    for step in ('route','score'):
        run=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'experiments/table.py'),step,
                            '--config',str(config_path),'--dry-run'],capture_output=True,encoding='utf-8')
        assert run.returncode==0,run.stderr
        jobs=json.loads(run.stdout)
        assert jobs
        assert '17123' not in run.stdout and 'four_panel_completion' not in run.stdout
        for job in jobs:
            assert all(Path(out).is_relative_to(expected_batch) for out in job['outputs'])
            cmd=job['command']
            if step=='route':
                measurement=Path(cmd[cmd.index('--measurement')+1])
                assert measurement.parent==expected_batch/'measurements'
            elif job['name'].startswith(('road_','physical_')):
                assert Path(cmd[cmd.index('--real-routes')+1])==(ROOT/config['paths']['metric_real_routes']).resolve()
                assert Path(cmd[cmd.index('--network')+1])==(ROOT/config['paths']['metric_network']).resolve()


def test_explicit_undefined_metric_is_na_not_unmeasured(tmp_path):
    source = fixture(tmp_path)
    path = Path(source['path'])
    path.write_text(json.dumps({'metrics': {'grid': None},
                               'metric_status': {'grid': {'status': 'NA'}}}))
    import hashlib
    source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    source['columns'] = {'grid': 'Grid'}
    rows = module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])
    assert rows[0]['status'] == 'NA'


def test_invalid_metric_does_not_make_table_complete(tmp_path):
    source = fixture(tmp_path)
    path = Path(source['path'])
    path.write_text(json.dumps({'metrics': {'grid': None},
                               'metric_status': {'grid': {'status': 'INVALID'}}}))
    import hashlib
    source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    source['columns'] = {'grid': 'Grid'}
    rows = module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])
    result = module().save(rows, tmp_path/'invalid_table')
    assert result['invalid'] == 1
    assert result['missing'] == 0
    assert result['complete'] is False
    assert rows[0]['value'] == ''


def test_defined_na_is_a_complete_observation_not_zero(tmp_path):
    source = fixture(tmp_path)
    path = Path(source['path'])
    path.write_text(json.dumps({'metrics': {'grid': None},
                               'metric_status': {'grid': {'status': 'NA'}}}))
    import hashlib
    source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    source['columns'] = {'grid': 'Grid'}
    rows = module().collect({'rows': ['SPRT + Origin'], 'columns': ['Grid']}, [source])
    result = module().save(rows, tmp_path/'na_table')
    assert result['invalid'] == 0 and result['complete'] is True
    assert rows[0]['status'] == 'NA' and rows[0]['value'] == ''


def test_tstr_plan_routes_only_train_releases(tmp_path):
    import subprocess
    import sys
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['releases']={m:{'coordinates':str(tmp_path/(m+'_coordinates.pkl')),
                           'lineage':str(tmp_path/(m+'_lineage.json'))}
                        for m in ('SPRT','PrivTrace','DPTraj-PM','DPStd')}
    config_path=tmp_path/'planning.json';config_path.write_text(json.dumps(config),encoding='utf-8')
    run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'experiments/table.py'), 'tstr', '--config',str(config_path),'--batch',str(tmp_path/'batch'), '--dry-run'], capture_output=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    jobs = json.loads(run.stdout)
    routes = [s for s in jobs if 'route-cell' in s['command']]
    assert len(routes) == 12
    assert all('MM2-MDP' not in s['command'] and 'MTR-DFR' not in s['command'] for s in routes)
    assert all('tstr_matrix' in s['command'][s['command'].index('--measurement')+1] for s in routes)
    assert '--require-synthesis-lineage' in jobs[-1]['command']


def test_final_plot_refuses_an_incomplete_table(tmp_path):
    import subprocess
    import sys
    directory = tmp_path / 'collected'
    directory.mkdir()
    (directory / 'coverage.json').write_text('{"complete": false}')
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'experiments/table.py'), 'plot', '--out', str(tmp_path)], capture_output=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'incomplete' in result.stderr
    assert not (tmp_path / 'figures').exists()


@pytest.mark.parametrize('explicit_out', [True, False])
def test_register_uses_explicit_current_sources_and_rejects_changed_hash(tmp_path, explicit_out):
    import hashlib
    import subprocess
    import sys
    batch=tmp_path/'current_batch'
    score=batch/'scores/DPStd/FMM'
    score.mkdir(parents=True)
    metrics=score/'metrics.json'
    metrics.write_text(json.dumps({'BTF':0.25}))
    manifest=score/'manifest.json'
    manifest.write_text(json.dumps({'schema_version':'saved-road-evaluation-v1',
        'outputs':{'metrics_json':{'path':str(metrics),'sha256':hashlib.sha256(metrics.read_bytes()).hexdigest()}},
        'inputs':{}}))
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['table_sources']=[{'row':'DPStd + FMM','path':'scores/DPStd/FMM/metrics.json',
        'manifest':'scores/DPStd/FMM/manifest.json','columns':{'BTF':'BTF'},
        'protocol':'saved-road-evaluation-v1'}]
    selected=tmp_path/'selected.json'
    selected.write_text(json.dumps(config),encoding='utf-8')
    output=tmp_path/'registry' if explicit_out else batch/'table'
    command=[sys.executable,'-X','utf8',str(ROOT/'experiments/table.py'),'register',
             '--config',str(selected),'--batch',str(batch)]
    if explicit_out:
        command.extend(['--out',str(output)])
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode==0,done.stderr
    registry=json.loads((output/'source_registry.json').read_text(encoding='utf-8'))
    assert len(registry['sources'])==1 and registry['unavailable_sources']==[]
    rows=module().collect({'rows':['DPStd + FMM'],'columns':['BTF']},registry['sources'])
    assert rows[0]['value']==0.25
    metrics.write_text(json.dumps({'BTF':0.5}))
    with pytest.raises(ValueError,match='hash'):
        module().collect({'rows':['DPStd + FMM'],'columns':['BTF']},registry['sources'])
    if explicit_out:
        command[-1]=str(tmp_path/'rejected')
    else:
        command.extend(['--out',str(tmp_path/'rejected')])
    rejected=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert rejected.returncode!=0 and 'hash mismatch' in rejected.stderr
    assert not (tmp_path/'rejected/source_registry.json').exists()


def test_registry_relocates_by_hash_and_preserves_manifest_na(tmp_path):
    import hashlib
    import subprocess
    import sys
    batch=tmp_path/'batch';batch.mkdir()
    data=batch/'metrics.json';data.write_text('{"BTF":null}')
    input_file=batch/'bound_input.bin';input_file.write_bytes(b'fixture-input')
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=batch/'manifest.json'
    manifest.write_text(json.dumps({'schema_version':'saved-road-evaluation-v1',
        'metric_status':{'BTF':'NA'},
        'inputs':{'synthetic_routes':{'path':'Z:/unavailable/run/input.bin','sha256':digest(input_file)}},
        'outputs':{'metrics_json':{'path':str(data),'sha256':digest(data)}}}))
    original=manifest.read_bytes()
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['table_artifact_locations']={digest(input_file):str(input_file)}
    config['table_sources']=[{'row':'DPMM','path':'metrics.json','manifest':'manifest.json',
        'columns':{'BTF':'BTF'},'protocol':'saved-road-evaluation-v1'}]
    selected=batch/'config.json';selected.write_text(json.dumps(config))
    out=tmp_path/'registry'
    command=[sys.executable,'-X','utf8',str(ROOT/'experiments/table.py'),'register','--config',str(selected),
             '--batch',str(batch),'--out',str(out)]
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode==0,done.stderr
    registry=json.loads((out/'source_registry.json').read_text())
    rows=module().collect({'rows':['DPMM'],'columns':['BTF']},registry['sources'])
    assert rows[0]['status']=='NA' and rows[0]['value']==''
    assert manifest.read_bytes()==original
    input_file.write_bytes(b'wrong-input')
    command[-1]=str(tmp_path/'rejected')
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode!=0 and 'hash mismatch' in done.stderr


@pytest.mark.parametrize('family', ['scores', 'road_scores'])
def test_frozen_matrix_reads_both_current_road_output_locations(tmp_path, family):
    import hashlib
    path=ROOT/'tools/collect_frozen_matrix.py'
    spec=importlib.util.spec_from_file_location('frozen_matrix_under_test',path)
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    directory=tmp_path/family/'SPRT'/'MM2-MDP';directory.mkdir(parents=True)
    result=directory/'metrics.json';result.write_text('{"BTF":0.375}')
    meta={'inputs':{'real_routes':{'sha256':'0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c'}},
          'real':{'reference_slots':15730},'synthetic':{'slots':15730},
          'outputs':{'metrics_json':{'sha256':hashlib.sha256(result.read_bytes()).hexdigest()}}}
    manifest=directory/'manifest.json';manifest.write_text(json.dumps(meta))
    rows=collector.collect(tmp_path,{'rows':['SPRT + MM2-MDP'],'columns':['BTF']})
    assert len(rows)==1 and rows[0]['value']==0.375 and rows[0]['family']==family
    meta['synthetic']['slots']=10040;manifest.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='denominator'):
        collector.collect(tmp_path,{'rows':['SPRT + MM2-MDP'],'columns':['BTF']})


@pytest.mark.parametrize('status', [None, 'NA', 'INVALID', 'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE'])
def test_frozen_matrix_does_not_infer_na_from_null(tmp_path, status):
    spec=importlib.util.spec_from_file_location('frozen_status_test',ROOT/'tools/collect_frozen_matrix.py')
    collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
    manifest=tmp_path/'manifest.json';result=tmp_path/'metrics.json'
    manifest.write_text(json.dumps({'metric_status':{'score':status} if status else {}}))
    result.write_text('{"metrics":{"score":null}}')
    assert collector.metric_status(None,'score',manifest,result)==(status or 'MISSING')
    result.write_text('{"metric_status":{"score":"VALID"}}')
    with pytest.raises(ValueError):
        collector.metric_status(None,'score',manifest,result)
    result.write_text('{}')
    with pytest.raises(ValueError,match='Non-finite'):
        collector.metric_status(float('nan'),'score',manifest,result)


@pytest.mark.parametrize('explicit_sources', [True, False])
def test_register_current_coordinate_protocol_and_population(tmp_path, explicit_sources):
    import hashlib
    import subprocess
    import sys
    directory=tmp_path if explicit_sources else tmp_path/'coordinate_scores_audit_v2/DPStd/FMM'
    directory.mkdir(parents=True,exist_ok=True)
    result=directory/'metrics.json';result.write_text('{"metrics":{"grid_density_jsd":0.25}}')
    manifest=directory/'manifest.json'
    meta={'schema_version':1,'metric_revision':{'protocol':'metric-audit-v2-20261016'},
          'inputs':{'real':{'count':15730}},
          'outputs':{'metrics.json':hashlib.sha256(result.read_bytes()).hexdigest()}}
    manifest.write_text(json.dumps(meta))
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['table_sources']=[{'row':'DPStd + FMM','path':'metrics.json','manifest':'manifest.json',
        'columns':{'grid_density_jsd':'Grid'},'protocol':'metric-audit-v2-20261016','key':'metrics'}]
    if not explicit_sources:
        del config['table_sources']
    selected=tmp_path/'config.json';selected.write_text(json.dumps(config))
    command=[sys.executable,str(ROOT/'experiments/table.py'),'register','--config',str(selected),
             '--batch',str(tmp_path),'--out',str(tmp_path/'accepted')]
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode==0,done.stderr
    registry=json.loads((tmp_path/'accepted/source_registry.json').read_text())
    assert module().collect({'rows':['DPStd + FMM'],'columns':['Grid']},registry['sources'])[0]['value']==0.25
    meta['inputs']['real']['count']=10040;manifest.write_text(json.dumps(meta))
    command[-1]=str(tmp_path/'rejected')
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode!=0 and 'population mismatch' in done.stderr
    assert not (tmp_path/'rejected').exists()


def test_default_register_road_tasks_verifies_path_hash_inputs(tmp_path):
    import hashlib
    import subprocess
    import sys
    directory=tmp_path/'road_tasks/DPStd/FMM';directory.mkdir(parents=True)
    result=directory/'metrics.json'
    result.write_text('{"metrics":{"RC-NDCG":0.2,"NextRoadAcc":0.3,"NextRoadNLL":1.5}}')
    data=tmp_path/'routes.bin';data.write_bytes(b'fixture-roads')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    manifest=directory/'manifest.json'
    manifest.write_text(json.dumps({'dataset_id':config['frozen_dataset_id'],
        'real_slots':15730,'synthetic_slots':15730,'command':['python','evaluate_road_tasks.py'],
        'inputs':{str(data):digest(data)},'result_sha256':digest(result)}))
    selected=tmp_path/'config.json';selected.write_text(json.dumps(config))
    command=[sys.executable,str(ROOT/'experiments/table.py'),'register','--config',str(selected),
             '--batch',str(tmp_path),'--out',str(tmp_path/'accepted')]
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode==0,done.stderr
    registry=json.loads((tmp_path/'accepted/source_registry.json').read_text())
    rows=module().collect({'rows':['DPStd + FMM'],'columns':['NextRoadAcc']},registry['sources'])
    assert rows[0]['value']==0.3 and rows[0]['scope']=='full'
    data.write_bytes(b'tampered')
    command[-1]=str(tmp_path/'rejected')
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode!=0 and 'hash mismatch' in done.stderr


def test_tstr_registry_requires_scoring_split_release_and_lineage(tmp_path):
    import hashlib
    import subprocess
    import sys
    files={}
    for label in ('train','test','split','synthetic','lineage'):
        path=tmp_path/(label+'.bin');path.write_bytes(label.encode())
        files[label]=(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
    result=tmp_path/'results.csv';result.write_text('Pipeline,Next-cell Hit@1\nDPStd + FMM,0.25\n')
    meta={'protocol':'train_test_bound_task_scoring_v2','synthesis_lineage_verified':True,
          'disjoint_split_verified':True,'results_sha256':hashlib.sha256(result.read_bytes()).hexdigest(),
          'scoring_inputs_sha256':dict(files.values()),
          'split_binding':{'train_sha256':files['train'][1],'test_sha256':files['test'][1],
             'disjoint_split':{'train_count':12584,'test_count':3146,'record_sha256':files['split'][1]},
             'synthetic':{'DPStd + FMM':files['synthetic'][1]},
             'synthesis_lineage':{'DPStd + FMM':{'record_sha256':files['lineage'][1]}}}}
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(meta))
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['table_sources']=[{'row':'DPStd + FMM','path':'results.csv','manifest':'manifest.json',
        'columns':{'Next-cell Hit@1':'NextCellHit1'},'protocol':meta['protocol'],
        'format':'csv','select':{'Pipeline':'DPStd + FMM'},'scope':'tstr'}]
    selected=tmp_path/'config.json';selected.write_text(json.dumps(config))
    command=[sys.executable,str(ROOT/'experiments/table.py'),'register','--config',str(selected),
             '--batch',str(tmp_path),'--out',str(tmp_path/'accepted')]
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode==0,done.stderr
    registry=json.loads((tmp_path/'accepted/source_registry.json').read_text())
    assert module().collect({'rows':['DPStd + FMM'],'columns':['NextCellHit1']},registry['sources'])[0]['value']==0.25
    del meta['scoring_inputs_sha256'][files['lineage'][0]]
    manifest.write_text(json.dumps(meta));command[-1]=str(tmp_path/'rejected')
    done=subprocess.run(command,capture_output=True,encoding='utf-8')
    assert done.returncode!=0 and 'omit required' in done.stderr

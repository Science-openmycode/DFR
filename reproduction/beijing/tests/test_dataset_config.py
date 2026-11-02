import json
from pathlib import Path
import pytest
from preprocess.dataset_config import load_config


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture(tmp_path, city='porto'):
    write(tmp_path/'data/canonical_manifest.json', dict(schema='frozen-road-dataset-v1',
        status='FROZEN', dataset=city, trajectory_count=10, train_count=8, test_count=2))
    write(tmp_path/'dataset.json', dict(schema='road-experiment-bundle-v1', dataset=city,
        paths=dict(prepared='data', network='public/network.shp', metric_cache='public/cache.pkl.gz')))
    config = dict(dataset_bundle='dataset.json', epsilon=1.4, seed=20260713,
                  paths=dict(legacy='legacy', output='results'))
    write(tmp_path/'experiment.json', config)
    return config


def test_legacy_config_is_unchanged(tmp_path):
    original=dict(dataset='beijing', paths=dict(prepared='resources/data'), seed=42)
    write(tmp_path/'old.json', original)
    assert load_config(tmp_path/'old.json', tmp_path/'other') == original


@pytest.mark.parametrize('city', ['beijing', 'porto', 'another_city'])
def test_same_loader_supports_cities_without_city_branches(tmp_path, city):
    fixture(tmp_path, city)
    result=load_config(tmp_path/'experiment.json', tmp_path/'legacyroot')
    assert result['dataset']==city
    assert (result['slots'],result['train_slots'],result['test_slots'])==(10,8,2)
    assert Path(result['paths']['real'])==tmp_path/'data/trajectories.pkl'
    assert Path(result['paths']['metric_real_routes'])==tmp_path/'data/road_records.pkl.gz'
    assert result['paths']['legacy']=='legacy'
    assert result['epsilon']==1.4


def test_population_conflict_rejected(tmp_path):
    c=fixture(tmp_path);c['slots']=15730;write(tmp_path/'experiment.json',c)
    with pytest.raises(ValueError,match='Conflicting dataset field'):
        load_config(tmp_path/'experiment.json',tmp_path)


def test_path_conflict_rejected(tmp_path):
    c=fixture(tmp_path);c['paths']['train']='beijing/train.pkl';write(tmp_path/'experiment.json',c)
    with pytest.raises(ValueError,match='Conflicting data path'):
        load_config(tmp_path/'experiment.json',tmp_path)


def test_unknown_schema_rejected(tmp_path):
    fixture(tmp_path);write(tmp_path/'dataset.json',dict(schema='unknown'))
    with pytest.raises(ValueError,match='schema'):load_config(tmp_path/'experiment.json',tmp_path)


def test_public_crs_shared_without_city_defaults(tmp_path):
    fixture(tmp_path)
    bundle=json.loads((tmp_path/'dataset.json').read_text())
    bundle['routing_crs']={'input_srs':'EPSG:4326','network_srs':'EPSG:32629'}
    bundle['bbox']=[41.1,41.2,-8.7,-8.55]
    write(tmp_path/'dataset.json',bundle)
    result=load_config(tmp_path/'experiment.json',tmp_path)
    assert result['routing_crs']==bundle['routing_crs']
    assert result['bbox']==bundle['bbox']


def test_public_crs_conflict_rejected(tmp_path):
    c=fixture(tmp_path);c['routing_crs']={'network_srs':'EPSG:32650'}
    write(tmp_path/'experiment.json',c)
    bundle=json.loads((tmp_path/'dataset.json').read_text())
    bundle['routing_crs']={'network_srs':'EPSG:32629'};write(tmp_path/'dataset.json',bundle)
    with pytest.raises(ValueError,match='Conflicting public resource'):
        load_config(tmp_path/'experiment.json',tmp_path)


@pytest.mark.parametrize('stage', ['synthesize', 'route', 'evaluate'])
def test_stage_argv_matches_equivalent_legacy_config(tmp_path, monkeypatch, capsys, stage):
    from experiments.separate import main, ROOT
    c=fixture(tmp_path)
    c.update(batch='isolated',bbox=[41.1,41.2,-8.7,-8.55])
    c['paths'].update(osm='public/ways.pkl',edge_cache='public/edge.pkl')
    write(tmp_path/'experiment.json',c)
    expanded=load_config(tmp_path/'experiment.json',ROOT)
    expanded.pop('dataset_bundle')
    write(tmp_path/'expanded.json',expanded)
    commands=[]
    for config in ('experiment.json','expanded.json'):
        argv=['entry','--config',str(tmp_path/config),'--method','SPRT','--dry-run']
        if stage!='synthesize': argv+=['--router','Nearest']
        monkeypatch.setattr('sys.argv',argv)
        main(stage)
        commands.append(json.loads(capsys.readouterr().out)['command'])
    assert commands[0]==commands[1]


@pytest.mark.parametrize('city,epsg',[('beijing','EPSG:32650'),('porto','EPSG:32629')])
def test_route_cli_forwards_explicit_city_projection(tmp_path,monkeypatch,capsys,city,epsg):
    from experiments.separate import main
    c=fixture(tmp_path,city)
    c.update(batch='projection_check')
    c['paths'].update(osm='osm.pkl',edge_cache='edges.pkl',fmm='fmm.exe',runtime='runtime',ubodt='table.txt')
    write(tmp_path/'experiment.json',c)
    b=json.loads((tmp_path/'dataset.json').read_text())
    b['routing_crs']=dict(input_srs='EPSG:4326',tracks_srs=epsg,network_srs=epsg)
    write(tmp_path/'dataset.json',b)
    monkeypatch.setattr('sys.argv',['route.py','--config',str(tmp_path/'experiment.json'),'--method','SPRT','--router','FMM','--dry-run'])
    main('route');command=json.loads(capsys.readouterr().out)['command']
    assert command[command.index('--tracks-srs')+1]==epsg
    assert command[command.index('--network-srs')+1]==epsg

import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

from preprocess.workflow import Workflow, selection
from tools import write_batch_commands as planner

ROOT=Path(__file__).resolve().parents[1]


def profile(root,city='beijing',adapter='geolife',**extra):
    path=root/f'{city}.json'
    path.write_text(json.dumps(dict(schema='readme-dataset-workflow-v1',dataset=city,
                                   adapter=adapter,source='input',**extra)),encoding='utf-8')
    return {'DFR_DATASET_CONFIG':str(path)}


def test_default_and_one_time_selection():
    assert selection(ROOT,{})[1]['dataset']=='beijing'
    assert selection(ROOT,{'DFR_DATASET_CONFIG':'configs/datasets/porto.workflow.json'})[1]['adapter']=='start_porto_archive'


def test_selection_refuses_city_change_and_profile_edit(tmp_path):
    env=profile(tmp_path);w=Workflow(tmp_path,env);w.guard()
    with pytest.raises(ValueError,match='separate clean checkout'):
        Workflow(tmp_path,profile(tmp_path,'porto','start_porto_archive')).guard()
    (tmp_path/'beijing.json').write_text((tmp_path/'beijing.json').read_text()+' ')
    with pytest.raises(ValueError,match='separate clean checkout'):w.guard()


def test_dry_run_does_not_create_outputs(tmp_path):
    w=Workflow(tmp_path,profile(tmp_path));w.run('roads',dry_run=True)
    assert not (tmp_path/'data').exists()


def test_city_mismatch_is_not_accepted(tmp_path):
    (tmp_path/'input').mkdir()
    (tmp_path/'input/dataset.json').write_text(json.dumps({'dataset':'porto'}))
    w=Workflow(tmp_path,profile(tmp_path,adapter='standard_bundle'));w.guard()
    with pytest.raises(ValueError,match='Selected city'):w._active_bundle()


def test_standard_source_is_read_only_and_caches_are_batch_local(tmp_path):
    source=tmp_path/'input';source.mkdir()
    original=json.dumps(dict(dataset='porto',paths=dict(prepared='prepared',network='network.shp',
        osm='public.pkl',time_endpoints='time.csv',metric_cache='old.pkl')))
    (source/'dataset.json').write_text(original)
    w=Workflow(tmp_path,profile(tmp_path,'porto','standard_bundle'));w.guard()
    active=json.loads(w._active_bundle().read_text())
    assert 'metric_cache' not in active['paths']
    assert active['paths']['prepared']==str(source/'prepared')
    assert (source/'dataset.json').read_text()==original


@pytest.mark.parametrize('city',['beijing','porto'])
def test_public_support_never_crosses_cities(tmp_path,city):
    (tmp_path/'configs').mkdir()
    (tmp_path/'configs/local_public.json').write_text(json.dumps({'paths':{}}))
    sweeps=tmp_path/'supplement/sweeps';sweeps.mkdir(parents=True)
    for k in (24,48,96,192,384,768):
        (sweeps/f'k_{k}_seed_1.json').write_text(json.dumps({'k':k}))
    w=Workflow(tmp_path,profile(tmp_path,city));calls=[]
    w.invoke=lambda label,args:calls.append(args)
    w.resources()
    assert ('--frozen-support' in calls[0])==(city=='beijing')
    assert calls[0][-1]=='resources' if city=='beijing' else calls[0][-1]=='data/local_public_resources'


def test_zero_node_mm2_export_preserves_topology(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    from prepare_mm2_city import export_osm
    frame=gpd.GeoDataFrame(dict(id=[0,1],source=[0,1],target=[1,2]),
        geometry=[LineString([(0,0),(1,0)]),LineString([(1,0),(2,0)])],crs=4326)
    target=tmp_path/'roads.osm';export_osm(frame,target)
    tree=ET.parse(target).getroot();ways=tree.findall('way')
    assert [int(w.attrib['id']) for w in ways]==[1,2]
    assert ways[0].findall('nd')[-1].attrib['ref']==ways[1].findall('nd')[0].attrib['ref']
    assert all(int(n.attrib['id'])>0 for n in tree.findall('node'))


def test_bundle_plan_uses_same_native_entrypoints_without_legacy_times(tmp_path,monkeypatch):
    for directory in ['configs','supplement/sweeps','reproduction_checked_20261024']:
        shutil.copytree(ROOT/directory,tmp_path/directory)
    for doc in planner.DOCS:
        target=tmp_path/doc;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/doc,target)
    c=json.loads((ROOT/'configs/beijing.json').read_text())
    c.update(dataset='porto',batch='local_new',slots=695083,train_slots=556066,test_slots=139017,dataset_bundle=str(tmp_path/'bundle.json'),
             routing_crs={'network_srs':'EPSG:32629'},mm2_city_binding={'sha256':'fixture'})
    c['paths']['time_endpoints']=str(tmp_path/'endpoints.csv')
    cfg=tmp_path/'input.json';cfg.write_text(json.dumps(c))
    monkeypatch.setattr(planner,'ROOT',tmp_path)
    monkeypatch.setattr('preprocess.dataset_contract.validate_dataset',lambda *a,**k:{'dataset_id':c['frozen_dataset_id']})
    result=planner.generate(cfg,tmp_path/'plans/local_new')
    text=(tmp_path/'plans/local_new/commands/REPRODUCE_NATIVE_BASELINES_20261024_CN.md').read_text()
    lines=[line for line in text.splitlines() if 'prepare_mtnet_frozen.py' in line]
    assert lines and all('--time-binding' not in line and '--raw-reference' not in line for line in lines)
    dfr=(tmp_path/'plans/local_new/commands/REPRODUCE_DFR_LENGTH_20261024_CN.md').read_text(encoding='utf-8')
    assert '全集695083条' in dfr and '训练专用556066条' in dfr
    for value in result['configs'].values():
        bound=json.loads((tmp_path/value).read_text())
        assert bound['dataset']=='porto'
        assert bound['dataset_bundle']==c['dataset_bundle']
        assert bound['routing_crs']==c['routing_crs']
        assert bound['mm2_city_binding']==c['mm2_city_binding']

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from preprocess.dfr_author_roads import author_groups,bind_author_domain,load_author_domain
from preprocess.dataset_contract import sha
from preprocess.dataset_config import load_config

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('relative',[
    'synthesize_dfr.py','synthesize_dfr_train.py','run_dfr_ablation_frozen.py',
    'supplement/k_original/synthesize_dfr.py','supplement/k_original/synthesize_endpoint_diagnostic.py'])
def test_every_dfr_entry_binds_the_public_author_domain(relative):
    import ast
    tree=ast.parse((ROOT/relative).read_text(encoding='utf-8'))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert any(n.func.id=='bind_author_domain' for n in calls),relative
    assert any(n.func.id=='load_config' for n in calls),relative

def test_beijing_domain_function_is_not_replaced():
    original=lambda cache:cache
    core=SimpleNamespace(build_public_endpoint_domain=original)
    assert bind_author_domain(core,{'dataset':'beijing'},ROOT,Path('unused')) is None
    assert core.build_public_endpoint_domain is original

def test_author_aliases_and_partial_overlap():
    row=lambda edges:dict(edges=edges,status='EXACT_UNIQUE_CONNECTED')
    groups,aliases=author_groups({'a':row([1,2]),'b':row([1,2])},[1,2])
    assert groups[1]==groups[2] and aliases==[['a','b']]
    with pytest.raises(ValueError,match='partial'):
        author_groups({'a':row([1,2]),'b':row([2,3])},[1,2,3])

def test_author_domain_needs_no_fabricated_osm_columns(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    frame=gpd.GeoDataFrame(dict(id=[1,2],source=[1,2],target=[2,3]),
        geometry=[LineString([(0,0),(1,0)]),LineString([(1,0),(2,0)])],crs=32629)
    network=tmp_path/'network.shp';frame.to_file(network)
    (tmp_path/'road_mapping.json').write_text(json.dumps({'77':dict(edges=[1,2],status='EXACT_UNIQUE_CONNECTED')}))
    names=['network.shp','network.dbf','network.shx','network.prj','road_mapping.json']
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(dict(carrier_policy='source_directed_v1',outputs={n:sha(tmp_path/n) for n in names})))
    core=SimpleNamespace()
    binding=dict(manifest=str(manifest),sha256=sha(manifest))
    assert bind_author_domain(core,{'dfr_author_roads':binding},ROOT,network)['mode']=='author-road-v1'
    edges,attrs=core.build_public_endpoint_domain({'edge_nodes':{1:(10,20),2:(20,30)}})
    assert len(edges)==2 and attrs[(10,20)][0]==attrs[(20,30)][0]
    assert attrs[(10,20)][1:]==(None,None)
    import shutil
    copied=tmp_path/'copied';copied.mkdir()
    for suffix in ('.shp','.dbf','.shx','.prj'):
        shutil.copy2(network.with_suffix(suffix),copied/('network'+suffix))
    load_author_domain(binding,ROOT,copied/'network.shp')
    with (copied/'network.dbf').open('ab') as handle:handle.write(b'changed')
    with pytest.raises(ValueError,match='copy changed'):
        load_author_domain(binding,ROOT,copied/'network.shp')

def test_bundle_author_manifest_is_relative_to_bundle_not_checkout(tmp_path):
    prepared=tmp_path/'data';prepared.mkdir()
    (prepared/'canonical_manifest.json').write_text(json.dumps(dict(schema='frozen-road-dataset-v1',
        status='FROZEN',dataset='porto',trajectory_count=10,train_count=8,test_count=2)))
    bundle=dict(schema='road-experiment-bundle-v1',dataset='porto',paths=dict(prepared='data',network='public/network.shp'),
        dfr_author_roads=dict(manifest='public/manifest.json',sha256='abc'))
    (tmp_path/'dataset.json').write_text(json.dumps(bundle))
    config=tmp_path/'run.json';config.write_text(json.dumps(dict(dataset_bundle='dataset.json')))
    assert load_config(config,ROOT)['dfr_author_roads']['manifest']==str(tmp_path/'public/manifest.json')

def test_dpmm_keeps_encoded_author_roads_but_beijing_filter_unchanged():
    original=ROOT/'vendor/dpmm/original'
    sys.path.insert(0,str(original))
    try:
        file=original/'check/run_dpmm_official_beijing.py'
        spec=importlib.util.spec_from_file_location('porto_dpmm_binding_test',file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:sys.path.remove(str(original))
    def way(highway,author=False):
        value=dict(id=77,tags=dict(highway=highway,oneway='yes'),
            geometry=[dict(lat=41.15,lon=-8.65),dict(lat=41.16,lon=-8.64)])
        if author:value.update(graph_policy='source_directed_v1',source='START_pre_vocabulary_road',source_road_id=99)
        return value
    bbox=(41.1,41.2,-8.7,-8.55)
    with pytest.raises(RuntimeError,match='zero drivable'):
        module.build_official_inputs([way('3')],bbox)
    edges,nodes,graph,_=module.build_official_inputs([way('3',True)],bbox)
    assert len(edges)==1 and set(edges.highway)=={'3'}
    assert graph.number_of_edges()==1
    beijing,_,_,_=module.build_official_inputs([way('residential')],bbox)
    assert len(beijing)==1

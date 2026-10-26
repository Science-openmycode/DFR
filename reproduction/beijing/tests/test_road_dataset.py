import importlib.util
from pathlib import Path
import numpy as np
import pytest
import csv
import gzip
import hashlib
import json
import pickle
import subprocess
import sys

def module():
    spec=importlib.util.spec_from_file_location('road_dataset',Path(__file__).resolve().parents[1]/'preprocess/road_dataset.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def test_retry_updates_connected_and_keeps_original_identity():
    initial=[dict(source_index=0,accepted=False,source_points=2,connected=False,observation_share=0)]
    retry=[dict(source_index=0,accepted=True,reason='ACCEPTED',cpath=(1,),opath=(1,1),residual_m=(1,2))]
    result=module().choose_records(initial,retry)[0]
    assert result['connected'] is True
    assert result['observation_share']==1
    assert result['first_success_candidates']==16
    assert result['source_index']==0

def test_retry_never_replaces_an_already_successful_trajectory():
    with pytest.raises(ValueError,match='failed-at-8'):
        module().choose_records([dict(source_index=0,accepted=True)],[dict(source_index=0)])

def test_duplicate_source_ids_are_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        module().choose_records([dict(source_index=0,accepted=False)],[dict(source_index=0),dict(source_index=0)])

def test_bias_measures_detect_disjoint_groups_and_identical_distributions():
    compare=module().numerical_comparison
    assert compare([1,2,100,101],[True,True,False,False])['ks']==1
    assert compare([1,2,1,2],[True,True,False,False])['ks']==0
    assert module().categorical_comparison(['a','a','b','b'],[True,True,False,False])['total_variation']==1

def test_distance_is_in_metres_and_includes_straight_motion():
    assert 111000 < module().distance(np.array([[0,0],[0,1]])).sum() < 112000

def test_cli_freezes_clean_toy_data_and_contract_checks_the_result(tmp_path):
    import geopandas as gpd
    from pyproj import Transformer
    from shapely.geometry import LineString
    root=Path(__file__).resolve().parents[1]
    adapter=root/'vendor/road_preprocessing/road_route_io_fixed.py'
    transform=Transformer.from_crs('EPSG:4326','EPSG:32650',always_xy=True)
    x,y=transform.transform(116.3,39.9)
    graph=tmp_path/'network.shp'
    gpd.GeoDataFrame({'id':[1],'source':[0],'target':[1]},geometry=[LineString([(x-50,y),(x+50,y)])],crs='EPSG:32650').to_file(graph)
    coords=np.array([[39.9,116.2999],[39.9,116.3001]],dtype='<f8')
    source=tmp_path/'source.pkl';source.write_bytes(pickle.dumps([coords,coords,coords]))
    times=tmp_path/'times.pkl';times.write_bytes(pickle.dumps([np.array([40000.,40000.001])]*3))
    binding=tmp_path/'binding.csv'
    with binding.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['source_index','coordinate_sha256'])
        key=hashlib.sha256((2).to_bytes(8,'little')+coords.tobytes()).hexdigest()
        writer.writerows((i,key) for i in range(3))
    records=[dict(source_index=i,accepted=True,reason='ACCEPTED',source_points=2,matcher_input_points=2,
                  cpath=(1,),opath=(1,1),residual_m=(0.,0.),connected=True,observation_share=1.) for i in range(3)]
    base=tmp_path/'base.pkl';base.write_bytes(pickle.dumps(records))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={str(p.resolve()):sha(p) for p in [source,graph,adapter]}
    manifest=tmp_path/'summary.json';manifest.write_text(json.dumps({'input_bindings':inputs,'output_sha256':sha(base)}),encoding='utf-8')
    retry=tmp_path/'retry';retry.mkdir()
    with gzip.open(retry/'diagnostic_records.pkl.gz','wb') as f:pickle.dump([],f)
    (retry/'manifest.json').write_text(json.dumps(dict(candidates=16,radius_m=200,gps_error_m=50,
        status='DIAGNOSTIC_COMPLETE_NOT_REFERENCE',input_bindings=inputs,source_indices=[])),encoding='utf-8')
    out=tmp_path/'out'
    command=[sys.executable,'-X','utf8',str(root/'preprocess/road_dataset.py'),'--source',str(source),
        '--network',str(graph),'--matcher-module',str(adapter),'--base-matches',str(base),
        '--base-manifest',str(manifest),'--retry-dir',str(retry),'--timestamps',str(times),
        '--timestamp-bindings',str(binding),'--bbox','39.75','40.15','116.1','116.65','--out',str(out)]
    run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
    assert run.returncode==0,run.stderr
    assert 'FROZEN:' in run.stdout
    spec=importlib.util.spec_from_file_location('contract',root/'preprocess/dataset_contract.py')
    contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
    assert contract.validate_dataset(out/'dataset')['count']==3
    assert source.read_bytes()==pickle.dumps([coords,coords,coords])

import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

def contract():
    spec=importlib.util.spec_from_file_location('dataset_contract',Path(__file__).resolve().parents[1]/'preprocess/dataset_contract.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def fixture(root):
    files={'trajectories.pkl':b'data','trajectories.pkl.gz':b'data','road_records.pkl.gz':b'roads','train.pkl':b'train','test.pkl':b'test',
           'train_split.json':b'{"indices":[0]}','test_split.json':b'{"indices":[1]}','source_indices.json':b'[3,7]','bbox.json':b'{}'}
    for name,value in files.items():(root/name).write_bytes(value)
    graph=root/'public.shp';graph.write_bytes(b'public')
    meta=dict(schema='frozen-road-dataset-v1',status='FROZEN',trajectory_count=2,train_count=1,test_count=1,
        network=str(graph),network_sha256=hashlib.sha256(b'public').hexdigest(),
        artifacts={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    (root/'canonical_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    return meta

def test_frozen_dataset_returns_its_population_and_identity(tmp_path):
    fixture(tmp_path)
    answer=contract().validate_dataset(tmp_path)
    assert answer['count']==2
    assert answer['train_count']==answer['test_count']==1
    assert len(answer['dataset_id'])==64

def test_changed_coordinate_file_is_rejected(tmp_path):
    fixture(tmp_path);(tmp_path/'trajectories.pkl').write_bytes(b'old raw source')
    with pytest.raises(ValueError,match='artifact changed'):contract().validate_dataset(tmp_path,verify_hashes=True)

def test_user_data_does_not_require_historical_bytes(tmp_path):
    fixture(tmp_path);(tmp_path/'trajectories.pkl').write_bytes(b'user supplied data')
    assert contract().validate_dataset(tmp_path)['count']==2

def test_review_only_output_cannot_masquerade_as_frozen(tmp_path):
    meta=fixture(tmp_path);meta['status']='BLOCKED_SELECTION_DIFFERENCES'
    (tmp_path/'canonical_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    with pytest.raises(ValueError,match='approved frozen'):contract().validate_dataset(tmp_path)

def test_overlap_is_rejected_even_with_recomputed_file_hash(tmp_path):
    meta=fixture(tmp_path);content=b'{"indices":[0]}'
    (tmp_path/'test_split.json').write_bytes(content)
    meta['artifacts']['test_split.json']=hashlib.sha256(content).hexdigest()
    (tmp_path/'canonical_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    with pytest.raises(ValueError,match='overlaps'):contract().validate_dataset(tmp_path)

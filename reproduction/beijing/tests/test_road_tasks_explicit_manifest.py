import hashlib
import json

import pytest

from evaluate_road_tasks import verify_score_inputs
from evaluate_road_tasks import road_task_records


def test_explicit_arm_manifest_binds_actual_inputs(tmp_path):
    inputs={key:tmp_path/key for key in ('real_routes','synthetic_routes','metric_cache')}
    for key,path in inputs.items():
        path.write_bytes(key.encode())
    ledger={'inputs':{key:{'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                      for key,path in inputs.items()}}
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(ledger),encoding='utf-8')
    assert verify_score_inputs(manifest,inputs)==ledger
    inputs['synthetic_routes'].write_bytes(b'other arm')
    with pytest.raises(ValueError,match='synthetic_routes'):
        verify_score_inputs(manifest,inputs)


def test_missing_score_manifest_is_not_replaced_with_full_method(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_score_inputs(tmp_path/'missing.json',{})


def test_beijing_legacy_records_are_returned_unchanged():
    raw=[{'accepted':True,'cpath':[7,9]},{'accepted':False,'cpath':[]}]
    assert road_task_records(raw,'edge-records',{7:(10,11),9:(11,12)}) is raw


def test_native_namespaces_map_only_through_shared_edge_ids():
    raw=[[(1,2),(2,3)],[]]
    rows=road_task_records(raw,'node-pairs',{7:(100,101),9:(101,102)},
                          {7:(1,2),9:(2,3)})
    assert rows[0]['cpath']==[7,9]
    assert len(rows)==2 and rows[1]['accepted'] is False
    assert raw==[[(1,2),(2,3)],[]]


def test_native_ambiguous_mapping_rejected():
    with pytest.raises(ValueError,match='Ambiguous'):
        road_task_records([[(1,2)]],'node-pairs',{7:(10,11),9:(10,11)},
                          {7:(1,2),9:(1,2)})


def test_native_disconnected_route_not_filled():
    with pytest.raises(ValueError,match='disconnected'):
        road_task_records([[(1,2),(3,4)]],'node-pairs',{7:(10,11),9:(12,13)},
                          {7:(1,2),9:(3,4)})

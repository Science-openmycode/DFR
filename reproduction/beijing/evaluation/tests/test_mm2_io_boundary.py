import json
import pickle
from pathlib import Path
import numpy as np
import pytest
from algorithms.routers.mm2_mdp_adapter import convert_rows, run_mm2
from preprocess.public_routing_contract import validate, sha


def test_raw_disconnect_not_hidden_by_canonical_node_merges():
    rows=[dict(id='0',aborted='no',duration='1',match='LINESTRING(0 0,1 1)',edge_ids='2,3')]
    routes,reasons=convert_rows(rows,{1:(10,20),2:(20,30)},1,{1:(100,200),2:(201,300)})
    assert not routes[0]['accepted'] and reasons=={'disconnected':1}


def test_gapped_geometry_not_accepted():
    rows=[dict(id='0',aborted='no',duration='1',match='MULTILINESTRING((0 0,1 1))',edge_ids='2')]
    assert convert_rows(rows,{1:(1,2)},1)[1]=={'gapped_geometry':1}


def test_all_skipped_keeps_slots_without_executing_native(tmp_path,monkeypatch):
    def unexpected(*args,**kwargs):raise AssertionError('Native must not run for no eligible coordinates')
    monkeypatch.setattr('algorithms.routers.mm2_mdp_adapter.subprocess.run',unexpected)
    data=tmp_path/'measurement.pkl';data.write_bytes(pickle.dumps([np.empty((0,2)),np.array([[1.,2.]])]))
    cache=tmp_path/'cache.pkl';cache.write_bytes(pickle.dumps({'edge_nodes':{1:(1,2)}}))
    binary=tmp_path/'mm2.exe';binary.write_bytes(b'not executed')
    network=tmp_path/'network';network.mkdir()
    m=run_mm2(data,tmp_path/'out',executable=binary,network=network,edge_cache=cache)
    assert m['records']==2 and m['mm2_executed'] is False
    assert m['reasons']['invalid_input_coordinate']==2


@pytest.mark.parametrize('bad',[None,'private-path','population','changed-M','public'])
def test_public_routing_contract_never_requires_private_files(tmp_path,bad):
    d=tmp_path/'M';d.mkdir();(d/'measurement.pkl').write_bytes(b'M bytes')
    meta=dict(status='VALID',M='SPRT',epsilon=1.4,public_slot_count=2,input_sha256='approved-population',
              outputs={'measurement.pkl':sha(d/'measurement.pkl')})
    if bad=='population':meta['input_sha256']='old'
    (d/'measurement_manifest.json').write_text(json.dumps(meta))
    public=tmp_path/'public';public.write_bytes(b'public')
    files={name:sha(d/name) for name in ('measurement.pkl','measurement_manifest.json')}
    c=dict(dataset_policy='saved-dp-measurement-public-r-only',frozen_dataset_id='id',slots=2,epsilon=1.4,
        paths={},routing_inputs={'SPRT':'M'},public_routing_contract=dict(schema='verified-measurement-public-routing-v1',
        dataset_id='id',slots=2,population_input_sha256='approved-population',measurements={'SPRT':files},public_files={'public':sha(public)}))
    if bad=='private-path':c['paths']['real']='MISSING_PRIVATE_FILE'
    if bad=='changed-M':(d/'measurement.pkl').write_bytes(b'changed')
    if bad=='public':public.write_bytes(b'changed')
    if bad:
        with pytest.raises(ValueError):validate(c,tmp_path,'SPRT')
    else:
        assert validate(c,tmp_path,'SPRT')==d

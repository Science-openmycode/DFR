"""Interface fixtures, not MTNet training or experimental scores."""
import gzip
import json
import pickle
import sys

import pytest
import register_mtnet as entry
from preprocess.dataset_contract import sha


@pytest.mark.parametrize('encoding',['utf-8','utf-8-sig'])
def test_readme_registration_accepts_powershell_json(tmp_path,monkeypatch,encoding):
    monkeypatch.setattr(entry,'ROOT',tmp_path)
    monkeypatch.setattr(entry,'validate_dataset',lambda p:{'dataset_id':'fixture'})
    def save(path,value):
        path.write_text(json.dumps(value),encoding=encoding)
        return path
    source=tmp_path/'native';source.mkdir()
    raw=source/'routes.pkl';raw.write_bytes(pickle.dumps([[1,2],[]]))
    cache=tmp_path/'cache.pkl.gz'
    with gzip.open(cache,'wb') as f:pickle.dump({'edge_nodes':{1:(10,11),2:(11,12)}},f)
    network=tmp_path/'network.shp';network.write_bytes(b'fixture-public-network')
    prep=save(tmp_path/'prep.json',{'fixture':True})
    model=tmp_path/'model.pt';model.write_bytes(b'fixture-model')
    save(source/'manifest.json',dict(generated_records=2,routes_sha256=sha(raw),
        post_generation_matching=False,private_input_access_during_generation=False,
        preparation_manifest_sha256=sha(prep),model_sha256=sha(model)))
    config=save(tmp_path/'config.json',dict(frozen_dataset_id='fixture',slots=2,batch='test',
        paths=dict(prepared='prepared',network=str(network),edge_cache=str(cache),output='results')))
    out=tmp_path/'registered'
    monkeypatch.setattr(sys,'argv',['register_mtnet.py','--config',str(config),'--source',str(source),
        '--preparation',str(prep),'--model',str(model),'--out',str(out)])
    entry.main()
    with gzip.open(out/'synthetic_routes.pkl.gz','rb') as f:rows=pickle.load(f)
    assert [r['cpath'] for r in rows]==[[1,2],[]]
    assert rows[0]['accepted'] is True and rows[1]['reason']=='empty_native_slot'
    meta=json.loads((out/'route_manifest.json').read_text())
    assert meta['records']==2 and meta['rematched'] is False and meta['gap_filling'] is False


@pytest.mark.parametrize('encoding',['utf-8','utf-8-sig'])
def test_source_collector_accepts_powershell_config_without_filling_missing(tmp_path,monkeypatch,encoding):
    from tools import collect_frozen_matrix as collector
    reference=tmp_path/'roads.bin';reference.write_bytes(b'fixture-road-reference')
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(slots=2,train_slots=1,test_slots=1,
        frozen_dataset_id='fixture',paths={'real_routes':str(reference)})),encoding=encoding)
    spec=tmp_path/'spec.json'
    spec.write_text(json.dumps({'rows':['MTNet'],'columns':['BTF']}),encoding='utf-8')
    batch=tmp_path/'empty_batch';batch.mkdir()
    out=tmp_path/'sources'
    monkeypatch.setattr(sys,'argv',['collect_frozen_matrix.py','--config',str(config),
        '--batch',str(batch),'--spec',str(spec),'--out',str(out)])
    collector.main()
    report=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert report['population']['dataset_id']=='fixture'
    assert report['population']['real_sha256']==sha(reference)
    assert report['counts']=={'MISSING':1}

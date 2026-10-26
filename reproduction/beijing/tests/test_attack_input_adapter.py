import json
import pickle
import numpy as np
import prepare_attack_inputs as adapter

def test_original_sampler_small_fixture(tmp_path,monkeypatch):
    dataset=tmp_path/'dataset';dataset.mkdir()
    for key,indices in [('train',[0,1,2,3]),('test',[4,5,6,7])]:
        (dataset/(key+'.pkl')).write_bytes(pickle.dumps([np.array([[i,1.],[i,2.]]) for i in indices]))
        (dataset/(key+'_split.json')).write_text(json.dumps({'indices':indices}))
    cfg=tmp_path/'config.json';cfg.write_text(json.dumps({'paths':{'prepared':str(dataset)},'frozen_dataset_id':'fixture'}))
    coords=tmp_path/'coords.pkl';coords.write_bytes(b'fixture')
    lineage=tmp_path/'lineage.json';lineage.write_text('{}')
    releases=tmp_path/'releases.json';releases.write_text(json.dumps({'fixture':{'coordinates':str(coords),'lineage':str(lineage)}}))
    monkeypatch.setattr(adapter,'validate_dataset',lambda p:{'dataset_id':'fixture'})
    adapter.prepare(cfg,tmp_path/'attack',tmp_path/'bound.json',releases)
    m=json.loads((tmp_path/'attack/split/manifest.json').read_text())
    assert m['attack_candidate_count_per_class']==2
    assert m['reference_count']==2
    assert set(m['source_indices']['nonmember_candidates']).isdisjoint(m['source_indices']['reference'])
    assert json.loads((tmp_path/'bound.json').read_text())['attack_resources_status']=='PREPARED_CURRENT_TRAIN_SPLIT'

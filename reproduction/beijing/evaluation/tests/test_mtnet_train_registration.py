import json
import pytest

from register_mtnet import validate_training_preparation
from preprocess.dataset_contract import sha


def fixture(tmp_path):
    files={}
    for name in ('real','train','test','split_audit'):
        files[name]=tmp_path/(name+'.json')
        files[name].write_text(name)
    (tmp_path/'train_split.json').write_text(json.dumps(dict(indices=[3,1])))
    files['split_audit'].write_text(json.dumps(dict(status='passed',
        all_source_indices_used_once=True,full_sha256=sha(files['real']),
        train_sha256=sha(files['train']),test_sha256=sha(files['test']))))
    binding=dict(split_audit_sha256=sha(files['split_audit']),
        train_sha256=sha(files['train']),test_sha256=sha(files['test']),
        train_indices_sha256=sha(tmp_path/'train_split.json'))
    config=dict(frozen_dataset_id='test-dataset',train_slots=2)
    meta=dict(dataset_id='test-dataset',evaluation_scope='strict_tstr',input_count=2,
        input_sha256=sha(files['train']),selected_frozen_indices=[3,1],split_binding=binding)
    return files,config,meta


@pytest.mark.parametrize('corruption',[None,'scope','indices','dataset','input','split'])
def test_train_registration_rejects_wrong_population(tmp_path,corruption):
    files,config,meta=fixture(tmp_path)
    if corruption=='scope':meta['evaluation_scope']='full_corpus'
    if corruption=='indices':meta['selected_frozen_indices']=[1,3]
    if corruption=='dataset':meta['dataset_id']='old'
    if corruption=='input':meta['input_sha256']=sha(files['real'])
    if corruption=='split':meta['split_binding']['test_sha256']='wrong'
    prep=tmp_path/'prep.json';prep.write_text(json.dumps(meta))
    if corruption is None:
        validate_training_preparation(prep,tmp_path,config,files.__getitem__)
    else:
        with pytest.raises(ValueError,match='train-only'):
            validate_training_preparation(prep,tmp_path,config,files.__getitem__)

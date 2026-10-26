import json
import pytest
from tools.finalize_mtnet_lineage import finalize
from prepare_remote_tstr import parse_cell
from preprocess.dataset_contract import sha


def test_only_native_origin_export_supported():
    assert parse_cell('MTNet/Origin')==('MTNet','Origin')
    with pytest.raises(ValueError):parse_cell('MTNet/FMM')


@pytest.mark.parametrize('bad',[None,'exit','epochs','model','scope'])
def test_finalize_requires_execution_and_binding(tmp_path,monkeypatch,bad):
    import tools.finalize_mtnet_lineage as module
    # Population checks have their own negative tests; isolate execution checks.
    monkeypatch.setattr(module,'validate_training_preparation',lambda *a:None)
    prep=tmp_path/'prep.json';prep.write_text(json.dumps(dict(split_binding=dict(train_sha256='train',test_sha256='test'))))
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(paths=dict(prepared=str(tmp_path)),train_slots=2,frozen_dataset_id='frozen')))
    d=tmp_path/'native';d.mkdir();(d/'native_release').mkdir()
    for f in ('model.pt','paper_algorithm_manifest.json','native_release/routes.pkl'):(d/f).write_text(f)
    receipt=dict(real_exit_code=1 if bad=='exit' else 0,stdout_completion=['done'],command='executed',evidence_scope='observed session')
    (d/'execution_observation.json').write_text(json.dumps(receipt))
    (d/'training.log').write_text('\n'.join(json.dumps(dict(epoch=i,steps=1)) for i in range(29 if bad=='epochs' else 30)))
    binding=dict(evaluation_scope='full' if bad=='scope' else 'strict_tstr',dataset_id='frozen',public_slot_count=2,
        split_binding=json.loads(prep.read_text())['split_binding'],preparation_manifest_sha256=sha(prep),files={'train_native_mtnet_dpsgd_paper.py':'code'})
    (d/'deployment_binding.json').write_text(json.dumps(binding))
    native=dict(preparation_manifest_sha256=sha(prep),generated_records=2,routes_sha256=sha(d/'native_release/routes.pkl'),
        model_sha256='wrong' if bad=='model' else sha(d/'model.pt'),post_generation_matching=False,private_input_access_during_generation=False,
        epsilon_training=1.4,delta_training=1e-5,privacy_scope='prepared-aligned')
    (d/'native_release/manifest.json').write_text(json.dumps(native))
    if bad:
        with pytest.raises(ValueError):finalize(d,prep,config)
        assert not (d/'lineage.json').exists()
    else:
        finalize(d,prep,config)
        record=json.loads((d/'lineage.json').read_text())
        assert record['returncode']==0 and record['outputs']['model.pt']==sha(d/'model.pt')
        with pytest.raises(FileExistsError):finalize(d,prep,config)

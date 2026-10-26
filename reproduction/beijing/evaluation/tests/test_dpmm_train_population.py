import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from preprocess.dpmm_population import population_input,validation_indices


def test_train_selects_only_frozen_train_path(tmp_path):
    (tmp_path/'canonical_manifest.json').write_text(json.dumps({'artifacts':{'train.pkl':'train-hash','trajectories.pkl':'full-hash'}}))
    identity={'train_count':80,'count':100}
    assert population_input(tmp_path,identity,'train')==(tmp_path/'train.pkl',80,'train-hash')
    assert population_input(tmp_path,identity)==(tmp_path/'trajectories.pkl',100,'full-hash')


def test_test_set_cannot_be_selected(tmp_path):
    with pytest.raises(ValueError):population_input(tmp_path,{},'test')


def test_exact_sixty_includes_longest_and_is_deterministic():
    data=[range((i*7)%111) for i in range(200)]
    selected=validation_indices(data,50,60)
    assert len(selected)==len(set(selected))==60
    assert selected==validation_indices(data,50,60)
    assert set(sorted(range(200),key=lambda i:len(data[i]),reverse=True)[:10])<=set(selected)


@pytest.mark.parametrize('count',[59,201])
def test_invalid_exact_sample_rejected(count):
    with pytest.raises(ValueError):validation_indices([range(2)]*200,50,count)

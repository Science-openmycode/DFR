from pathlib import Path
import pytest
from tools.finalize_mtnet_lineage import model_directory
from tools.prepare_dpmm_train_evaluation import is_train_generation


@pytest.mark.parametrize('exe',['python','.venv/Scripts/python.exe','"C:/含 空格/python.exe"'])
def test_documented_interpreter(exe):
    assert is_train_generation(exe+' synthesize_dpmm.py --split train --out x')


@pytest.mark.parametrize('tail',['--split full','--split train --split full','--split','--split trainer'])
def test_reject_wrong_population(tail):
    assert not is_train_generation('python synthesize_dpmm.py '+tail)


def test_model_layouts(tmp_path):
    with pytest.raises(ValueError):model_directory(tmp_path)
    (tmp_path/'trained').mkdir()
    (tmp_path/'trained/model.pt').touch()
    assert model_directory(tmp_path)==tmp_path/'trained'
    (tmp_path/'model.pt').touch()
    with pytest.raises(ValueError):model_directory(tmp_path)
    (tmp_path/'trained/model.pt').unlink()
    assert model_directory(tmp_path)==tmp_path

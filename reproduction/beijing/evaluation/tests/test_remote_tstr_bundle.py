from pathlib import Path
import pytest
from prepare_remote_tstr import safe_relative,parse_cell


@pytest.mark.parametrize('value',['../secret','inputs/../../secret'])
def test_bundle_rejects_path_escape(value):
    with pytest.raises(ValueError):safe_relative(value)


def test_bundle_relative_path_keeps_hierarchy():
    assert safe_relative('legacy/evaluation/file.py')==Path('legacy/evaluation/file.py')


@pytest.mark.parametrize('value',['../Origin','DPMM/FMM','SPRT/MM2','SPRT/FMM/extra'])
def test_rejects_unknown_or_native_rematching_cells(value):
    with pytest.raises(ValueError):parse_cell(value)


def test_cell_keeps_m_and_r_separate():
    assert parse_cell('PrivTrace/STMatch')==('PrivTrace','STMatch')

import hashlib
import pytest
from tools.check_documented_command import check

EXPECTED='python route.py --config configs/test.json --method DPStd --router FMM'


def fixture(tmp_path):
    doc=tmp_path/'run.md'
    doc.write_text('# Plan\n\n```powershell\n'+EXPECTED+'\n```\n',encoding='utf-8')
    return doc,hashlib.sha256(doc.read_bytes()).hexdigest()


def test_exact_outer_command_passes_without_executing(tmp_path):
    doc,digest=fixture(tmp_path)
    assert check(doc,4,EXPECTED,digest)==EXPECTED


@pytest.mark.parametrize('actual',[
    'python run.py route-cell --config configs/test.json --method DPStd --router FMM',
    'fmm.exe --network network.shp --gps gps.csv',
    EXPECTED+' --candidates 8',
    EXPECTED.replace('configs/test.json','configs/server.json'),
    EXPECTED.replace('python ','E:/anconda/python.exe '),
    EXPECTED.replace('--method DPStd --router FMM','--router FMM --method DPStd'),
    EXPECTED+' ',
    EXPECTED+'\npython other.py',
])
def test_any_text_or_entrypoint_change_rejected(tmp_path,actual):
    doc,digest=fixture(tmp_path)
    with pytest.raises(ValueError):check(doc,4,actual,digest)


def test_document_rewrite_cannot_make_a_changed_command_pass(tmp_path):
    doc,digest=fixture(tmp_path)
    replacement=EXPECTED.replace('route.py','run.py')
    doc.write_text('```powershell\n'+replacement+'\n```')
    with pytest.raises(ValueError,match='Document changed'):check(doc,2,replacement,digest)


def test_prose_is_not_a_command(tmp_path):
    doc,digest=fixture(tmp_path)
    with pytest.raises(ValueError):check(doc,1,'# Plan',digest)


def test_template_is_not_a_concrete_command(tmp_path):
    doc=tmp_path/'template.md';doc.write_text('```powershell\npython route.py --method <M>\n```')
    digest=hashlib.sha256(doc.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='template'):check(doc,2,'python route.py --method <M>',digest)

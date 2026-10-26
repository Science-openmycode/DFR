import hashlib
import json
from pathlib import Path
import importlib.util
import pytest

spec=importlib.util.spec_from_file_location('final_output_integrity', Path(__file__).parents[2]/'tools/verify_current_final_outputs.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('style', ['filename', 'remote-path', 'result'])
def test_output_styles(tmp_path, style):
    data=b'example'
    (tmp_path/'metrics.json').write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    meta={'outputs': {'metrics.json':sha}}
    if style=='remote-path':
        meta={'outputs':{'metrics_json':{'path':r'D:\MTR\run\metrics.json','sha256':sha}}}
    elif style=='result':
        meta={'result_sha256':sha}
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps(meta),encoding='utf-8')
    assert len(module.verify_outputs(path))==1
    (tmp_path/'metrics.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash differs'):
        module.verify_outputs(path)


def test_missing_and_no_binding(tmp_path):
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps({'outputs':{'metrics.json':'0'*64}}))
    with pytest.raises(ValueError,match='Missing final output'):
        module.verify_outputs(path)
    path.write_text('{}')
    with pytest.raises(ValueError,match='No recognized'):
        module.verify_outputs(path)

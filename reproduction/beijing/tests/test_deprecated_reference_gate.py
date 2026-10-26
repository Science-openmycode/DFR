import json
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

@pytest.mark.parametrize('script,arguments', [
    ('synthesize.py', ['--method','SPRT']),
    ('route.py', ['--method','SPRT','--router','Nearest']),
    ('evaluate_tstr.py', ['--method','SPRT']),
])
def test_deprecated_reference_blocks_all_dataset_consumers(script, arguments, tmp_path):
    root=Path(__file__).resolve().parents[1]
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'road_reference_status':'DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING'}),encoding='utf-8')
    result=subprocess.run([sys.executable,'-X','utf8',str(root/script),*arguments,'--config',str(config)],
                          capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 2
    assert 'road reference' in result.stderr.lower()
    assert list(tmp_path.iterdir()) == [config]

def test_deprecated_reference_is_rejected_before_loading_data():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        config=Path(directory)/'config.json'
        config.write_text(json.dumps({'road_reference_status':'DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING'}),encoding='utf-8')
        run=subprocess.run([sys.executable,'-X','utf8',str(root/'evaluate.py'),'--method','SPRT','--router','Nearest',
                            '--config',str(config)],capture_output=True,text=True,encoding='utf-8')
        assert run.returncode==2
        assert 'road reference' in run.stderr.lower()
        assert list(Path(directory).iterdir())==[config]

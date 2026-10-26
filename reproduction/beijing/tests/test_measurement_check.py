import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
from test_dataset_contract import fixture

def test_cli_checks_actual_count_and_rejects_wrong_source(tmp_path):
    prepared=tmp_path/'prepared';prepared.mkdir();meta=fixture(prepared)
    dataset_id=hashlib.sha256((prepared/'canonical_manifest.json').read_bytes()).hexdigest()
    root=Path(__file__).resolve().parents[1]
    result=tmp_path/'results'/'new'/'measurements'/'SPRT';result.mkdir(parents=True)
    source_sha=hashlib.sha256((prepared/'trajectories.pkl').read_bytes()).hexdigest()
    data=result/'measurement.pkl';data.write_bytes(pickle.dumps([[[0.,0.],[0.,1.]],[[1.,0.],[1.,1.]]]))
    manifest=dict(input_sha256=source_sha,epsilon=1.4,seed=42,public_slot_count=2,
                  outputs={'measurement.pkl':hashlib.sha256(data.read_bytes()).hexdigest()})
    path=result/'measurement_manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(paths={'prepared':str(prepared),'output':str(tmp_path/'results')},
        frozen_dataset_id=dataset_id,epsilon=1.4,seed=42,batch='new')),encoding='utf-8')
    out=tmp_path/'audit.json'
    command=[sys.executable,'-X','utf8',str(root/'check_measurements.py'),'--config',str(config),'--methods','SPRT','--out',str(out)]
    first=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
    assert first.returncode==0,first.stderr
    assert json.loads(out.read_text(encoding='utf-8'))['methods'][0]['records']==2
    manifest['input_sha256']='wrong';path.write_text(json.dumps(manifest),encoding='utf-8')
    command[-1]=str(tmp_path/'bad.json')
    second=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
    assert second.returncode!=0
    assert 'wrong input' in second.stderr
    assert not (tmp_path/'bad.json').exists()

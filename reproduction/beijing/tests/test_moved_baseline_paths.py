"""Only exercise relocated input/CLI wiring; no author model generation."""
import json
from pathlib import Path
import pickle
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def test_adatrace_prepare_uses_config_paths_without_java(tmp_path):
    data=tmp_path/'real.pkl'
    trajectories=[np.array([[39.9,116.3],[39.91,116.31]])]
    data.write_bytes(pickle.dumps(trajectories))
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(slots=1,paths=dict(real=str(data)))))
    out=tmp_path/'prepared'
    subprocess.run([sys.executable,str(ROOT/'adatrace.py'),'prepare','--config',str(config),'--out',str(out)],check=True)
    m=json.loads((out/'input_manifest.json').read_text())
    assert m['slots']==1 and m['roundtrip_max_degrees']<1e-8
    assert len((out/'input.dat').read_text().splitlines())==2

def test_adatrace_current_synthesize_dry_run_is_local(tmp_path):
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(dataset='beijing',batch='test',epsilon=1,seed=42,slots=1,bbox=[39,40,116,117],paths=dict(output=str(tmp_path),prepared=str(tmp_path)))))
    r=subprocess.run([sys.executable,str(ROOT/'synthesize.py'),'--config',str(config),'--method','AdaTrace','--dry-run'],capture_output=True,text=True,check=True)
    result=json.loads(r.stdout)
    assert result['command'][3].endswith('adatrace.py')
    assert result['command'][4]=='generate'
    assert result['prepare_command'][4]=='prepare'
    assert not (tmp_path/'test').exists()

def test_no_experiment_host_paths_in_moved_adapters():
    for name in ('adatrace.py','dptraj_pm.py'):
        text=(ROOT/name).read_text(encoding='utf-8')
        assert 'D:/MTR/' not in text and 'C:/MTR_' not in text

def test_matrix_methods_and_parameter_names():
    spec=json.loads((ROOT/'reference_results/matrix/spec_current_methods.json').read_text(encoding='utf-8'))
    assert len(spec['columns'])==11
    assert 'MTNet' in spec['rows'] and 'MTNet_DP_OD_coarse24' in spec['rows']
    assert all('64' not in row for row in spec['rows'])

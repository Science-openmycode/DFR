import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


def load():
    file = Path(__file__).resolve().parents[1]/'legacy/evaluation/evaluation/metric_suites/road_route.py'
    spec = importlib.util.spec_from_file_location('fmm_execution_safety_module', file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('failure', [False, True])
def test_live_logs_no_table_copy_and_failure_evidence(tmp_path, monkeypatch, failure):
    module = load()
    from pyproj import CRS
    monkeypatch.setattr(module, 'network_metadata', lambda _: ({10:(1,2)}, CRS.from_epsg(32650)))
    monkeypatch.setattr(module, '_copy_shapefile', lambda *a: None)
    monkeypatch.setattr(module, '_copy_runtime', lambda f,u,r,s: (s/'fmm.exe',None))
    monkeypatch.setattr(module, '_link_or_copy', lambda *a: pytest.fail('ASCII table should be read in place'))
    # Keep native fixture paths ASCII even when the checkout contains Chinese.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='fmm_wrapper_') as directory:
        root=Path(directory)
        table=root/'ubodt.txt'; table.write_text('fixture')
        def run(command, **kwargs):
            assert 'capture_output' not in kwargs
            assert command[command.index('--ubodt')+1] == str(table.resolve())
            assert command[command.index('--radius')+1] == '200'
            kwargs['stdout'].write('native progress\n'); kwargs['stdout'].flush()
            assert (root/'matcher.stdout.log').read_text() == 'native progress\n'
            if failure: raise subprocess.CalledProcessError(7, command)
            Path(command[command.index('--output')+1]).write_text('id;cpath\n0;10\n1;\n')
            return subprocess.CompletedProcess(command,0)
        monkeypatch.setattr(module.subprocess,'run',run)
        args=([np.array([[39.,116.],[39.1,116.1]])]*2,root/'network.shp',table,
              root/'fmm.exe',None,None,32,200,50,8,.95,root,True)
        if failure:
            with pytest.raises(RuntimeError,match='evidence retained'):
                module.run_fmm(*args)
            stages=list(root.glob('mtr_road_metric_*'))
            assert len(stages)==1 and (stages[0]/'gps.csv').exists()
            assert json.loads((stages[0]/'failure.json').read_text())['status']=='FAILED'
        else:
            records,invocation=module.run_fmm(*args)
            assert len(records)==2 and records[0].cpath==(10,) and not records[1].accepted
            assert invocation['returncode']==0
            assert not list(root.glob('mtr_road_metric_*'))
        assert (root/'matcher.stdout.log').is_file()


@pytest.mark.parametrize('include_stmatch',[False,True])
def test_installer_preserves_parameters_and_backups(tmp_path,monkeypatch,include_stmatch):
    import hashlib
    file=Path(__file__).resolve().parents[1]/'tools/install_fmm_safety.py'
    spec=importlib.util.spec_from_file_location('install_fmm_test',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=tmp_path/'reproduction/beijing';root.mkdir(parents=True)
    source=tmp_path/'public_assets/matcher/fmm.exe';source.parent.mkdir(parents=True)
    source.write_bytes(b'tested fixture binary')
    target=root/'resources/fmm/fmm.exe';target.parent.mkdir(parents=True)
    target.write_bytes(b'previous fixture binary')
    st_source=source.parent/'stmatch.exe';st_source.write_bytes(b'new stmatch')
    st_target=root/'resources/stmatch/stmatch.exe';st_target.parent.mkdir(parents=True);st_target.write_bytes(b'old stmatch')
    (target.parent/'safety_build.json').write_text(json.dumps({'fmm_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
       'stmatch_sha256':hashlib.sha256(st_source.read_bytes()).hexdigest()}))
    config=root/'config.json'
    original={'paths':{'fmm':'resources/fmm/fmm.exe','stmatch':'resources/stmatch/stmatch.exe'},'epsilon':1.4,'seed':42,'threads':4,
              'matcher_compatibility':{'fmm_sha256':'old','stmatch_sha256':'unchanged'}}
    config.write_text(json.dumps(original))
    monkeypatch.setattr(module,'ROOT',root)
    monkeypatch.setattr(sys,'argv',['install_fmm_safety.py','--config',str(config)]+(['--include-stmatch'] if include_stmatch else []))
    import psutil
    monkeypatch.setattr(psutil,'process_iter',lambda *a: [])
    module.main()
    updated=json.loads(config.read_text())
    assert all(updated[k]==original[k] for k in ['paths','epsilon','seed','threads'])
    if include_stmatch:
        assert updated['matcher_compatibility']['stmatch_sha256']==hashlib.sha256(st_source.read_bytes()).hexdigest()
        assert st_target.read_bytes()==st_source.read_bytes()
    else:
        assert updated['matcher_compatibility']['stmatch_sha256']=='unchanged'
        assert st_target.read_bytes()==b'old stmatch'
    assert target.read_bytes()==source.read_bytes()
    backup=Path(updated['fmm_safety_build']['backup'])
    assert (backup/'fmm.before.exe').read_bytes()==b'previous fixture binary'
    assert json.loads((backup/'config.before.json').read_text())==original
    if include_stmatch:assert (backup/'stmatch.before.exe').read_bytes()==b'old stmatch'


def test_shipped_fmm_copies_match_the_tested_build():
    import hashlib
    root=Path(__file__).resolve().parents[1]
    expected=json.loads((root/'resources/fmm/safety_build.json').read_text())['fmm_sha256']
    for binary in (root/'resources/fmm/fmm.exe',root.parents[1]/'public_assets/matcher/fmm.exe'):
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected



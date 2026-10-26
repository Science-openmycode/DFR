import copy
from pathlib import Path

import pytest

from prepare_mtnet_deployment import deployment_population


def train_meta():
    return dict(input_count=12584,original_loader_counts={'trainable':100},
                evaluation_scope='strict_tstr',full_population_count=15730,
                selected_frozen_indices=list(range(12584)),input_sha256='train',
                split_binding=dict(split_audit_sha256='audit',train_sha256='train',
                                   test_sha256='test',train_indices_sha256='indices'))


def test_train_deployment_requires_explicit_train_only_flag():
    assert deployment_population(train_meta(),True)==12584
    with pytest.raises(ValueError):
        deployment_population(train_meta())


def test_old_full_preparation_is_still_accepted_for_full_only():
    full=dict(input_count=15730,original_loader_counts={'trainable':852})
    assert deployment_population(full)==15730
    with pytest.raises(ValueError):
        deployment_population(full,True)


@pytest.mark.parametrize('field,value',[
    ('evaluation_scope','full_corpus'),('full_population_count',100),
    ('input_sha256','test'),('selected_frozen_indices',[0]*12584),
    ('split_binding',{}),('original_loader_counts',{'trainable':0})])
def test_train_export_rejects_wrong_or_incomplete_binding(field,value):
    meta=copy.deepcopy(train_meta());meta[field]=value
    with pytest.raises(ValueError):
        deployment_population(meta,True)


def test_runner_preserves_training_parameters_and_uses_bound_slot_count():
    script=(Path(__file__).resolve().parents[2]/'deployment/RUN_MTNET_GPU.ps1').read_text()
    assert "'--epochs','30'" in script
    assert "'--target-epsilon','1.4','--target-delta','0.00001'" in script
    assert "'--microbatch-size','1'" in script
    assert "'--public-slot-count',[string]$slots" in script
    assert "$binding.evaluation_scope -notin @('full_corpus','strict_tstr')" in script
    assert '-WindowStyle Hidden' in script


def test_resume_runner_uses_explicit_root_and_bound_population():
    script=(Path(__file__).resolve().parents[2]/'deployment/RUN_MTNET_GPU_RESUME.ps1').read_text()
    assert "D:/MTR" not in script
    assert '[Parameter(Mandatory=$true)]' in script
    assert "'--public-slot-count',[string]$slots" in script
    assert "$binding.evaluation_scope -notin @('full_corpus','strict_tstr')" in script


def test_clean_setup_installs_base_lock_before_gpu():
    script=(Path(__file__).resolve().parents[2]/'deployment/SETUP_MTNET_GPU.ps1').read_text()
    assert 'requirements-clean-windows-py313.txt' in script
    assert script.index("'-r',$requirements") < script.index("'-r',$gpuRequirements")
    assert 'requirements-gpu-windows-py313.txt' in script
    assert "@('-m','pip','check')" in script
    assert '-RedirectStandardError $stderr' in script
    assert '$process.ExitCode -ne 0' in script
    assert '--system-site-packages' not in script
    assert 'sys.version_info[:2] == (3,13)' in script
    assert 'sys.prefix != sys.base_prefix' in script
    assert "[Guid]::NewGuid().ToString('N')" in script
    assert "$stdout=Join-Path $logRoot" in script
    assert "Invoke-SetupStep 'environment_freeze'" in script
    assert script.index('Existing environment is not') < script.index("Invoke-SetupStep 'base_dependencies'")


def test_windows_native_arguments_roundtrip(tmp_path):
    import json
    import subprocess
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows native argv contract')
    root=Path(__file__).resolve().parents[2]
    probe=tmp_path/'probe with spaces.py'
    probe.write_text('import json,sys; print(json.dumps(sys.argv[1:]))',encoding='utf-8')
    values=['plain','with spaces','', 'quote"inside', 'C:\\ends with slash\\', '北京目录']
    request=tmp_path/'args.json'
    request.write_text(json.dumps([str(probe),*values]),encoding='utf-8')
    output=tmp_path/'stdout.txt';error=tmp_path/'stderr.txt'
    def literal(value):return "'"+str(value).replace("'","''")+"'"
    script=tmp_path/'roundtrip.ps1'
    script.write_text(
        ". "+literal(root/'deployment/NativeArguments.ps1')+"\n"
        "$values=Get-Content -Raw -Encoding UTF8 "+literal(request)+" | ConvertFrom-Json\n"
        "$p=Start-Process -FilePath "+literal(sys.executable)+
        " -ArgumentList (ConvertTo-NativeArguments $values) -WindowStyle Hidden -Wait -PassThru"
        " -RedirectStandardOutput "+literal(output)+" -RedirectStandardError "+literal(error)+"\nexit $p.ExitCode\n",
        encoding='utf-8-sig')
    result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,timeout=30)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert json.loads(output.read_text(encoding='utf-8-sig'))==values


def test_export_contains_setup_closure_and_bound_hashes(tmp_path,monkeypatch):
    import hashlib
    import json
    import sys
    import zipfile
    from prepare_mtnet_deployment import main
    prepared=tmp_path/'prepared';original=tmp_path/'original'
    data=prepared/'data/beijing_roads_l20';data.mkdir(parents=True)
    (data/'fixture.txt').write_bytes(b'isolated test data, not an experiment')
    meta=dict(input_count=15730,original_loader_counts={'trainable':852},dataset_id='fixture',
              data_files_sha256={'fixture.txt':hashlib.sha256((data/'fixture.txt').read_bytes()).hexdigest()})
    (prepared/'full_preparation_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    (prepared/'public_origin_ids.npy').write_bytes(b'fixture')
    (original/'official').mkdir(parents=True)
    source_files={}
    for name in ('mtnet.py','train.py','util/config.py'):
        source=original/'official'/name;source.parent.mkdir(parents=True,exist_ok=True)
        source.write_text('# fixture',encoding='utf-8')
        source_files[name]=hashlib.sha256(source.read_bytes()).hexdigest().upper()
    (original/'canonical_mtnet_source_lock.json').write_text(json.dumps({'files_sha256':source_files}),encoding='utf-8')
    (original/'train_native_mtnet_dpsgd_paper.py').write_text('# fixture',encoding='utf-8')
    out=tmp_path/'export with spaces';archive=tmp_path/'export.zip'
    monkeypatch.setattr(sys,'argv',['prepare_mtnet_deployment.py','--prepared',str(prepared),
        '--original-root',str(original),'--out',str(out),'--archive',str(archive)])
    # Reject source drift before creating an export or archive.
    (original/'official/mtnet.py').write_text('# altered',encoding='utf-8')
    with pytest.raises(ValueError,match='source lock changed'):
        main()
    assert not out.exists() and not archive.exists()
    (original/'official/mtnet.py').write_text('# fixture',encoding='utf-8')
    main()
    binding=json.loads((out/'deployment_binding.json').read_text(encoding='utf-8'))
    required={'RUN_MTNET_GPU.ps1','RUN_MTNET_GPU_RESUME.ps1','SETUP_MTNET_GPU.ps1',
              'NativeArguments.ps1','requirements-clean-windows-py313.txt','requirements-gpu-windows-py313.txt','generate_mtnet.py'}
    assert required <= set(binding['files'])
    with zipfile.ZipFile(archive) as z:
        assert required <= set(z.namelist())
        for name,digest in binding['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest

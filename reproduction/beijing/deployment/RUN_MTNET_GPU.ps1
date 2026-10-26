param([Parameter(Mandatory=$true)][string]$Root,[string]$PythonExecutable='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'NativeArguments.ps1')
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='1'
$python=if($PythonExecutable){$PythonExecutable}else{Join-Path $Root '.venv/Scripts/python.exe'}
$binding=Get-Content (Join-Path $Root 'deployment_binding.json') -Raw | ConvertFrom-Json
foreach($file in $binding.files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $Root $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value){throw "Deployment hash changed: $($file.Name)"}
}
$preflight=Start-Process -FilePath $python -ArgumentList @('-c','"import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"') -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'cuda_check.log') -RedirectStandardError (Join-Path $Root 'cuda_check.stderr.log')
if($preflight.ExitCode -ne 0){throw 'CUDA unavailable; do not silently switch to CPU'}
Get-Content (Join-Path $Root 'cuda_check.log')
$train=Join-Path $Root 'trained'
if(Test-Path -LiteralPath $train){throw 'Training output exists; no duplicate job'}
$n=$binding.training_count
$slots=if($binding.public_slot_count){[int]$binding.public_slot_count}else{[int]$binding.input_count}
if($slots -notin @(15730,12584)){throw 'Unexpected frozen population'}
if($slots -eq 12584 -and $binding.evaluation_scope -ne 'strict_tstr'){throw 'Missing training-only binding'}
Write-Output "START MTNet 30 epochs; training records=$n; evaluation population=$slots; microbatch=1"
$timer=[Diagnostics.Stopwatch]::StartNew()
$arguments=@((Join-Path $Root 'train_native_mtnet_dpsgd_paper.py'),'--mtnet-root',(Join-Path $Root 'official'),'--data-parent',(Join-Path $Root 'data'),'--city','beijing_roads_l20','--max-route-edges','20','--out',$train,'--epochs','30','--batch-size',[string]$n,'--clip-C','1','--target-epsilon','1.4','--target-delta','0.00001','--dataset-size-public','--release-condition-policy','public_fixed','--dp-domain-scope','prepared_aligned','--gradient-engine','vmap','--microbatch-size','1','--split-per','1','--progress-every','64','--loss-probe-size','128','--seed','20260712','--source-lock',(Join-Path $Root 'canonical_mtnet_source_lock.json'))
$process=Start-Process -FilePath $python -ArgumentList (ConvertTo-NativeArguments $arguments) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'training.log') -RedirectStandardError (Join-Path $Root 'training.stderr.log')
if($process.ExitCode -ne 0){throw "MTNet training failed with exit $($process.ExitCode); inspect separate stdout/stderr"}
Write-Output "DONE MTNet training seconds=$($timer.Elapsed.TotalSeconds)"
$generation=Start-Process -FilePath $python -ArgumentList (ConvertTo-NativeArguments @((Join-Path $Root 'generate_mtnet.py'),'--root',$Root,'--public-slot-count',[string]$slots)) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'generation.log') -RedirectStandardError (Join-Path $Root 'generation.stderr.log')
if($generation.ExitCode -ne 0){throw 'MTNet native generation failed'}
$observation = @{
    real_exit_code = $generation.ExitCode
    training_exit_code = $process.ExitCode
    stdout_completion = $true
    seconds = $timer.Elapsed.TotalSeconds
    command = @($python) + $arguments
    evidence_scope = 'Observed training and generation child exit codes in RUN_MTNET_GPU.ps1; command is training child argv, not an outer shell receipt'
}
$observation | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Root 'execution_observation.json') -Encoding UTF8
Write-Output "DONE MTNet native release total_seconds=$($timer.Elapsed.TotalSeconds)"

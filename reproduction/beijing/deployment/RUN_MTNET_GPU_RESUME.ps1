param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path
. (Join-Path $PSScriptRoot 'NativeArguments.ps1')
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='1'
$python=Join-Path $Root '.venv/Scripts/python.exe'
$binding=Get-Content (Join-Path $Root 'deployment_binding.json') -Raw|ConvertFrom-Json
foreach($file in $binding.files.PSObject.Properties){
 if((Get-FileHash -LiteralPath (Join-Path $Root $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value){throw "Original deployment changed: $($file.Name)"}
}
$train=Join-Path $Root 'trained'
$checkpoint=Join-Path $Root 'trained_private_training_state/epoch_boundary_checkpoint.pt'
if(-not (Test-Path -LiteralPath $checkpoint)){throw 'No complete epoch-boundary state to resume'}
if(Test-Path -LiteralPath (Join-Path $train 'model.pt')){throw 'Final model already exists; do not retrain'}
$n=[string]$binding.training_count
$slots=if($binding.public_slot_count){[int]$binding.public_slot_count}else{[int]$binding.input_count}
if($slots -lt 1 -or $slots -ne [int]$binding.input_count){throw 'Invalid prepared population'}
if($binding.evaluation_scope -notin @('full_corpus','strict_tstr')){throw 'Missing population scope'}
$preflight=Start-Process -FilePath $python -ArgumentList @('-c','"import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"') -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'cuda_resume_check.log') -RedirectStandardError (Join-Path $Root 'cuda_resume_check.stderr.log')
if($preflight.ExitCode -ne 0){throw 'CUDA resume check failed'}
Get-Content (Join-Path $Root 'cuda_resume_check.log')
$previous=Join-Path $Root 'training.first_epoch_warning_interrupt.log'
if(Test-Path -LiteralPath $previous){throw 'Resume runner already used; inspect its existing state rather than duplicate it'}
Copy-Item -LiteralPath (Join-Path $Root 'training.log') -Destination $previous
$arguments=@((Join-Path $Root 'train_native_mtnet_dpsgd_paper.py'),'--mtnet-root',(Join-Path $Root 'official'),'--data-parent',(Join-Path $Root 'data'),'--city','beijing_roads_l20','--max-route-edges','20','--out',$train,'--epochs','30','--batch-size',$n,'--clip-C','1','--target-epsilon','1.4','--target-delta','0.00001','--dataset-size-public','--release-condition-policy','public_fixed','--dp-domain-scope','prepared_aligned','--gradient-engine','vmap','--microbatch-size','1','--split-per','1','--progress-every','64','--loss-probe-size','128','--seed','20260712','--source-lock',(Join-Path $Root 'canonical_mtnet_source_lock.json'),'--resume')
Write-Output 'START MTNet resume from saved update boundary; still exactly 30 total epochs'
$timer=[Diagnostics.Stopwatch]::StartNew()
$process=Start-Process -FilePath $python -ArgumentList (ConvertTo-NativeArguments $arguments) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'training.log') -RedirectStandardError (Join-Path $Root 'training.stderr.log')
if($process.ExitCode -ne 0){throw "MTNet trainer returned exit $($process.ExitCode); inspect separate stdout/stderr"}
Write-Output "DONE MTNet remaining training seconds=$($timer.Elapsed.TotalSeconds)"
$generation=Start-Process -FilePath $python -ArgumentList (ConvertTo-NativeArguments @((Join-Path $Root 'generate_mtnet.py'),'--root',$Root,'--public-slot-count',[string]$slots)) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $Root 'generation.log') -RedirectStandardError (Join-Path $Root 'generation.stderr.log')
if($generation.ExitCode -ne 0){throw "MTNet generation failed with exit $($generation.ExitCode)"}
Write-Output "DONE native MTNet total continuation seconds=$($timer.Elapsed.TotalSeconds)"

param([Parameter(Mandatory=$true)][string]$Root,[string]$BasePython='python')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'NativeArguments.ps1')
$env:PYTHONUTF8='1'
# This dependency lock was validated on Python 3.13. Fail before creating or
# modifying an environment; silently resolving older dependencies is not valid.
& $BasePython -c "import sys; print(sys.version); sys.exit(0 if sys.version_info[:2] == (3,13) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'This delivery lock requires Python 3.13. Supply a compatible BasePython; no environment was changed.' }
New-Item -ItemType Directory -Path $Root -Force | Out-Null
$venv=Join-Path $Root '.venv'
$python=Join-Path $venv 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & $BasePython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'MTNet environment creation failed' }
}
& $python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,13) and sys.prefix != sys.base_prefix else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Existing environment is not an isolated Python 3.13 environment. Preserve it for diagnostics and use a fresh environment; dependencies were not changed.' }
$requirements=Join-Path $PSScriptRoot 'requirements-clean-windows-py313.txt'
if (-not (Test-Path -LiteralPath $requirements)) { $requirements=Join-Path (Split-Path -Parent $PSScriptRoot) 'requirements-clean-windows-py313.txt' }
if (-not (Test-Path -LiteralPath $requirements)) { throw 'Missing bundled clean dependency lock' }
$gpuRequirements=Join-Path (Split-Path -Parent $requirements) 'requirements-gpu-windows-py313.txt'
if (-not (Test-Path -LiteralPath $gpuRequirements)) { throw 'Missing bundled CUDA dependency lock' }
$logRoot=Join-Path $Root ('setup_logs/'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')+'_'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $logRoot | Out-Null
Write-Output ('SETUP_LOG_DIRECTORY='+$logRoot)
function Invoke-SetupStep {
    param([string]$Name,[string[]]$Values)
    $stdout=Join-Path $logRoot ($Name+'.stdout.log')
    $stderr=Join-Path $logRoot ($Name+'.stderr.log')
    $process=Start-Process -FilePath $python -ArgumentList (ConvertTo-NativeArguments $Values) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if ($process.ExitCode -ne 0) { throw "$Name failed with exit $($process.ExitCode); see $stdout and $stderr" }
}
# Install the Microsoft Visual C++ x64 runtime on this machine first (README).
# Loading torch in the computation check below verifies that prerequisite.
Invoke-SetupStep 'base_dependencies' @('-m','pip','install','--disable-pip-version-check','-r',$requirements)
Invoke-SetupStep 'cuda_dependencies' @('-m','pip','install','--disable-pip-version-check','-r',$gpuRequirements)
Invoke-SetupStep 'dependency_consistency' @('-m','pip','check')
& $python -c "import torch; print(torch.__version__); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); x=torch.ones(8,device='cuda'); print(x.sum().item())"
if ($LASTEXITCODE -ne 0) { throw 'CUDA computation test failed' }
Invoke-SetupStep 'environment_freeze' @('-m','pip','freeze')
Write-Output 'MTNET_GPU_ENVIRONMENT_READY_NOT_AN_EXPERIMENT_RESULT'

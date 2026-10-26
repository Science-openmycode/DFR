param([int]$TrainingSshProcessId=13980, [double]$MinimumFreeGiB=4.0, [switch]$InspectOnly)
$ErrorActionPreference='Stop'
if(-not $InspectOnly){throw 'Retired historical controller: use the documented independent commands; no historical queue may run from this delivery.'}
$env:PYTHONUTF8='1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot/MemoryGuard.ps1"
$base='data_results/simple_runs/roads_8_16_20261016'
$cfg='configs/beijing_roads_8_16_matcher_io_v2_20261016.json'
if($MinimumFreeGiB -lt 4){throw 'This scoring queue requires at least 4 GiB free.'}
if($InspectOnly){
    [pscustomobject]@{free_gib=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB;
        minimum_free_gib=$MinimumFreeGiB;would_run=$false} | ConvertTo-Json
    exit 0
}
$dependency=Get-CimInstance Win32_Process -Filter "ProcessId=$TrainingSshProcessId"
if($dependency){
    if($dependency.Name -ne 'ssh.exe' -or $dependency.CommandLine -notmatch 'RUN_MTNET_GPU_RESUME.ps1'){
        throw 'Training SSH PID does not belong to this queue.'
    }
    Write-Output "WAIT MTNet SSH PID $TrainingSshProcessId"
    Wait-Process -Id $TrainingSshProcessId
}
$target="$base/native/MTNet"
if(Test-Path -LiteralPath $target){
    $reuse=@(Get-ChildItem -LiteralPath $target -Force).Count -gt 0
}else{New-Item -ItemType Directory $target | Out-Null}
if(-not $reuse){
scp -r pc@10.134.48.163:D:/MTR/mtnet_20261016/native_release "$target/"
if($LASTEXITCODE -ne 0){throw 'MTNet native release transfer failed.'}
scp pc@10.134.48.163:D:/MTR/mtnet_20261016/trained/model.pt "$target/model.pt"
if($LASTEXITCODE -ne 0){throw 'MTNet model transfer failed.'}
scp pc@10.134.48.163:D:/MTR/mtnet_20261016/trained/paper_algorithm_manifest.json "$target/paper_algorithm_manifest.json"
if($LASTEXITCODE -ne 0){throw 'MTNet training manifest transfer failed.'}
}
$release=Get-Content -LiteralPath "$target/native_release/manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if((Get-FileHash -LiteralPath "$target/model.pt" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $release.model_sha256){
    throw 'Downloaded model hash differs from the native release.'
}
if((Get-FileHash -LiteralPath "$target/native_release/routes.pkl" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $release.routes_sha256){
    throw 'Downloaded routes differ from manifest; no overwrite or scoring.'
}
if((Get-FileHash -LiteralPath "$base/mtnet_prepared/full_preparation_manifest.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $release.preparation_manifest_sha256){
    throw 'Downloaded release uses different prepared inputs.'
}
Invoke-MtrMemoryBound -Label 'register_mtnet.py' -MinimumFreeGiB $MinimumFreeGiB -StateFile "$base/mtnet_scoring_memory_gate_state.json" -Action {
& E:/anconda/python.exe -X utf8 register_mtnet.py --config $cfg --source "$target/native_release" `
    1> "$base/mtnet_registration.log" 2> "$base/mtnet_registration.stderr.log"
if($LASTEXITCODE -ne 0){throw 'Native MTNet registration failed.'}
}
foreach($stage in @('evaluate.py','evaluate_physical.py','evaluate_coordinates.py','evaluate_road_tasks.py')){
    Invoke-MtrMemoryBound -Label "MTNet $stage" -MinimumFreeGiB $MinimumFreeGiB -StateFile "$base/mtnet_scoring_memory_gate_state.json" -Action {
    $arguments=@('-X','utf8',$stage,'--config',$cfg,'--method','MTNet','--router','Origin')
    if($stage -eq 'evaluate_coordinates.py'){$arguments+=@('--metric-protocol','audit-v2')}
    & E:/anconda/python.exe @arguments `
        1> "$base/mtnet_${stage}.log" 2> "$base/mtnet_${stage}.stderr.log"
    if($LASTEXITCODE -ne 0){throw "Native MTNet score failed: $stage"}
    Write-Output "DONE native MTNet $stage"
    }
}

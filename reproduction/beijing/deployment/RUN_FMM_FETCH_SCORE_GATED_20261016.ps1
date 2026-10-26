param([int]$RemoteQueueSshPid=12344,[switch]$InspectOnly)
$ErrorActionPreference='Stop'
if(-not $InspectOnly){throw 'Retired historical controller: use the documented independent commands; no historical queue may run from this delivery.'}
$env:PYTHONUTF8='1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot/MemoryGuard.ps1"
$base='data_results/simple_runs/roads_8_16_20261016'
$cfg='configs/beijing_roads_8_16_matcher_io_v2_20261016.json'
if($InspectOnly){
    Write-Output 'After remote queue exit: verify/fetch each FMM; score only with >=4GiB free; coordinates use audit-v2.'
    exit 0
}
$dependency=Get-CimInstance Win32_Process -Filter "ProcessId=$RemoteQueueSshPid"
if($dependency){
    if($dependency.Name -ne 'ssh.exe' -or $dependency.CommandLine -notmatch 'RUN_REMOTE_FMM_REMAINING.ps1'){
        throw 'Remote queue identity differs; stopped nothing.'
    }
    Wait-Process -Id $RemoteQueueSshPid
}
foreach($m in @('PrivTrace','DPStd','DPTraj-PM')){
    & E:/anconda/python.exe -X utf8 fetch_routes.py --config $cfg --method $m --router FMM `
        1> "$base/fetch_${m}_FMM.log" 2> "$base/fetch_${m}_FMM.stderr.log"
    if($LASTEXITCODE -ne 0){throw "Fetch/verification failed: $m"}
}
# Transfer all completed cells before any memory-gated scoring. Otherwise
# the first blocked evaluator prevents fetching later, already finished cells.
foreach($m in @('PrivTrace','DPStd','DPTraj-PM')){
    foreach($stage in @('evaluate.py','evaluate_physical.py','evaluate_coordinates.py','evaluate_road_tasks.py')){
        Invoke-MtrMemoryBound -Label "$m FMM $stage" -MinimumFreeGiB 4 -StateFile "$base/fmm_scoring_memory_gate_state.json" -Action {
        $arguments=@('-X','utf8',$stage,'--config',$cfg,'--method',$m,'--router','FMM')
        if($stage -eq 'evaluate_coordinates.py'){$arguments+=@('--metric-protocol','audit-v2')}
        Write-Output "START $m $stage"
        & E:/anconda/python.exe @arguments `
            1> "$base/after_remote_${stage}_${m}_FMM.log" 2> "$base/after_remote_${stage}_${m}_FMM.stderr.log"
        if($LASTEXITCODE -ne 0){throw "Scoring failed: $m $stage; do not consume partial output."}
        Write-Output "DONE $m $stage"
        }
    }
}

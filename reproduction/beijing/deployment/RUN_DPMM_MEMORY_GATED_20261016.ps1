param(
    [int]$ValidationProcessId = 0,
    [double]$MinimumFreeGiB = 6.0,
    [int]$PollSeconds = 30,
    [switch]$InspectOnly
)
$ErrorActionPreference = 'Stop'
if(-not $InspectOnly){throw 'Retired historical controller: use the documented independent commands; no historical queue may run from this delivery.'}
$env:PYTHONUTF8 = '1'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. "$PSScriptRoot/MemoryGuard.ps1"
$base = 'data_results/simple_runs/roads_8_16_20261016'
$validationFile = "$base/dpmm_equivalence/validation.json"
$stateFile = "$base/dpmm_memory_gate_state.json"
if ($MinimumFreeGiB -lt 6.0 -or $PollSeconds -lt 1) {
    throw 'This batch requires at least 6 GiB free before the two-worker graph job.'
}
function Get-FreeGiB {
    return (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
}
function Read-Validation {
    return Get-Content -LiteralPath $validationFile -Raw -Encoding UTF8 | ConvertFrom-Json
}
if ($InspectOnly) {
    if(-not (Test-Path -LiteralPath $validationFile)){
        [pscustomobject]@{status='RETIRED_HISTORICAL_CONTROLLER';validation_present=$false;would_start=$false} | ConvertTo-Json
        exit 0
    }
    $v = Read-Validation
    [pscustomobject]@{free_gib=Get-FreeGiB; required_gib=$MinimumFreeGiB;
        tested=$v.tested_records;target=$v.target_records;complete=$v.complete;
        passed=$v.passed;would_start=$false} | ConvertTo-Json
    exit 0
}
if ($ValidationProcessId -gt 0) {
    $dependency = Get-CimInstance Win32_Process -Filter "ProcessId=$ValidationProcessId"
    if ($dependency) {
        if ($dependency.CommandLine -notmatch 'validate_dpmm_dataset.py') {
            throw 'Dependency PID no longer belongs to the expected validation.'
        }
        Write-Output "WAIT validation PID $ValidationProcessId"
        Wait-Process -Id $ValidationProcessId
    }
}
$v = Read-Validation
if (-not $v.complete -or -not $v.passed -or $v.tested_records -ne 60 -or
    $v.target_records -ne 60 -or @($v.rows).Count -ne 60 -or
    @($v.rows | Where-Object {-not $_.exact_output_equal}).Count -ne 0) {
    throw 'Require all 60 exact-output validation records; no lower threshold.'
}
$ablation = Get-Content -LiteralPath "$base/ablation/MTR-DFR/manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json
if ($ablation.protocol -ne 'generated_mtr_dfr_algorithm_ablation_v3' -or $ablation.variants.Count -ne 4) {
    throw 'The four-arm ablation has not completed.'
}
Invoke-MtrMemoryBound -Label 'DPMM full generation' -MinimumFreeGiB $MinimumFreeGiB -PollSeconds $PollSeconds -StateFile $stateFile -Action {
    if (Test-Path -LiteralPath "$base/native/DPMM") { throw 'Native output exists; never start a second writer.' }
    $writers = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match 'synthesize_dpmm.py'
    })
    if ($writers.Count) { throw 'A DPMM writer already exists; refusing duplicate generation.' }
Write-Output 'START independent documented synthesize_dpmm.py command, unchanged algorithm'
& E:/anconda/python.exe -X utf8 synthesize_dpmm.py `
    --config configs/beijing_roads_8_16_matcher_io_v2_20261016.json `
    --adapter ../four_panel_completion_20261008/cloud_results/dpmm_full_archive/dpmm/check/run_dpmm_official_beijing.py `
    --optimizer ../four_panel_completion_20261008/fast_dpmm_paths.py `
    --validation $validationFile --workers 2 `
    1> "$base/dpmm_full_generation.log" 2> "$base/dpmm_full_generation.stderr.log"
if ($LASTEXITCODE -ne 0) { throw "DPMM generation failed: exit $LASTEXITCODE" }
Write-Output 'DONE full DPMM generation; final outputs still require verification and evaluation'
}

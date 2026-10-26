# Shared across local experiment controllers. Keep ownership throughout a
# large-graph command, not just during the free-memory check.
function Invoke-MtrMemoryBound {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][double]$MinimumFreeGiB,
        [Parameter(Mandatory=$true)][scriptblock]$Action,
        [string]$StateFile='',
        [int]$PollSeconds=30,
        [string]$MutexName='Local\MTR_DFR_20261016_BIG_GRAPH'
    )
    if($MinimumFreeGiB -le 0 -or $PollSeconds -lt 1){throw 'Invalid memory guard parameters.'}
    $mutex=New-Object System.Threading.Mutex($false,$MutexName)
    $held=$false
    try {
        while($true){
            try {$held=$mutex.WaitOne(0)}
            catch [System.Threading.AbandonedMutexException] {$held=$true}
            $free=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
            $status=if(-not $held){'WAITING_FOR_OTHER_EXPERIMENT'}elseif($free -lt $MinimumFreeGiB){'WAITING_FOR_MEMORY'}else{'RUNNING'}
            if($StateFile){
                [ordered]@{local_time=(Get-Date -Format o);stage=$Label;status=$status;
                    free_gib=$free;minimum_free_gib=$MinimumFreeGiB;controller_pid=$PID} |
                    ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
            }
            if($held -and $status -eq 'RUNNING'){break}
            if($held){$mutex.ReleaseMutex();$held=$false}
            Write-Output "WAIT ${Label}: $status, $([math]::Round($free,2)) GiB free"
            Start-Sleep -Seconds $PollSeconds
        }
        & $Action
    }
    finally {
        if($held){$mutex.ReleaseMutex()}
        $mutex.Dispose()
    }
}

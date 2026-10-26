"""Exercise the actual PowerShell guard without loading scientific data."""
import base64
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHELL = shutil.which('powershell')
pytestmark = pytest.mark.skipif(not SHELL, reason='Windows PowerShell required')


def command(body):
    source = f"$ErrorActionPreference='Stop'; . '{ROOT / 'deployment/MemoryGuard.ps1'}'; " + body
    return [SHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', base64.b64encode(source.encode('utf-16-le')).decode()]


def test_guard_releases_after_exception_and_keeps_memory_check():
    name = 'Local\\MTR_TEST_' + uuid.uuid4().hex
    body = "function Get-CimInstance { [pscustomobject]@{FreePhysicalMemory=100*1MB} }; "
    body += f"try {{Invoke-MtrMemoryBound -Label test -MinimumFreeGiB 4 -MutexName '{name}' -Action {{throw 'expected'}}}} catch {{if($_ -notmatch 'expected'){{throw}}}}; "
    body += f"Invoke-MtrMemoryBound -Label next -MinimumFreeGiB 4 -MutexName '{name}' -Action {{'RELEASED'}}"
    done = subprocess.run(command(body), capture_output=True, timeout=20)
    assert done.returncode == 0, done.stderr
    assert b'RELEASED' in done.stdout


def test_guard_serializes_processes_even_when_both_have_memory(tmp_path):
    name = 'Local\\MTR_TEST_' + uuid.uuid4().hex
    ready = tmp_path / 'ready'
    mock = "function Get-CimInstance { [pscustomobject]@{FreePhysicalMemory=100*1MB} }; "
    first = subprocess.Popen(command(mock + f"Invoke-MtrMemoryBound -Label first -MinimumFreeGiB 4 -MutexName '{name}' -Action {{New-Item -ItemType File '{ready}' | Out-Null; Start-Sleep -Seconds 3}}"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists()
        start = time.monotonic()
        second = subprocess.run(command(mock + f"Invoke-MtrMemoryBound -Label second -MinimumFreeGiB 4 -PollSeconds 1 -MutexName '{name}' -Action {{'SECOND'}}"), capture_output=True, timeout=20)
        assert second.returncode == 0, second.stderr
        assert b'WAITING_FOR_OTHER_EXPERIMENT' in second.stdout
        assert b'SECOND' in second.stdout
        assert time.monotonic() - start >= 2
    finally:
        first.communicate(timeout=20)


def test_low_memory_never_enters_action():
    name = 'Local\\MTR_TEST_' + uuid.uuid4().hex
    body = "function Get-CimInstance { [pscustomobject]@{FreePhysicalMemory=0} }; function Start-Sleep {throw 'TEST_STOP'}; "
    body += f"try {{Invoke-MtrMemoryBound -Label low -MinimumFreeGiB 4 -MutexName '{name}' -Action {{throw 'ACTION_MUST_NOT_RUN'}}}} catch {{if($_ -notmatch 'TEST_STOP'){{throw}}; 'BLOCKED'}}"
    done = subprocess.run(command(body), capture_output=True, timeout=20)
    assert done.returncode == 0, done.stderr
    assert b'BLOCKED' in done.stdout


def test_controller_syntax_and_inspect_only():
    for file in ('RUN_DPMM_MEMORY_GATED_20261016.ps1', 'RUN_MTNET_FETCH_SCORE_MEMORY_GATED_20261016.ps1', 'RUN_FMM_FETCH_SCORE_GATED_20261016.ps1'):
        path = ROOT / 'deployment' / file
        body = f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{throw ($e|Out-String)}}; & '{path}' -InspectOnly"
        done = subprocess.run(command(body), capture_output=True, timeout=20, cwd=ROOT)
        assert done.returncode == 0, done.stderr


def test_completed_downloads_precede_memory_gated_scoring():
    source=(ROOT/'deployment/RUN_FMM_FETCH_SCORE_GATED_20261016.ps1').read_text()
    # The second method loop must start after the fetch command and before
    # the first guarded evaluation; a blocked score cannot block downloads.
    loops=[i for i in range(len(source)) if source.startswith("foreach($m in @('PrivTrace','DPStd','DPTraj-PM'))",i)]
    assert len(loops)==2
    assert loops[0] < source.index('fetch_routes.py') < loops[1] < source.index('Invoke-MtrMemoryBound')


def test_historical_controllers_cannot_start_old_queues():
    for file in ('RUN_DPMM_MEMORY_GATED_20261016.ps1', 'RUN_MTNET_FETCH_SCORE_MEMORY_GATED_20261016.ps1', 'RUN_FMM_FETCH_SCORE_GATED_20261016.ps1'):
        done=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'deployment'/file)],
                            capture_output=True,timeout=20)
        assert done.returncode!=0
        assert b'Retired historical controller' in done.stderr

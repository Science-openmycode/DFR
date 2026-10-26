"""Launcher paths must survive the upstream trainer changing its directory."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['RUN_MTNET_GPU.ps1', 'RUN_MTNET_GPU_RESUME.ps1'])
def test_launcher_resolves_root_before_constructing_child_paths(name):
    script = (ROOT / 'deployment' / name).read_text(encoding='utf-8')
    assert script.index('$Root=(Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path') < script.index("Join-Path $Root")


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell path semantics')
def test_resolved_relative_root_survives_child_directory_change(tmp_path):
    root = tmp_path / 'relative deployment with spaces'
    (root / 'official').mkdir(parents=True)
    lock = root / 'canonical_mtnet_source_lock.json'
    lock.write_text('{}', encoding='utf-8')
    command = ("$Root='relative deployment with spaces'; "
               "$Root=(Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path; "
               "$lock=Join-Path $Root 'canonical_mtnet_source_lock.json'; "
               "Set-Location (Join-Path $Root 'official'); "
               "if (-not (Test-Path -LiteralPath $lock)) { exit 7 }; "
               "Get-Content -LiteralPath $lock")
    result = subprocess.run([shutil.which('powershell.exe'), '-NoProfile', '-Command', command],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '{}' in result.stdout

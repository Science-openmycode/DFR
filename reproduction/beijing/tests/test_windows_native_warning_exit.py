import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell 5 native stderr semantics')
@pytest.mark.parametrize('exit_code',[0,3])
def test_warning_is_not_failure_but_actual_nonzero_exit_is_preserved(tmp_path,exit_code):
    child=tmp_path/'warning_child.py'
    child.write_text("import sys\nsys.stderr.write('ordinary warning\\n')\nprint('finished')\nsys.exit("+str(exit_code)+")\n")
    stdout=tmp_path/'out.log';stderr=tmp_path/'err.log'
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    command=("$ErrorActionPreference='Stop';$p=Start-Process -FilePath "+quote(sys.executable)
             +" -ArgumentList "+quote('"'+str(child)+'"')
             +" -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput "+quote(stdout)
             +" -RedirectStandardError "+quote(stderr)+";exit $p.ExitCode")
    result=subprocess.run([shutil.which('powershell.exe'),'-NoProfile','-Command',command],capture_output=True,timeout=30)
    assert result.returncode==exit_code,result.stderr
    assert 'finished' in stdout.read_text()
    assert 'ordinary warning' in stderr.read_text()

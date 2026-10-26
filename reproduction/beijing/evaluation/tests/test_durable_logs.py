import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('durable_test_runner', ROOT/'experiments/_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('exit_code', [0, 7])
def test_independent_output_logs_and_exit(tmp_path, exit_code):
    output = tmp_path/'result.txt'
    command = [sys.executable, '-c', "import sys;from pathlib import Path;"
               f"Path({str(output)!r}).write_text('done');"
               f"print('OUT');print('ERR',file=sys.stderr);sys.exit({exit_code})"]
    step = dict(name='probe', command=command, outputs=[str(output)])
    if exit_code:
        with pytest.raises(subprocess.CalledProcessError):
            runner.execute([step], tmp_path/'logs', ROOT)
    else:
        runner.execute([step], tmp_path/'logs', ROOT)
    record = json.loads((tmp_path/'logs/probe.json').read_text())
    assert record['exit_code'] == exit_code
    assert record['status'] == ('FAILED' if exit_code else 'DONE')
    assert (tmp_path/'logs/probe.log').read_text().strip() == 'OUT'
    assert (tmp_path/'logs/probe.stderr.log').read_text().strip() == 'ERR'
    assert output.read_text() == 'done'

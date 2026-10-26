"""Run a frozen PowerShell command with durable server-side stdout/stderr and receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from check_documented_command import check


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def worker(job):
    spec = json.loads((job/'request.json').read_text(encoding='utf-8'))
    start = time.monotonic()
    record = dict(status='RUNNING', started=now(), supervisor_pid=os.getpid(), **spec)
    save(job/'status.json', record)
    try:
        check(spec['document'], spec['line'], spec['command'], spec['document_sha256'])
        if hashlib.sha256((job/'command.ps1').read_bytes()).hexdigest() != spec['script_sha256']:
            raise ValueError('Frozen command script changed')
        env = os.environ.copy()
        env.update(spec['environment'])
        with (job/'stdout.log').open('wb') as out, (job/'stderr.log').open('wb') as err:
            child = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy',
                                      'Bypass', '-File', str(job/'command.ps1')],
                                     cwd=spec['cwd'], env=env, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err)
            record['shell_pid'] = child.pid
            save(job/'status.json', record)
            code = child.wait()
        record.update(status='EXITED', exit_code=code)
    except BaseException as exc:
        record.update(status='LAUNCH_FAILED', error=repr(exc))
    record.update(finished=now(), elapsed_seconds=time.monotonic()-start)
    save(job/'status.json', record)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    launch = sub.add_parser('launch')
    launch.add_argument('--document', type=Path, required=True)
    launch.add_argument('--line', type=int, required=True)
    launch.add_argument('--document-sha256', required=True)
    launch.add_argument('--command', required=True)
    launch.add_argument('--cwd', type=Path, required=True)
    launch.add_argument('--job-dir', type=Path, required=True)
    launch.add_argument('--environment-json', type=Path)
    for name in ('worker', 'status'):
        sub.add_parser(name).add_argument('--job-dir', type=Path, required=True)
    a = p.parse_args()
    job = a.job_dir.resolve()
    if a.action == 'worker':
        worker(job)
        return
    if a.action == 'status':
        print((job/'status.json').read_text(encoding='utf-8'))
        return
    if os.name != 'nt':
        p.error('This launcher is for Windows PowerShell hosts')
    check(a.document, a.line, a.command, a.document_sha256)
    if not a.cwd.is_dir():
        p.error('Missing working directory')
    environment = json.loads(a.environment_json.read_text(encoding='utf-8-sig')) if a.environment_json else {}
    if not all(isinstance(k, str) and isinstance(v, str) for k,v in environment.items()):
        p.error('Environment must be string-to-string')
    job.mkdir(parents=True, exist_ok=False)
    # The experiment line is copied literally. Redirection occurs on the shell handles.
    script = "$ErrorActionPreference='Stop'\n$ProgressPreference='SilentlyContinue'\n" + a.command + "\nexit $LASTEXITCODE\n"
    (job/'command.ps1').write_text(script, encoding='utf-8-sig')
    spec = dict(document=str(a.document.resolve()), line=a.line, command=a.command,
                document_sha256=a.document_sha256, cwd=str(a.cwd.resolve()),
                environment=environment, script_sha256=hashlib.sha256((job/'command.ps1').read_bytes()).hexdigest())
    save(job/'request.json', spec)
    save(job/'status.json', dict(status='QUEUED', **spec))
    try:
        with (job/'supervisor.stdout.log').open('wb') as out, (job/'supervisor.stderr.log').open('wb') as err:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', '--job-dir', str(job)],
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, close_fds=True,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB)
        print(json.dumps(dict(supervisor_pid=child.pid, job_dir=str(job), status='LAUNCHED_NOT_COMPLETED')))
    except BaseException as exc:
        save(job/'status.json', dict(status='LAUNCH_FAILED', error=repr(exc), **spec))
        raise


if __name__ == '__main__':
    main()

"""Small, synchronous command runner. Complete steps, not partial algorithms, resume."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def execute(steps, log_dir, cwd, env=None):
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    for i, step in enumerate(steps, 1):
        record = log_dir / (step['name'] + '.json')
        inputs = {str(p): digest(p) for p in step.get('inputs', [])}
        code = {}
        for folder in step.get('dependency_roots', []):
            if not Path(folder).is_dir():
                raise FileNotFoundError(folder)
            for source in sorted(Path(folder).rglob('*')):
                if source.is_file() and source.suffix in ('.py', '.json', '.yaml', '.toml'):
                    code[str(source)] = digest(source)
        binding = {'command': step['command'], 'inputs': inputs, 'code': code}
        if record.exists():
            old = json.loads(record.read_text(encoding='utf-8'))
            if old.get('status') == 'DONE':
                if old['binding'] != binding or any(not Path(p).is_file() or digest(p) != h for p, h in old['outputs'].items()):
                    raise RuntimeError(f"{step['name']}: completed step changed; choose a new batch")
                print(f"[{i}/{len(steps)}] SKIP {step['name']}", flush=True)
                continue
            raise RuntimeError(f"{step['name']}: previous incomplete step; choose a new batch (no partial resume)")
        if any(Path(p).exists() for p in step['outputs']):
            raise RuntimeError(f"{step['name']}: unregistered output exists; choose a new batch")
        print(f"[{i}/{len(steps)}] RUN {step['name']}", flush=True)
        start = time.monotonic()
        payload = {'status': 'RUNNING', 'binding': binding}
        record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            stdout_path = log_dir / (step['name'] + '.log')
            stderr_path = log_dir / (step['name'] + '.stderr.log')
            payload['logs'] = {'stdout': str(stdout_path), 'stderr': str(stderr_path)}
            with stdout_path.open('wb') as log, stderr_path.open('wb') as errors:
                process = subprocess.Popen(step['command'], cwd=cwd, env=env,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=errors)
                payload['child_pid'] = process.pid
                record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
                code = process.wait()
            payload['exit_code'] = code
            if code:
                raise subprocess.CalledProcessError(code, step['command'])
            missing = [p for p in step['outputs'] if not Path(p).is_file()]
            if missing:
                raise RuntimeError(f"Missing expected outputs: {missing}")
            payload.update(status='DONE', outputs={p: digest(p) for p in step['outputs']})
        except BaseException:
            payload['status'] = 'FAILED'
            raise
        finally:
            payload['elapsed_seconds'] = round(time.monotonic() - start, 3)
            record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"{payload['status']} {step['name']}: {payload['elapsed_seconds']} s", flush=True)


def main(experiment):
    parser = argparse.ArgumentParser(description=f'Run {experiment} using the existing implementation.')
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without running or writing outputs')
    parser.add_argument('--batch', help='New output batch name')
    if experiment == 'main':
        parser.add_argument('--method', choices=['SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd'])
        parser.add_argument('--only-router', choices=['Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP'])
        parser.add_argument('--exclude-router', action='append', default=[])
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    if experiment in config.get('unsupported_stages', {}):
        parser.error(config['unsupported_stages'][experiment])
    if not args.dry_run and config.get('road_reference_status')=='DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING':
        parser.error('Road reference is deprecated: resolve preprocessing review and bind a frozen common road dataset before running experiments.')
    if args.batch:
        config['batch'] = args.batch
    if Path(config['batch']).name != config['batch'] or config['batch'] in ('.', '..'):
        parser.error('batch must be a single directory name')
    from _plans import build
    try:
        steps, directory, legacy = build(experiment, config, args, ROOT)
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps(steps, ensure_ascii=True, indent=2))
        return
    # Validate static input closure before paying for synthesis.
    produced = {p for s in steps for p in s['outputs']}
    for step in steps:
        for path in step.get('inputs', []):
            if path not in produced and not Path(path).is_file():
                parser.error(f'missing input: {path}')
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', DFR_LEGACY_ROOT=str(legacy), DFR_PRESERVE_EMPTY_SLOTS='1')
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        env[key] = str(config.get('threads', 1))
    execute(steps, directory / 'logs' / experiment, ROOT, env)


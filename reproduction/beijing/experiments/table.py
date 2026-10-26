"""Register and assemble the current batch without regenerating trajectories."""
import argparse
import json
from pathlib import Path
import sys
from _table_catalog import ROOT, prepare
from evaluation.table_collection import collect, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['register', 'collect', 'route', 'score', 'tstr', 'plot'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--batch', type=Path, help='Current result batch; defaults to the selected config output/batch')
    parser.add_argument('--out', type=Path, help='Table directory; defaults to the selected batch/table')
    parser.add_argument('--spec', type=Path, default=ROOT / 'plotting/specs/full_27x48.json')
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml')
    args = parser.parse_args()
    if args.batch is None:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        args.batch = ROOT / config['paths']['output'] / config['batch']
    if args.out is None:
        args.out = args.batch / 'table'
    if args.dry_run and args.step not in ('route', 'score', 'tstr'):
        parser.error('--dry-run is supported only for route, score, and tstr')
    directory = args.out.resolve()
    if args.step == 'plot':
        coverage = json.loads((directory / 'collected/coverage.json').read_text(encoding='utf-8'))
        if not coverage.get('complete'):
            parser.error('incomplete table: complete missing measurements before final plotting')
        parser.error('final plotting is not connected yet; source figure alignment is required')
    registry = directory / 'source_registry.json'
    if args.step in ('route', 'score', 'tstr'):
        from _table_jobs import jobs
        from _runner import execute
        import os
        tasks = jobs(args.step, args.batch, args.config)
        if args.dry_run:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
            return
        # Validate all static dependencies before starting the first expensive job.
        outputs = {p for t in tasks for p in t['outputs']}
        for task in tasks:
            for path in task['inputs']:
                if path not in outputs and not Path(path).is_file():
                    parser.error(f'missing dependency: {path}')
        env = os.environ.copy()
        env.update(PYTHONUTF8='1', DFR_LEGACY_ROOT=env.get('DFR_LEGACY_ROOT', str(ROOT/'legacy')))
        execute(tasks, directory / 'logs' / args.step, ROOT, env)
    elif args.step == 'register':
        if registry.exists():
            parser.error('registry exists; use collect, or choose a new --out directory')
        result = prepare(args.batch, args.config)
        directory.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"Registered {len(result['sources'])} sources; missing files: {len(result['unavailable_sources'])}")
    else:
        record = json.loads(registry.read_text(encoding='utf-8'))
        spec = json.loads(args.spec.read_text(encoding='utf-8'))
        rows = collect(spec, record['sources'])
        result = save(rows, directory / 'collected')
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

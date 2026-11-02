"""Verify current application/matrix assets after relocation, denying original reads."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(root, forbidden):
    def guard(event, args):
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(args[0])).resolve()
            if p.is_relative_to(forbidden) and not p.is_relative_to(forbidden/'.venv'):
                raise RuntimeError('Forbidden original-checkout read: '+str(p))
    sys.addaudithook(guard)
    sys.path.insert(0, str(root))
    from evaluation.applications.framework import prepare_cells
    from evaluation.applications.visualization import load_summary
    summary = root/'reference_results/applications'
    meta, _ = load_summary(summary)
    spec = json.loads((root/'reference_results/matrix/spec_framework.json').read_text(encoding='utf-8'))
    sources = root/'reference_results/matrix'
    manifest = json.loads((sources/'manifest.json').read_text(encoding='utf-8'))
    assert sha(sources/'matrix_sources.csv') == manifest['outputs']['matrix_sources.csv']
    cells, checked = [], {}
    with (sources/'matrix_sources.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            for key in ('result', 'manifest'):
                if not row[key]:
                    continue
                p = (root/row[key]).resolve()
                if not p.is_relative_to(root):
                    raise ValueError('Nonportable source: '+str(p))
                if p not in checked:
                    checked[p] = sha(p)
                assert checked[p] == row[key+'_sha256'], p
            cells.append(dict(row=row['row'], metric=row['column'],
                              value=float(row['value']) if row['value'] else None,
                              status=row['status']))
    final, methods = prepare_cells(cells, spec)
    sensitivity_cells = 0; sensitivity_scores = 0
    current = root/'reference_results/sensitivity_current'
    if current.is_dir():
        sensitivity = json.loads((current/'manifest.json').read_text(encoding='utf-8'))
        for name, h in sensitivity['outputs'].items():
            if sha(current/name) != h:
                raise ValueError('Changed current sensitivity asset: '+name)
        application_sweep = json.loads((current/'summary.json').read_text(encoding='utf-8'))
        if application_sweep['cells'] != 65 or len(application_sweep['rows']) != 260:
            raise ValueError('Incomplete K/budget current applications')
        sensitivity_cells = application_sweep['cells']; sensitivity_scores = len(application_sweep['rows'])
        from plotting.render_current_sweeps import values
        for kind, source in [('k', root/'reference_results/k/all_metrics.json'),
                             ('budget', root/'reference_results/budget/summary.json')]:
            expected = values(source, current/'summary.json', kind)
            table = json.loads((current/f'figures/{kind}/plot_data.json').read_text(encoding='utf-8'))
            for item in table:
                actual = [expected[item['x'], seed, item['stage'], item['metric']] for seed in range(20260719, 20260724)]
                if actual != item['values']:
                    raise ValueError('Current sensitivity plotted values changed')
    return dict(status='PASS', methods=len(methods), metrics=len(spec['columns']),
                cells=len(final), source_files_verified=len(checked),
                application_conditions=meta['methods'], original_checkout_reads=0,
                sensitivity_cells=sensitivity_cells, sensitivity_application_scores=sensitivity_scores,
                scope='Current packaged applications, final matrix and sensitivity dependencies; no experiments repeated')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--forbid-original', type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.forbid_original:
        result = verify(ROOT, args.forbid_original.resolve())
    else:
        from package_delivery import collect_files
        target = Path(tempfile.mkdtemp(prefix='current_applications_', dir=args.out.resolve().parent))
        for source in collect_files(ROOT):
            dest = target/source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Data are immutable inputs; code/config are independent copies.
            if source.suffix in ('.pkl', '.gz', '.npz', '.npy'):
                try:
                    os.link(source, dest)
                    continue
                except OSError:
                    pass
            shutil.copy2(source, dest)
        command = [sys.executable, '-X', 'utf8', str(target/'tools/verify_portable_supplements.py'),
                   '--forbid-original', str(ROOT), '--out', str(target/'verification.json')]
        tick = time.perf_counter()
        done = subprocess.run(command, cwd=target, capture_output=True, text=True, encoding='utf-8')
        result = dict(command=command, exit_code=done.returncode,
                      elapsed_seconds=time.perf_counter()-tick, relocated_root=str(target),
                      stdout=done.stdout, stderr=done.stderr)
        if (target/'verification.json').is_file():
            result['verification'] = json.loads((target/'verification.json').read_text(encoding='utf-8'))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if result.get('exit_code', 0):
        raise SystemExit(result['exit_code'])


if __name__ == '__main__':
    main()

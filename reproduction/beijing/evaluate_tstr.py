"""Score one saved train-only release; never synthesize or route."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method', required=True)
    p.add_argument('--router', choices=('Origin','Nearest','FMM','STMatch','MM2-MDP'), default='Origin')
    p.add_argument('--batch', type=Path, default=ROOT/'local_batches/beijing_corrected_20261013')
    p.add_argument('--config', type=Path, default=ROOT/'configs/beijing.yaml')
    p.add_argument('--input', type=Path, help='Saved train-only coordinate release or its routed geometry view')
    p.add_argument('--lineage', type=Path, help='Executed train-only generation record for this release')
    p.add_argument('--out', type=Path, help='New score directory')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--metric-protocol',choices=('legacy','audit-v2'),default='legacy',
                   help='Use isolated corrected retrieval/slot/NLL protocol without changing background jobs')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8-sig'))
    if not a.dry_run and c.get('road_reference_status') == 'DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING':
        p.error('Road reference is deprecated: freeze the preprocessed road dataset and derive its training/test split before TSTR.')
    def path(key):
        return (ROOT/c['paths'][key]).resolve()
    release = c.get('releases', {}).get(a.method, {})
    if (not a.input or not a.lineage) and not release:
        p.error('No registered train-only release; provide --input and --lineage')
    source = (a.input or ROOT/release['coordinates']).resolve()
    lineage = (a.lineage or ROOT/release['lineage']).resolve()
    if a.router != 'Origin':
        if a.method not in ('SPRT','PrivTrace','DPTraj-PM','DPStd'):
            p.error('Native methods must use Origin')
        source = (a.input or a.batch/'tstr_matrix/routes'/a.method/a.router/'view/coordinates.pkl').resolve()
    name = a.method if a.router == 'Origin' else a.method+' + '+a.router
    folder='tstr_audit_v2' if a.metric_protocol=='audit-v2' else 'tstr'
    out = (a.out or path('output')/c['batch']/folder/a.method/a.router).resolve()
    script = path('legacy')/'evaluation/run_tstr_experiment.py'
    command = [sys.executable, '-X', 'utf8', str(script), '--train-real', str(path('train')),
        '--test-real', str(path('test')), '--split-audit', str(path('split_audit')),
        '--require-synthesis-lineage', '--synthetic', str(source), '--names', name,
        '--synthesis-lineage', name+'='+str(lineage), '--osm-cache', str(path('osm')),
        '--bbox', *map(str,c['bbox']), '--seed', str(c['evaluation_seed']), '--out-dir', str(out)]
    if a.metric_protocol=='audit-v2':
        command=[sys.executable,'-X','utf8',str(ROOT/'evaluation/audit_v2_runner.py'),
                 '--stage','tstr','--legacy',str(path('legacy')),'--',*command[4:]]
    if a.dry_run:
        print(json.dumps({'command':command}, ensure_ascii=False, indent=2))
        return
    if out.exists():
        p.error('Output already exists; choose a new --out')
    inputs = [script, source, lineage, path('train'), path('test'), path('split_audit'), path('osm')]
    if a.metric_protocol=='audit-v2':
        inputs += [ROOT/'evaluation/audit_v2_runner.py',ROOT/'evaluation/audit_metric_fixes.py']
    sidecar = source.with_name(source.name+'.manifest.json')
    if sidecar.exists():
        inputs.append(sidecar)
    hashes = {str(f): digest(f) for f in inputs}
    start = time.monotonic()
    subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONUTF8='1'), check=True)
    if any(digest(f) != h for f,h in hashes.items()):
        raise RuntimeError('Input changed during scoring; do not use this result')
    manifest = out/'manifest.json'
    meta = json.loads(manifest.read_text(encoding='utf-8'))
    if not meta.get('synthesis_lineage_verified') or not meta.get('disjoint_split_verified'):
        raise RuntimeError('Strict TSTR verification failed')
    meta.update(results_sha256=digest(out/'results.csv'), command=command,
                scoring_inputs_sha256=hashes, elapsed_seconds=round(time.monotonic()-start,3))
    manifest.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"DONE: {out / 'results.csv'} ({meta['elapsed_seconds']} s)", flush=True)


if __name__ == '__main__':
    main()

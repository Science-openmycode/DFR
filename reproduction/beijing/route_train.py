"""Route a saved train-only M release and export its exact geometry; no scoring."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'experiments'))
from _table_jobs import jobs
from _runner import execute


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method', required=True, choices=('SPRT','PrivTrace','DPTraj-PM','DPStd'))
    p.add_argument('--router', required=True, choices=('Nearest','FMM','STMatch'))
    p.add_argument('--batch', type=Path, default=ROOT/'local_batches/beijing_corrected_20261013')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--config', type=Path, default=ROOT/'configs/beijing.yaml')
    a = p.parse_args()
    c = json.loads(a.config.read_text(encoding='utf-8-sig'))
    if not a.dry_run and c.get('road_reference_status') == 'DEPRECATED_PENDING_FULL_ROAD_PREPROCESSING':
        p.error('Road reference is deprecated: freeze the preprocessed road dataset before routing this batch.')
    names = {'train_'+a.method, 'train_route_'+a.method+'_'+a.router, 'train_geometry_'+a.method+'_'+a.router}
    if a.method not in c.get('releases', {}):
        p.error('No registered train-only release for '+a.method)
    tasks = [t for t in jobs('tstr', a.batch, a.config) if t['name'] in names]
    if a.dry_run:
        print(json.dumps(tasks, ensure_ascii=False, indent=2))
        return
    produced = {f for t in tasks for f in t['outputs']}
    for t in tasks:
        for f in t['inputs']:
            if f not in produced and not Path(f).is_file():
                p.error('Missing input: '+f)
    execute(tasks, a.batch/'tstr_matrix/logs', ROOT, dict(os.environ, PYTHONUTF8='1'))


if __name__ == '__main__':
    main()

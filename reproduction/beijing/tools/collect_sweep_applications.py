"""Verify and aggregate completed four-application sweep answers; no evaluation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

METRICS = ('MFPOrderedRouteOverlap', 'RepresentativeRealCoverage',
           'SelectedRoadMarginalOverlap', 'IncomingExitDistributionOverlap')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def collect(plan, kind='all'):
    data = json.loads(Path(plan).read_text(encoding='utf-8')); rows = []; sources = {}
    cells = [c for c in data['cells'] if kind == 'all' or c['kind'] == kind]
    seen = set(); question_hash = None; resource_hash = None
    for c in cells:
        key = (c['kind'], c['value'], c['seed'])
        if key in seen:
            raise ValueError('Duplicate cell')
        seen.add(key)
        b = Path(c['answer']); manifest = b/'manifest.json'
        m = json.loads(manifest.read_text(encoding='utf-8'))
        config = json.loads(Path(c['config']).read_text(encoding='utf-8'))
        def bound_path(value):
            p = Path(value)
            return p if p.is_absolute() else Path(c['config']).parent/p
        if (digest(bound_path(config['questions'])) != m['questions_sha256']
                or digest(bound_path(config['resources'])/'manifest.json') != m['resources_sha256']):
            raise ValueError('Changed application questions/resources')
        adapter = Path(c['config']).parent/'slots/manifest.json'
        a = json.loads(adapter.read_text(encoding='utf-8'))
        if (m['status'] != 'COMPLETE' or m['dataset_id'] != data['dataset_id']
                or m['slots'] != config['slots'] or m['method'] != c['answer_method']
                or a['source_sha256'] != c['source_sha256'] or a['rematched'] is not False
                or a['output_sha256'] != m['input_slots_sha256']
                or digest(c['source']) != c['source_sha256']):
            raise ValueError('Changed source or answer binding')
        for name, h in m['outputs'].items():
            if digest(b/name) != h:
                raise ValueError('Changed answer output')
        question_hash = question_hash or m['questions_sha256']
        resource_hash = resource_hash or m['resources_sha256']
        if (m['questions_sha256'], m['resources_sha256']) != (question_hash, resource_hash):
            raise ValueError('Sweeps must answer identical locked questions')
        values = json.loads((b/'metrics.json').read_text(encoding='utf-8'))['metrics']
        for metric in METRICS:
            value = values[metric]
            if value is None or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Incomplete application metric')
            rows.append(dict(kind=c['kind'], value=c['value'], seed=c['seed'], metric=metric,
                             score=value, source_sha256=c['source_sha256']))
        for p in (manifest, b/'metrics.json', adapter, Path(c['config'])):
            sources[str(p)] = digest(p)
    for selected in (('k', 'budget') if kind == 'all' else (kind,)):
        values = [24, 48, 96, 192, 384, 768] if selected == 'k' else [.2, .4, .7, 1, 1.4, 2, 3]
        expected = {(selected, value, seed) for value in values for seed in range(20260719, 20260724)}
        if {c for c in seen if c[0] == selected} != expected:
            raise ValueError('Incomplete design: '+selected)
    aggregates = []
    for kind, value, metric in sorted({(r['kind'], r['value'], r['metric']) for r in rows}):
        group = [r for r in rows if (r['kind'], r['value'], r['metric']) == (kind, value, metric)]
        if len(group) != 5 or len({r['seed'] for r in group}) != 5:
            raise ValueError('Expected five seeds')
        vals = [r['score'] for r in group]
        aggregates.append(dict(kind=kind, value=value, metric=metric, n=5,
                               mean=statistics.mean(vals), sd=statistics.stdev(vals)))
    return dict(status='COMPLETE', dataset_id=data['dataset_id'], rows=rows, aggregates=aggregates,
                sources=sources, questions_sha256=question_hash, resources_sha256=resource_hash,
                cells=len(cells), unique_releases=len({c['source_sha256'] for c in cells}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--kind', choices=['all', 'k', 'budget'], default='all')
    a = p.parse_args(); result = collect(a.plan, a.kind)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print('VERIFIED', result['cells'], 'cells;', len(result['rows']), 'scores')

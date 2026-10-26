"""Independent saved-road arithmetic check, never import the production scorer.

Checks 17 named statistics. Network bytes are hash-bound, but geometry parsing,
OD-prefix scores and five shape statistics are explicitly outside this check.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import pickle
import time


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    path = Path(path)
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as f:
        return pickle.load(f)


def compress(values):
    result = []
    for v in values:
        if not result or v != result[-1]:
            result.append(v)
    return tuple(result)


def accumulate(raw, cache):
    edges = cache['edge_nodes']
    labels = cache['labels96']
    degree = cache['outdegree']
    result = {k: Counter() for k in ('edges', 'turns', 'unit', 'family', 'od')}
    result.update(slots=len(raw), valid=0, decision_slots=0, branches=defaultdict(Counter))
    for row in raw:
        if not isinstance(row, dict) or type(row.get('accepted')) is not bool:
            raise ValueError('Explicit edge-records only; no inferred representation')
        if not row['accepted']:
            continue
        route = tuple(tuple(edges[int(e)]) for e in row['cpath'])
        if not route or any(a[1] != b[0] for a, b in zip(route, route[1:])):
            continue
        result['valid'] += 1
        result['edges'].update(route)
        turns = tuple(zip(route, route[1:]))
        result['turns'].update(turns)
        decisions = [turn for turn in turns if degree.get(turn[0][1], 0) > 1]
        if decisions:
            result['decision_slots'] += 1
            weight = 1.0 / (len(raw) * len(decisions))
            for turn in decisions:
                result['unit'][turn] += weight
        for a, b in turns:
            result['branches'][a][b] += 1.0 / max(len(route) - 1, 1)
        regions = [labels.get(route[0][0], -1)] + [labels.get(e[1], -1) for e in route]
        result['family'][compress(regions)] += 1
        labels24 = cache['labels24']
        result['od'][(labels24.get(route[0][0], -1), labels24.get(route[-1][1], -1))] += 1
    return result


def overlap(a, b):
    sa, sb = sum(a.values()), sum(b.values())
    if not sa or not sb:
        return 0.0
    # Iterate the real support only: missing synthetic mass contributes zero.
    return sum(min(v / sa, b.get(k, 0.0) / sb) for k, v in a.items())


def statistics(real, synthetic):
    n, nr = max(synthetic['slots'], 1), max(real['valid'], 1)
    y = synthetic['valid'] / n
    d = real['decision_slots'] / nr
    bounded = sum(min(v, synthetic['unit'].get(k, 0.0)) for k, v in real['unit'].items())
    out = {'RoadYield': y,
           'DemandFid': sum(min(v / nr, synthetic['od'].get(k, 0) / n) for k, v in real['od'].items()),
           'BTF': min(1.0, bounded / d) if d else 0.0,
           'RC-CPC': overlap(real['unit'], synthetic['unit']),
           'EdgeCPC': overlap(real['edges'], synthetic['edges']),
           'TurnCPC': overlap(real['turns'], synthetic['turns']),
           'FamilyCPC': overlap(real['family'], synthetic['family']) * y}
    for key, prefix in (('edges', 'Edge'), ('turns', 'Turn')):
        a, b = set(real[key]), set(synthetic[key])
        common = len(a.intersection(b))
        recall, precision = (common / len(a) if a else 1.0), (common / len(b) if b else 0.0)
        out[prefix + 'Recall'] = recall
        out[prefix + 'Precision'] = precision
        out[prefix + 'F1'] = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
        cpc = out[prefix + 'CPC']
        out[prefix + 'IoU'] = cpc / (2 - cpc)
    total = fidelity = dominant = 0.0
    for entry, counts in real['branches'].items():
        if len(counts) <= 1:
            continue
        mass = sum(counts.values())
        total += mass
        other = synthetic['branches'].get(entry, Counter())
        if other:
            fidelity += mass * overlap(counts, other)
            dominant += mass * (max(counts, key=counts.get) == max(other, key=other.get))
    out['BranchCPC'] = fidelity / max(total, 1e-12) if total else math.nan
    out['ExitAcc'] = dominant / max(total, 1e-12) if total else math.nan
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    started = time.perf_counter()
    meta = json.loads(a.manifest.read_text(encoding='utf-8'))
    if meta['representation'] != 'edge-records':
        raise ValueError('This independent checker only supports explicit edge records')
    for bindings in meta['inputs'].values():
        for item in (bindings if isinstance(bindings, list) else [bindings]):
            if sha(item['path']) != item['sha256']:
                raise ValueError('Input changed: ' + item['path'])
    if meta['inputs']['real_routes']['sha256'] != '0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c':
        raise ValueError('Wrong frozen reference')
    score = meta['outputs']['metrics_json']
    if sha(score['path']) != score['sha256']:
        raise ValueError('Saved score changed')
    cache = load(meta['inputs']['metric_cache']['path'])
    real = accumulate(load(meta['inputs']['real_routes']['path']), cache)
    if real['slots'] != 15730 or real['valid'] != 15730:
        raise ValueError('Unexpected reference filtering')
    synthetic = accumulate(load(meta['inputs']['synthetic_routes']['path']), cache)
    if synthetic['slots'] != 15730:
        raise ValueError('Lost release slots')
    actual = statistics(real, synthetic)
    expected = json.loads(Path(score['path']).read_text(encoding='utf-8'))
    comparisons = {}
    for key, value in actual.items():
        target = expected[key]
        passed = (target is None and math.isnan(value)) or (target is not None and math.isclose(value, target, rel_tol=1e-9, abs_tol=1e-10))
        comparisons[key] = dict(saved=target, independent=None if math.isnan(value) else value, passed=passed)
    report = dict(classification='INDEPENDENT_ARITHMETIC_CHECK_NOT_NEW_RELEASE',
                  production_scorer_imported=False, method=meta['method'], router=meta['router'],
                  inputs=meta['inputs'], saved_manifest_sha256=sha(a.manifest), checker_sha256=sha(__file__),
                  real_slots=real['slots'], synthetic_slots=synthetic['slots'], synthetic_valid=synthetic['valid'],
                  checks=comparisons, passed=all(v['passed'] for v in comparisons.values()),
                  elapsed_seconds=time.perf_counter()-started,
                  limitations=['17 statistics only; no OD-prefix or shape arithmetic verification',
                               'Public geometry conversion/connectivity is not independently parsed; network bytes are bound',
                               'Matches current physical-outdegree BTF, not regional or angle-excluded BTF'])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], checks=len(comparisons), seconds=report['elapsed_seconds'])))
    if not report['passed']:
        raise ValueError('Independent arithmetic differs; preserve evidence')


if __name__ == '__main__':
    main()

"""Independent remaining seven road statistics; no production scorer import."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import time

from independent_road_arithmetic import load, sha, compress

SHAPE = ('TotalLengthRetention', 'BackboneLengthRetention', 'ClosedLengthRetention',
         'ClosedSegmentRetention', 'RepeatedEdgeRetention')


def accumulate(raw, cache, lengths):
    groups = {r:defaultdict(Counter) for r in (96,384)}
    od_counts = {r:Counter() for r in (96,384)}
    totals = Counter()
    valid = 0
    for item in raw:
        if not item.get('accepted'):
            continue
        route = tuple(tuple(cache['edge_nodes'][int(e)]) for e in item['cpath'])
        if not route or any(a[1] != b[0] for a,b in zip(route,route[1:])):
            continue
        valid += 1
        labels = cache['labels24']
        od = labels.get(route[0][0],-1), labels.get(route[-1][1],-1)
        for resolution in (96,384):
            labels = cache['labels'+str(resolution)]
            path = compress([labels.get(route[0][0],-1)] + [labels.get(e[1],-1) for e in route])
            if len(path) > 1:
                od_counts[resolution][od] += 1
                for stop in range(2,len(path)+1):
                    groups[resolution][od][path[:stop]] += 1.0/(len(path)-1)
        # Separate implementation of chronological closed-walk removal.
        spine_nodes = [route[0][0]]
        spine_edges = []
        positions = {route[0][0]:0}
        closed_length = closed_count = 0
        for edge in route:
            vertex = edge[1]
            if vertex in positions:
                at = positions[vertex]
                closed_length += sum(lengths.get(e,0) for e in spine_edges[at:]) + lengths.get(edge,0)
                closed_count += 1
                for deleted in spine_nodes[at+1:]:
                    del positions[deleted]
                spine_nodes = spine_nodes[:at+1]
                spine_edges = spine_edges[:at]
            else:
                spine_edges.append(edge)
                spine_nodes.append(vertex)
                positions[vertex] = len(spine_nodes)-1
        totals['TotalLengthRetention'] += sum(lengths.get(e,0) for e in route)
        totals['BackboneLengthRetention'] += sum(lengths.get(e,0) for e in spine_edges)
        totals['ClosedLengthRetention'] += closed_length
        totals['ClosedSegmentRetention'] += closed_count
        totals['RepeatedEdgeRetention'] += len(route)-len(set(route))
    return dict(slots=len(raw), valid=valid, groups=groups, od_counts=od_counts, totals=totals)


def statistics(real, synthetic):
    result = {}
    for resolution in (96,384):
        counts = real['od_counts'][resolution]
        total = sum(counts.values())
        score = 0.0
        for od, n in counts.items():
            a, b = real['groups'][resolution][od], synthetic['groups'][resolution].get(od,{})
            sa, sb = sum(a.values()), sum(b.values())
            if sa and sb:
                score += n/max(total,1)*sum(min(v/sa,b.get(k,0)/sb) for k,v in a.items())
        result['ODPF'+str(resolution)] = score*synthetic['valid']/max(synthetic['slots'],1)
    for name in SHAPE:
        base = real['totals'][name]/max(real['valid'],1)
        result[name] = (synthetic['totals'][name]/max(synthetic['slots'],1))/base if base else 0.0
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    started = time.perf_counter()
    meta = json.loads(a.manifest.read_text(encoding='utf-8'))
    if meta['representation'] != 'edge-records':
        raise ValueError('Explicit edge records required')
    for value in meta['inputs'].values():
        for binding in value if isinstance(value,list) else [value]:
            if sha(binding['path']) != binding['sha256']:
                raise ValueError('Input hash mismatch')
    if meta['inputs']['real_routes']['sha256'] != '0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c':
        raise ValueError('Wrong population')
    output = meta['outputs']['metrics_json']
    if sha(output['path']) != output['sha256']:
        raise ValueError('Saved score hash mismatch')
    cache = load(meta['inputs']['metric_cache']['path'])
    import geopandas as gpd
    frame = gpd.read_file(meta['inputs']['network']['path'],ignore_geometry=True,columns=['id','length_m'])
    lengths = {}
    for item in frame.itertuples(index=False):
        edge = cache['edge_nodes'].get(int(item.id))
        if edge is None:
            continue
        edge = tuple(edge)
        value = max(float(item.length_m),0.001)
        lengths[edge] = min(value,lengths.get(edge,value))
    del frame
    real = accumulate(load(meta['inputs']['real_routes']['path']),cache,lengths)
    synthetic = accumulate(load(meta['inputs']['synthetic_routes']['path']),cache,lengths)
    if real['slots'] != 15730 or real['valid'] != 15730 or synthetic['slots'] != 15730:
        raise ValueError('Denominator mismatch')
    expected = json.loads(Path(output['path']).read_text())
    values = statistics(real,synthetic)
    checks = {k:dict(saved=expected[k],independent=v,
                    passed=math.isclose(v,expected[k],abs_tol=1e-10,rel_tol=1e-9)) for k,v in values.items()}
    report = dict(classification='INDEPENDENT_STRUCTURE_ARITHMETIC_NOT_NEW_RELEASE',
                  production_scorer_imported=False, inputs=meta['inputs'],
                  manifest_sha256=sha(a.manifest), checker_sha256=sha(__file__),
                  helper_sha256=sha(Path(__file__).with_name('independent_road_arithmetic.py')),
                  checks=checks, passed=all(v['passed'] for v in checks.values()),
                  seconds=time.perf_counter()-started,
                  limitation='Seven statistics only; public edge geometry direction/connectivity is not independently reparsed; no new metric definitions')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=len(checks),seconds=report['seconds'])))
    if not report['passed']:
        raise ValueError('Independent structure arithmetic differs; preserve report')


if __name__ == '__main__':
    main()

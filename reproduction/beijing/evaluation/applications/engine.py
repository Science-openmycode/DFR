"""Prepare public resources, answer four tasks from road slots, and summarize."""
import argparse
import csv
import gzip
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from .metrics import aggregate, digest, read
from .core import author_greedy, clip, erase_loops, marginal_score, ordered, overlap, solve


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)


def load_config(path):
    path = path.resolve(); cfg = read(path)
    for key in ('public_edges', 'questions', 'region', 'resources'):
        p = Path(cfg[key]); cfg[key] = p if p.is_absolute() else path.parent/p
    for item in cfg['methods']:
        p = Path(item['slots']); item['slots'] = p if p.is_absolute() else path.parent/p
    if len({x['name'] for x in cfg['methods']}) != len(cfg['methods']):
        raise ValueError('Duplicate methods')
    cfg['config_path'] = path
    return cfg


def prepare(cfg, out):
    start = time.perf_counter()
    import numpy as np
    from scipy.spatial import cKDTree
    out.mkdir(parents=True, exist_ok=False)
    region = read(cfg['region']); box = region['bounds_xy_m']
    if cfg.get('coordinate_units') != 'metre':
        raise ValueError('Projected metre geometry required; no implicit Beijing projection')
    pieces = []; maximum_node = -1
    for parent, e in enumerate(rows(cfg['public_edges'])):
        maximum_node = max(maximum_node, int(e['u']), int(e['v']))
        points = e['geometry']; groups = []
        for j, (a, b) in enumerate(zip(points, points[1:])):
            c = clip(a, b, box)
            if c:
                if groups and j == groups[-1][-1][0]+1 and math.dist(groups[-1][-1][1][1], c[0]) < 1e-7:
                    groups[-1].append((j, c))
                else:
                    groups.append([(j, c)])
        if groups:
            pieces.append((parent, e, groups))
    roads, segments, mapping, coord_nodes = [], [], [], {}
    next_node = maximum_node+1
    def node(p, original, parent):
        nonlocal next_node
        if original is not None:
            return original
        key = (parent, round(p[0], 8), round(p[1], 8))
        if key not in coord_nodes:
            coord_nodes[key] = next_node; next_node += 1
        return coord_nodes[key]
    for parent, e, groups in pieces:
        for group in groups:
            i = len(roads); a, b = group[0][1][0], group[-1][1][1]
            u = int(e['u']) if math.dist(a, e['geometry'][0]) < 1e-7 else None
            v = int(e['v']) if math.dist(b, e['geometry'][-1]) < 1e-7 else None
            roads.append([i, node(a, u, parent), node(b, v, parent), *a, *b,
                          sum(math.dist(*c) for _, c in group)])
            mapping.append(dict(id=i, original_row=parent, original_edge_id=int(e['edge_id'])))
            segments.extend((i, *c[0], *c[1]) for _, c in group)
    if not roads:
        raise ValueError('No public geometry in region')
    # Same conservative endpoint bound as the verified native cache builder;
    # the original author distance, not Euclidean distance, decides coverage.
    seg = np.array(segments, dtype=float)
    endpoints = np.concatenate((seg[:, 1:3], seg[:, 3:5]))
    index = cKDTree(endpoints); eps = float(cfg['coverage_distance_m'])
    radius = 1.208*eps+1e-7; cache = []
    def distance(s, r):
        ax, ay, bx, by = s[1:]; cx, cy, dx, dy = r[3:7]
        vx, vy, wx, wy = bx-ax, by-ay, dx-cx, dy-cy
        l, h = math.sqrt(vx*vx+vy*vy), math.sqrt(wx*wx+wy*wy)
        angle = 0.
        if l != 0 and h != 0:
            co = max(-1., min(1., (vx*wx+vy*wy)/(l*h)))
            angle = max(l, h)*math.sqrt(1-co*co)
        if l > h:
            sx, sy, ex, ey, px, py, qx, qy = ax, ay, bx, by, cx, cy, dx, dy
        else:
            sx, sy, ex, ey, px, py, qx, qy = cx, cy, dx, dy, ax, ay, bx, by
        ux, uy = ex-sx, ey-sy; z = ux*ux+uy*uy
        if z == 0:
            return float('nan')
        a, b = ((px-sx)*ux+(py-sy)*uy)/z, ((qx-sx)*ux+(qy-sy)*uy)/z
        apx, apy, bpx, bpy = sx+a*ux, sy+a*uy, sx+b*ux, sy+b*uy
        p, q = math.sqrt((px-apx)**2+(py-apy)**2), math.sqrt((qx-bpx)**2+(qy-bpy)**2)
        pp, qq = math.sqrt((sx-apx)**2+(sy-apy)**2), math.sqrt((sx-bpx)**2+(sy-bpy)**2)
        return (0. if p == 0 and q == 0 else (p*p+q*q)/(p+q))+angle+min(pp, qq)
    for i, r in enumerate(roads):
        candidates = {j % len(seg) for group in index.query_ball_point([r[3:5], r[5:7]], radius) for j in group}
        cache.append(sorted({int(seg[j, 0]) for j in candidates if distance(seg[j], r) < eps}))
        if i % 2000 == 0:
            print('PUBLIC_GEOMETRY', i, '/', len(roads), flush=True)
    write(out/'roads.json', roads); write(out/'mapping.json', mapping); write(out/'coverage.json', cache)
    write(out/'manifest.json', dict(status='COMPLETE', dataset_id=cfg['dataset_id'],
          public_edges_sha256=digest(cfg['public_edges']), region_sha256=digest(cfg['region']),
          questions_sha256=digest(cfg['questions']), coverage_distance_m=eps,
          outputs={p.name: digest(p) for p in out.iterdir() if p.is_file()}, seconds=time.perf_counter()-start))
    print('RESOURCES_COMPLETE', len(roads), time.perf_counter()-start, flush=True)


def resource_check(cfg):
    folder = cfg['resources']; m = read(folder/'manifest.json')
    for key, path in [('public_edges_sha256', cfg['public_edges']), ('region_sha256', cfg['region']),
                      ('questions_sha256', cfg['questions'])]:
        if m[key] != digest(path):
            raise ValueError('Resource binding mismatch: '+key)
    if m['dataset_id'] != cfg['dataset_id'] or m['coverage_distance_m'] != cfg['coverage_distance_m']:
        raise ValueError('Wrong dataset/distance')
    for name, h in m['outputs'].items():
        if digest(folder/name) != h:
            raise ValueError('Resource changed: '+name)


def answer(cfg, method, reference, out):
    start = time.perf_counter(); resource_check(cfg)
    q = read(cfg['questions']); region = read(cfg['region'])
    if q['dataset_id'] != cfg['dataset_id']:
        raise ValueError('Wrong questions dataset')
    item = next(x for x in cfg['methods'] if x['name'] == method)
    if digest(item['slots']) != item['sha256']:
        raise ValueError('Slots differ from configured input')
    out.mkdir(parents=True, exist_ok=False)
    records = []; used = set(); population = cfg['slots']
    for i, r in enumerate(rows(item['slots'])):
        if r['slot_id'] != i or i >= population or bool(r['edge_ids']) != r['valid']:
            raise ValueError('Incomplete or invalid slot contract')
        seq = r['edge_ids'] if r['valid'] else []
        records.append(seq); used.update(seq)
    if len(records) != population:
        raise ValueError('Incomplete population')
    edges = {e['edge_id']: {k: e[k] for k in ('u', 'v', 'length_m', 'origin_zone', 'destination_zone')}
             for e in rows(cfg['public_edges']) if e['edge_id'] in used}
    if set(edges) != used:
        raise ValueError('Unknown public road; no rematching or repair')
    paths = []; rcounts = defaultdict(Counter); turns = defaultdict(Counter)
    selected = set(q['selected_roads']); incoming = {tuple(x) for x in q['turning_incoming']}
    incidence = defaultdict(int)
    for slot, seq in enumerate(records):
        if not seq:
            paths.append([]); continue
        for a, b in zip(seq, seq[1:]):
            if edges[a]['v'] != edges[b]['u']:
                raise ValueError('Disconnected valid road sequence')
            key = (edges[a]['v'], a)
            if key in incoming:
                turns[key][b] += 1
        od = (edges[seq[0]]['origin_zone'], edges[seq[-1]]['destination_zone'])
        for e in set(seq):
            incidence[e] |= 1 << slot
            if e in selected:
                rcounts[e][od] += 1
        paths.append(erase_loops(seq, edges))
    destinations = {x['destination'] for x in q['mfp_queries']}
    weights = {d: Counter() for d in destinations}
    for path in paths:
        seen = set()
        for e in path:
            seen.add(e); d = edges[e]['v']
            if d in weights:
                weights[d].update(seen)
    mfp = []
    for d in sorted(destinations):
        labels = solve(weights[d], d, edges)
        for query in q['mfp_queries']:
            if query['destination'] == d:
                state = labels.get(query['source'])
                mfp.append(dict(query_id=query['query_id'], ordered_edge_ids=list(state[1]) if state else [],
                                status='ANSWER' if state else 'NO_SUPPORTED_PATH'))
        print('MFP_DEST_COMPLETE', method, d, len(mfp), '/', len(q['mfp_queries']), flush=True)
    roads = read(cfg['resources']/'roads.json'); mapping = read(cfg['resources']/'mapping.json')
    public_cache = read(cfg['resources']/'coverage.json')
    occ = [incidence[str(row['original_edge_id'])] for row in mapping]
    masks = []
    for indices in public_cache:
        bits = 0
        for j in indices:
            bits |= occ[j]
        masks.append(bits)
    routes = author_greedy(roads, masks, max([q['representative']['K'], *q['representative']['supplementary_K']]), cfg['route_budget_m'])
    raw = dict(method=method, mfp=mfp,
               selected_road=[[e, [[o, d, c] for (o, d), c in sorted(rcounts[e].items())]] for e in q['selected_roads']],
               turning=[[n, a, [[b, c] for b, c in sorted(turns[n, a].items())]] for n, a in q['turning_incoming']],
               representative_routes=routes)
    if reference is None:
        if method != cfg['real_method']:
            raise ValueError('First answer must be configured real reference')
        ref = raw; real_masks = masks; ref_path = out
        region_bits = 0
        for b in occ:
            region_bits |= b
        if region_bits.bit_count() != q['representative']['real_population']:
            raise ValueError('Real region population changed')
        if set(i for i in range(population) if region_bits >> i & 1) != set(region['real_slot_ids']):
            raise ValueError('Real region slots changed')
        write(out/'real_coverage.json', [hex(b) for b in real_masks])
    else:
        rm = read(reference/'manifest.json')
        if rm['method'] != cfg['real_method'] or rm['questions_sha256'] != digest(cfg['questions']):
            raise ValueError('Wrong reference')
        for name, h in rm['outputs'].items():
            if digest(reference/name) != h:
                raise ValueError('Reference changed')
        if rm['resources_sha256'] != digest(cfg['resources']/'manifest.json'):
            raise ValueError('Reference graph changed')
        ref = read(reference/'raw_answers.json'); real_masks = [int(b, 16) for b in read(reference/'real_coverage.json')]; ref_path = reference
    # Ordered overlap needs the real answer's lengths even when synthetic misses roads.
    ref_used = {e for r in ref['mfp'] for e in r['ordered_edge_ids']}
    if not ref_used <= edges.keys():
        for e in rows(cfg['public_edges']):
            if e['edge_id'] in ref_used and e['edge_id'] not in edges:
                edges[e['edge_id']] = {'length_m': e['length_m']}
    ref_mfp = {r['query_id']: r for r in ref['mfp']}
    comparisons = [dict(query_id=r['query_id'], status=r['status'],
                        ordered_length_overlap=ordered(ref_mfp[r['query_id']]['ordered_edge_ids'], r['ordered_edge_ids'], edges)) for r in mfp]
    real_roads = {e: Counter({(o, d): c for o, d, c in vals}) for e, vals in ref['selected_road']}
    real_turns = {(n, a): Counter(dict(vals)) for n, a, vals in ref['turning']}
    rd = [dict(road=e, real_support=sum(real_roads[e].values()), synthetic_support=sum(rcounts[e].values()),
               score=marginal_score(real_roads[e], rcounts[e])) for e in q['selected_roads']]
    td = [dict(junction=n, incoming=a, real_support=sum(real_turns[n, a].values()), synthetic_support=sum(turns[n, a].values()),
               score=overlap(real_turns[n, a], turns[n, a])) for n, a in q['turning_incoming']]
    rep = {}
    for k in sorted({q['representative']['K'], *q['representative']['supplementary_K']}):
        covered = 0
        for route in routes[:k]:
            for e in route:
                covered |= real_masks[e]
        n = q['representative']['real_population']
        rep[str(k)] = dict(actual_routes=len(routes[:k]), covered=covered.bit_count(), population=n, score=covered.bit_count()/n)
    details = dict(mfp=comparisons, selected_road=rd, turning=td, representative=rep)
    write(out/'raw_answers.json', raw); write(out/'details.json', details)
    metrics = aggregate(q, details)
    write(out/'metrics.json', dict(method=method, metrics=metrics, scope='retrospective_four_road_applications'))
    write(out/'manifest.json', dict(status='COMPLETE', method=method, dataset_id=cfg['dataset_id'],
          questions_sha256=digest(cfg['questions']), input_slots_sha256=digest(item['slots']),
          resources_sha256=digest(cfg['resources']/'manifest.json'), slots=population,
          input_kind='full_saved_road_release_no_retraining_no_rematching',
          reference=str(ref_path), seconds=time.perf_counter()-start, argv=sys.argv,
          outputs={p.name: digest(p) for p in out.iterdir() if p.is_file()}))
    print('ANSWER_COMPLETE', method, metrics, time.perf_counter()-start, flush=True)


def summarize(cfg, inputs, out):
    out.mkdir(parents=True, exist_ok=False); result = []; receipts = {}
    expected_inputs = {x['name']: x['sha256'] for x in cfg['methods']}
    expected_resources = digest(cfg['resources']/'manifest.json')
    for folder in inputs:
        m = read(folder/'manifest.json')
        if m['status'] != 'COMPLETE' or m['dataset_id'] != cfg['dataset_id'] or m['questions_sha256'] != digest(cfg['questions']):
            raise ValueError('Incompatible answer result')
        if (m['resources_sha256'] != expected_resources
                or m['input_slots_sha256'] != expected_inputs.get(m['method'])
                or m['slots'] != cfg['slots']):
            raise ValueError('Different graph resources, input release or population')
        for name, h in m['outputs'].items():
            if digest(folder/name) != h:
                raise ValueError('Result changed')
        if m['method'] in receipts:
            raise ValueError('Duplicate method result')
        receipts[m['method']] = digest(folder/'manifest.json')
        result.append(dict(method=m['method'], **read(folder/'metrics.json')['metrics']))
    if set(receipts) != {x['name'] for x in cfg['methods']}:
        raise ValueError('Incomplete method matrix')
    with (out/'results.csv').open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(result[0])); w.writeheader(); w.writerows(result)
    q = read(cfg['questions'])
    write(out/'manifest.json', dict(status='COMPLETE', methods=len(result), receipts=receipts,
          dataset_id=cfg['dataset_id'], slots=cfg['slots'],
          scope='retrospective_four_road_applications', protocol='supported_questions_20261102',
          task_counts=dict(od=len(q['mfp_queries']), roads=len(q['selected_roads']),
                           incoming=len(q['turning_incoming']), region_trips=q['representative']['real_population']),
          representative_K=q['representative']['K'],
          table_sha256=digest(out/'results.csv'), questions_sha256=digest(cfg['questions'])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['prepare', 'answer', 'summarize']); p.add_argument('--config', type=Path, required=True)
    p.add_argument('--method'); p.add_argument('--reference', type=Path); p.add_argument('--input', type=Path, action='append')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); c = load_config(a.config)
    if a.stage == 'prepare': prepare(c, a.out)
    elif a.stage == 'answer': answer(c, a.method, a.reference, a.out)
    else: summarize(c, a.input or [], a.out)

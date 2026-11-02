"""Audit frozen K outputs and public partition geometry without resynthesis."""
import argparse
import collections
import gzip
import hashlib
import json
import pickle
import time
from pathlib import Path


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def components(labels, edges):
    parent = {n: n for n in labels}
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for u, v in edges:
        if labels[u] == labels[v]:
            a, b = root(u), root(v)
            if a != b:
                parent[a] = b
    sizes = collections.Counter((labels[n], root(n)) for n in labels)
    by_cell = collections.defaultdict(list)
    for (cell, _), size in sizes.items():
        by_cell[cell].append(size)
    return {str(cell): dict(nodes=sum(s), components=len(s), largest_fraction=max(s)/sum(s))
            for cell, s in sorted(by_cell.items())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    started = time.perf_counter()
    cfg = json.loads((a.root/'configs/beijing.json').read_text(encoding='utf-8'))
    cache_path = Path(cfg['paths']['metric_cache'])
    with gzip.open(cache_path, 'rb') as f:
        cache = pickle.load(f)
    edges = list(cache['edge_nodes'].values())
    partition_reports = {}
    maps = {}
    for k in [24, 48, 96, 192, 384]:
        path = a.root/f'partitions/partition{k}.json'
        obj = json.loads(path.read_text(encoding='utf-8'))
        assert obj['metric_cache_sha256'].lower() == sha(cache_path).lower()
        assert obj['network_sha256'].lower() == sha(cfg['paths']['network']).lower()
        labels = {int(n): int(c) for n, c in obj['labels'].items()}
        maps[k] = labels
        stats = components(labels, edges)
        partition_reports[str(k)] = dict(sha256=sha(path), cells=stats,
            disconnected_cells=sum(v['components'] > 1 for v in stats.values()),
            nodes_outside_largest=sum(v['nodes']*(1-v['largest_fraction']) for v in stats.values()))
    nested = {}
    for coarse, fine in zip([24, 48, 96, 192], [48, 96, 192, 384]):
        parents = collections.defaultdict(set)
        for n, cell in maps[fine].items():
            parents[cell].add(maps[coarse][n])
        nested[f'{coarse}->{fine}'] = dict(crossing_fine_cells=sum(len(v)>1 for v in parents.values()))
    receipts = []
    for lane in range(3):
        receipts += [json.loads(s) for s in (a.root/f'lane_{lane}_receipts.jsonl').read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    plan = json.loads((a.root/'plan.json').read_text(encoding='utf-8'))
    outputs = []
    for cell in plan['cells']:
        for step in cell['steps']:
            exits = [r for r in receipts if r['event']=='EXIT' and r['command']==step['command']]
            assert len(exits)==1 and exits[0]['exit_code']==0, (cell['name'], step, exits)
        out = a.root/f"results/{cell['name']}/native/MTR-DFR"
        lineage_path = out.with_name(out.name+'.private_audit')/'input_lineage.json'
        lineage = json.loads(lineage_path.read_text(encoding='utf-8'))
        assert lineage['status']=='DONE' and lineage['epsilon']==1.4
        assert lineage['public_endpoint_partition']['k']==cell['k']
        for rel, expected in lineage['outputs'].items():
            assert sha(out/rel).lower()==expected.lower(), out/rel
        with gzip.open(next(out.glob('seed_*/road_routes.pkl.gz')), 'rb') as f:
            rows=pickle.load(f)
        assert len(rows)==15730
        outputs.append(dict(name=cell['name'], slots=len(rows), generation_seconds=lineage['elapsed_seconds'],
                            lineage_sha256=sha(lineage_path), output_hashes=lineage['outputs']))
    report=dict(status='VERIFIED_20_NEW_RUNS_AND_PUBLIC_PARTITIONS', existing_reuse384=json.loads((a.root/'reuse384.json').read_text(encoding='utf-8-sig')),
                completed_new_cells=outputs, partitions=partition_reports, nesting=nested,
                exit_count=sum(r['event']=='EXIT' for r in receipts), elapsed_seconds=time.perf_counter()-started,
                source_sha256=sha(__file__))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('completed_new_cells','partitions','existing_reuse384')}))
    print(json.dumps({k:{f:v for f,v in s.items() if f!='cells'} for k,s in partition_reports.items()}))


if __name__=='__main__':
    main()

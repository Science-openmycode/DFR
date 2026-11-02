"""Representation-only adapters for existing main-code road outputs.

Pickle is only for trusted locally generated experiment artifacts. This command
never map-matches coordinates or repairs rejected/disconnected road sequences.
"""
import argparse
import gzip
import json
import math
import pickle
import time
from collections import Counter
from pathlib import Path
from .metrics import digest
from .engine import rows, write


def load(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rb') as f:
        return pickle.load(f)


def public(network, metric_cache, out):
    import shapefile
    start = time.perf_counter(); out.mkdir(parents=True, exist_ok=False)
    cache = load(metric_cache)
    edge_nodes = {str(e): tuple(map(str, uv)) for e, uv in cache['edge_nodes'].items()}
    seen = set(); positions = {}
    reader = shapefile.Reader(str(network))
    with gzip.open(out/'public_edges.jsonl.gz', 'wt', encoding='utf-8') as f:
        for sr in reader.iterShapeRecords():
            eid, u, v, length = sr.record[:4]; eid, u, v = str(eid), str(u), str(v)
            if eid in seen or edge_nodes.get(eid) != (u, v):
                raise ValueError('Road ID/direction differs between metric cache and public network')
            seen.add(eid); pts = [list(p) for p in sr.shape.points]
            if len(pts) < 2 or not math.isfinite(length) or length <= 0:
                raise ValueError('Invalid public geometry')
            for n, pos in ((u, pts[0]), (v, pts[-1])):
                if n in positions and math.dist(positions[n], pos) > .01:
                    raise ValueError('Node geometry mismatch')
                positions[n] = pos
            e = dict(edge_id=eid, u=u, v=v, length_m=float(length), geometry=pts,
                     start_heading=math.atan2(pts[1][1]-pts[0][1], pts[1][0]-pts[0][0]),
                     end_heading=math.atan2(pts[-1][1]-pts[-2][1], pts[-1][0]-pts[-2][0]),
                     origin_zone=str(cache['labels384'][int(u)]), destination_zone=str(cache['labels384'][int(v)]))
            f.write(json.dumps(e, separators=(',', ':'))+'\n')
    if seen != set(edge_nodes):
        raise ValueError('Incomplete public graph')
    write(out/'manifest.json', dict(status='COMPLETE', network_files={p.suffix: digest(p) for p in network.parent.glob(network.stem+'.*') if p.is_file()},
          metric_cache_sha256=digest(metric_cache), public_edges_sha256=digest(out/'public_edges.jsonl.gz'), roads=len(seen), seconds=time.perf_counter()-start))


def adapt(source, public_edges, population, out):
    start = time.perf_counter(); out.mkdir(parents=True, exist_ok=False)
    records = load(source)
    if len(records) != population:
        raise ValueError('Wrong full release population')
    nodes = {e['edge_id']: (e['u'], e['v']) for e in rows(public_edges)}
    seen = set(); reasons = Counter(); valid = 0
    with gzip.open(out/'slots.jsonl.gz', 'wt', encoding='utf-8') as f:
        for slot, record in enumerate(records):
            seq = list(map(str, record.get('cpath', [])))
            if record.get('accepted', False) and seq:
                if any(e not in nodes for e in seq):
                    raise ValueError('Unknown public edge in accepted record')
                if any(nodes[a][1] != nodes[b][0] for a, b in zip(seq, seq[1:])):
                    raise ValueError('Disconnected accepted record; do not invent connectors')
                reason = None; valid += 1
            else:
                seq = []; reason = record.get('reason', 'empty_or_rejected')
            source_index = record.get('source_index', slot)
            if source_index in seen:
                raise ValueError('Duplicate source index')
            seen.add(source_index); reasons[str(reason or 'valid')] += 1
            f.write(json.dumps(dict(slot_id=slot, source_index=source_index, edge_ids=seq,
                                   valid=bool(seq), failure_reason=reason), separators=(',', ':'))+'\n')
    write(out/'manifest.json', dict(status='COMPLETE', source_sha256=digest(source), public_edges_sha256=digest(public_edges),
          slots=population, valid=valid, reason_counts=dict(reasons), output_sha256=digest(out/'slots.jsonl.gz'),
          representation_only=True, rematched=False, repaired=False, seconds=time.perf_counter()-start))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='stage', required=True)
    a = sub.add_parser('public'); a.add_argument('--network', type=Path, required=True); a.add_argument('--metric-cache', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    a = sub.add_parser('adapt'); a.add_argument('--input', type=Path, required=True); a.add_argument('--public-edges', type=Path, required=True)
    a.add_argument('--slots', type=int, required=True); a.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.stage == 'public': public(a.network, a.metric_cache, a.out)
    else: adapt(a.input, a.public_edges, a.slots, a.out)

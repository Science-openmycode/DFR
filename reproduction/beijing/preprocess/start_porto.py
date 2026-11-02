"""Audit START road sequences against a separately constructed public graph.

This stage never matches GPS, chooses a path, interpolates time, or freezes a
restricted population. It emits explicit road and trajectory acceptance reasons.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import time
import zipfile


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(z, name, delimiter=','):
    with z.open(name) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream, delimiter=delimiter)


def point(p):
    # START and OSM use seven-decimal coordinates. No spatial nearest neighbour.
    return tuple(round(float(x), 7) for x in p[:2])


def map_road(coords, candidates, endpoints):
    points = [point(p) for p in coords]
    pairs = [(a, b) for a, b in zip(points, points[1:]) if a != b]
    if not pairs:
        return {'status': 'EMPTY_GEOMETRY'}
    hits = [candidates.get(pair, []) for pair in pairs]
    if any(not h for h in hits):
        return {'status': 'NO_EXACT_DIRECTED_SEGMENT'}
    if any(len(h) != 1 for h in hits):
        return {'status': 'AMBIGUOUS_EXACT_SEGMENT'}
    path = [h[0] for h in hits]
    if any(endpoints[a][1] != endpoints[b][0] for a, b in zip(path, path[1:])):
        return {'status': 'PUBLIC_NODE_DISCONNECTED'}
    return {'status': 'EXACT_UNIQUE_CONNECTED', 'edges': path,
            'source': endpoints[path[0]][0], 'target': endpoints[path[-1]][1]}


def trajectory_reason(path, times, mapping):
    if not path:
        return 'EMPTY_PATH'
    if any(type(e) is not int or str(e) not in mapping for e in path):
        return 'UNKNOWN_START_ROAD'
    if len(times) != len(path):
        return 'TIME_LENGTH_MISMATCH'
    if any(type(t) not in (int, float) or not __import__('math').isfinite(t) for t in times):
        return 'INVALID_TIME'
    if any(b < a for a, b in zip(times, times[1:])):
        return 'TIME_NONMONOTONE'
    mapped = [mapping[str(e)] for e in path]
    if any(r['status'] != 'EXACT_UNIQUE_CONNECTED' for r in mapped):
        return 'UNMAPPED_ROAD'
    for a, b, ma, mb in zip(path, path[1:], mapped, mapped[1:]):
        if a != b and ma['target'] != mb['source']:
            return 'PUBLIC_TRANSITION_DISCONNECTED'
    return 'MAPPING_ELIGIBLE'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--archive-sha256', required=True)
    p.add_argument('--public-manifest', type=Path, required=True)
    p.add_argument('--public-manifest-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    started = time.monotonic()
    if a.out.exists():
        p.error('Output exists; keep evidence and choose a new directory')
    if sha(a.archive) != a.archive_sha256 or sha(a.public_manifest) != a.public_manifest_sha256:
        raise ValueError('Source binding mismatch')
    manifest = json.loads(a.public_manifest.read_text(encoding='utf-8'))
    if manifest['dataset'] != 'porto':
        raise ValueError('Expected Porto public graph')
    for name, digest in manifest['outputs'].items():
        file = a.public_manifest.parent / name
        if file.parent.resolve() != a.public_manifest.parent.resolve() or sha(file) != digest:
            raise ValueError('Public graph artifact mismatch: ' + name)
    import pyogrio
    from pyproj import CRS, Transformer
    candidates = defaultdict(list)
    endpoints = {}
    author_graph = manifest.get('status') == 'AUTHOR_PRE_VOCABULARY_GRAPH_EXPORTED'
    public_geometry = {}
    network_path = a.public_manifest.parent / 'network.shp'
    info = pyogrio.read_info(network_path)
    if CRS(info['crs']) != CRS(manifest['projected_crs']):
        raise ValueError('Graph CRS mismatch')
    transform = Transformer.from_crs(info['crs'], 'EPSG:4326', always_xy=True)
    for offset in range(0, info['features'], 10000):
        network = pyogrio.read_dataframe(network_path, skip_features=offset, max_features=10000,
                                         columns=['id', 'source', 'target'])
        for feature in network.itertuples():
            edge = int(feature.id)
            if edge in endpoints:
                raise ValueError('Repeated public edge ID')
            geom = feature.geometry
            if geom.geom_type != 'LineString' or (not author_graph and len(geom.coords) != 2):
                raise ValueError('Expected public segment graph')
            points = [point(transform.transform(*c)) for c in geom.coords]
            endpoints[edge] = (int(feature.source), int(feature.target))
            if author_graph:
                public_geometry[edge] = points
            else:
                candidates[tuple(points)].append(edge)
    a.out.mkdir(parents=True)
    mapping = {}
    counts = Counter(); duplicates = Counter(); lengths = Counter()
    database = sqlite3.connect(a.out / 'duplicate_audit.sqlite')
    database.execute('CREATE TABLE seen(digest TEXT PRIMARY KEY, split TEXT, row_number INTEGER)')
    with zipfile.ZipFile(a.archive) as z:
        bound_mapping = json.loads((a.public_manifest.parent/'road_mapping.json').read_text(encoding='utf-8')) if author_graph else None
        for row in rows(z, 'porto_roadmap_edge/porto_roadmap_edge.geo'):
            key = str(int(row['geo_id']))
            if key in mapping:
                raise ValueError('Duplicate START road ID')
            coords = json.loads(row['coordinates'])
            if author_graph:
                binding = bound_mapping[key]
                edge_path = binding['edges']
                if not edge_path: raise ValueError('Empty source edge binding')
                joined = list(public_geometry[edge_path[0]])
                for previous, edge in zip(edge_path, edge_path[1:]):
                    if endpoints[previous][1] != endpoints[edge][0] or joined[-1] != public_geometry[edge][0]:
                        raise ValueError('Disconnected source geometry representation')
                    joined.extend(public_geometry[edge][1:])
                # Consecutive identical geometry vertices do not constitute a road segment.
                expected = [point(p) for p in coords]
                expected = [v for i,v in enumerate(expected) if i==0 or v!=expected[i-1]]
                if joined != expected:
                    raise ValueError('Author geometry differs from exported graph')
                if (endpoints[edge_path[0]][0],endpoints[edge_path[-1]][1]) != (binding['source'], binding['target']):
                    raise ValueError('Author topology differs from exported graph')
                mapping[key] = binding
            else:
                mapping[key] = map_road(coords, candidates, endpoints)
        (a.out / 'road_mapping.json').write_text(json.dumps(mapping, indent=2), encoding='utf-8')
        del candidates, endpoints
        with (a.out / 'trajectory_audit.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['original_split', 'row_number', 'source_id', 'road_count', 'status', 'duplicate_of'])
            for split in ('train', 'eval', 'test'):
                for number, row in enumerate(rows(z, f'porto/porto_{split}.csv', ';')):
                    path = json.loads(row['path']); times = json.loads(row['tlist'])
                    reason = trajectory_reason(path, times, mapping)
                    digest = hashlib.sha256(json.dumps([path, times], separators=(',', ':')).encode()).hexdigest()
                    previous = database.execute('SELECT split,row_number FROM seen WHERE digest=?', (digest,)).fetchone()
                    if previous:
                        duplicates[f'{previous[0]}->{split}'] += 1
                    else:
                        database.execute('INSERT INTO seen VALUES(?,?,?)', (digest, split, number))
                    writer.writerow([split, number, row.get('id', ''), len(path), reason,
                                     f'{previous[0]}:{previous[1]}' if previous else ''])
                    counts[f'{split}:{reason}'] += 1
                    lengths[f'{reason}:{len(path)}'] += 1
                    if (number + 1) % 100000 == 0:
                        database.commit()
                        print(json.dumps({'split': split, 'processed': number + 1}), flush=True)
                database.commit()
    database.close()
    result = dict(status='MAPPING_AUDIT_COMPLETE_NOT_FROZEN', argv=[sys.executable, *sys.argv],
                  source_sha256=a.archive_sha256, public_manifest_sha256=a.public_manifest_sha256,
                  code_sha256=sha(__file__), road_status=dict(Counter(r['status'] for r in mapping.values())),
                  trajectory_status=dict(counts), duplicate_path_time_pairs=dict(duplicates),
                  lengths=dict(lengths), elapsed_seconds=time.monotonic() - started,
                  timestamp_semantics='START processed road-aligned timestamps; not raw GPS times',
                  acceptance=('author road identity plus exact directed polyline and public node continuity' if author_graph else 'exact unique directed segments at seven decimals and public node continuity'),
                  outputs={f.name: sha(f) for f in a.out.iterdir() if f.is_file()})
    (a.out / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('lengths', 'argv')}, indent=2))


if __name__ == '__main__':
    main()

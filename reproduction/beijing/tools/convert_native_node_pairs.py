"""Represent native node-pair walks as public edge IDs; never select or fill a route."""
import argparse
import gzip
import hashlib
import json
import pickle
from pathlib import Path


def canonical_pairs(frame):
    """Parallel IDs are interchangeable only for identical directed geometry."""
    pairs, geometry = {}, {}
    for row in frame[['id','source','target','geometry']].itertuples(index=False):
        pair = (int(row.source), int(row.target))
        if pair in geometry and not geometry[pair].equals_exact(row.geometry, 1e-8):
            raise ValueError(f'Ambiguous physical geometry for node pair {pair}')
        geometry[pair] = row.geometry
        pairs[pair] = min(int(row.id), pairs.get(pair, int(row.id)))
    return pairs


def convert(raw, pairs):
    records = []
    for i, route in enumerate(raw):
        route = [tuple(map(int, pair)) for pair in route]
        if any(len(pair) != 2 for pair in route):
            raise ValueError('Native route is not a node-pair walk')
        if any(a[1] != b[0] for a,b in zip(route, route[1:])):
            raise ValueError('Native route is disconnected; no repair permitted')
        if any(pair not in pairs for pair in route):
            raise ValueError('Native route contains an unknown public node pair')
        records.append({'source_index':i, 'accepted':bool(route),
                        'cpath':[pairs[pair] for pair in route],
                        'reason':'accepted' if route else 'empty_native_slot'})
    return records


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--routes', type=Path, required=True)
    p.add_argument('--network', type=Path, required=True)
    p.add_argument('--expected-slots', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    a=p.parse_args()
    if a.out.exists():
        p.error('Choose a new output directory')
    import geopandas as gpd
    with gzip.open(a.routes,'rb') as f:
        raw=pickle.load(f)
    if len(raw)!=a.expected_slots:
        raise ValueError('Wrong number of native output slots')
    pairs=canonical_pairs(gpd.read_file(a.network))
    records=convert(raw,pairs)
    a.out.mkdir(parents=True)
    output=a.out/'synthetic_routes.pkl.gz'
    with gzip.open(output,'wb',compresslevel=3) as f:
        pickle.dump(records,f,pickle.HIGHEST_PROTOCOL)
    meta={'classification':'NATIVE_ROAD_REPRESENTATION_ONLY', 'rematched':False,
          'gap_filling':False,'route_selection':False,'records':len(records),
          'native_sha256':sha(a.routes),'public_network_sha256':sha(a.network),
          'output_sha256':sha(output),'source_representation':'physical_node_pairs',
          'policy':'Minimum ID only among edges with identical directed geometry; reject ambiguity otherwise'}
    (a.out/'route_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta,indent=2))


if __name__=='__main__':
    main()

"""Represent native node-pair walks as public edge IDs; never select or fill a route."""
import argparse
import gzip
import hashlib
import json
import pickle
from collections import defaultdict
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


def source_pairs(cache, frame):
    """Join explicit source nodes to physical geometry only through shared edge IDs."""
    physical_ids = set(map(int, frame['id']))
    if set(map(int, cache['edge_nodes'])).difference(physical_ids):
        raise ValueError('Source edge is absent from selected public network')
    return resolve_pairs(cache['edge_nodes'], frame=frame)


def resolve_pairs(source_edges, metric_edges=None, *, frame=None, network=None,
                  required_pairs=None):
    """Canonicalize aliases, never choose between physically different roads.

    Explicit source and metric namespaces join only by edge ID. Parallel IDs
    need proof of equal directed geometry AND endpoints; without that proof
    ambiguity is still an error. Only used pairs need resolution when supplied.
    """
    groups = defaultdict(list)
    for edge, pair in source_edges.items():
        pair = tuple(map(int, pair))
        if required_pairs is None or pair in required_pairs:
            groups[pair].append(int(edge))
    if required_pairs is not None and set(required_pairs).difference(groups):
        raise ValueError('Unknown source node pair')
    if metric_edges is not None:
        missing = {edge for ids in groups.values() for edge in ids}.difference(metric_edges)
        if missing:
            raise ValueError('No shared public edge ID for source node pairs')
    aliases = {edge for ids in groups.values() if len(ids)>1 for edge in ids}
    if aliases and frame is None and network is not None:
        import geopandas as gpd
        # Bound the extra geometry read to parallel IDs, not the whole graph.
        frame = gpd.read_file(network, where='id IN ('+','.join(map(str,sorted(aliases)))+')')
    physical = {}
    if frame is not None:
        for row in frame[['id','source','target','geometry']].itertuples(index=False):
            edge = int(row.id)
            if edge in aliases:
                if edge in physical:
                    raise ValueError('Ambiguous duplicate public edge ID')
                physical[edge] = row
    pairs = {}
    for pair, ids in groups.items():
        if len(ids)>1:
            if any(edge not in physical for edge in ids):
                raise ValueError(f'Ambiguous source node pair {pair}: missing public geometry proof')
            first = physical[ids[0]]
            for edge in ids:
                row = physical[edge]
                if (row.source,row.target)!=(first.source,first.target) or (
                    row.geometry is None or first.geometry is None or
                    row.geometry.is_empty or first.geometry.is_empty or
                    not first.geometry.equals_exact(row.geometry, 1e-8)):
                    raise ValueError(f'Ambiguous source node-pair geometry {pair}')
                if metric_edges is not None and tuple(metric_edges[edge])!=tuple(metric_edges[ids[0]]):
                    raise ValueError(f'Ambiguous metric endpoints for source pair {pair}')
        pairs[pair] = min(ids)
    return pairs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--routes', type=Path, required=True)
    p.add_argument('--network', type=Path, required=True)
    p.add_argument('--source-cache', type=Path, help='Explicit native node namespace; joined by shared edge IDs')
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
    frame=gpd.read_file(a.network)
    if a.source_cache:
        with gzip.open(a.source_cache,'rb') as f: cache=pickle.load(f)
        pairs=source_pairs(cache,frame)
    else:
        pairs=canonical_pairs(frame)
    records=convert(raw,pairs)
    a.out.mkdir(parents=True)
    output=a.out/'synthetic_routes.pkl.gz'
    with gzip.open(output,'wb',compresslevel=3) as f:
        pickle.dump(records,f,pickle.HIGHEST_PROTOCOL)
    meta={'classification':'NATIVE_ROAD_REPRESENTATION_ONLY', 'rematched':False,
          'gap_filling':False,'route_selection':False,'records':len(records),
          'native_sha256':sha(a.routes),'public_network_sha256':sha(a.network),
          'converter_sha256':sha(Path(__file__)),
          'output_sha256':sha(output),'source_representation':'physical_node_pairs',
          'policy':'Minimum ID only among edges with identical directed geometry; reject ambiguity otherwise'}
    if a.source_cache:
        meta.update(source_cache_sha256=sha(a.source_cache), source_representation='explicit_source_node_pairs')
    (a.out/'route_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta,indent=2))


if __name__=='__main__':
    main()

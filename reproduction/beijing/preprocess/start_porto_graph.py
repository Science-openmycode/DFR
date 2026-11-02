"""Export the author-provided pre-vocabulary Porto graph without reading trips."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import pickle
import sys
import time
import zipfile
from start_porto import rows, point, sha


def original_graph(z):
    roads = {int(r['geo_id']): r for r in rows(z, 'porto_roadmap_edge/porto_roadmap_edge.geo')}
    connections = {(int(r['origin_id']), int(r['destination_id']))
                   for r in rows(z, 'porto_roadmap_edge/porto_roadmap_edge.rel')}
    coordinates = {k: json.loads(r['coordinates']) for k, r in roads.items()}
    starts = defaultdict(list)
    for k, ps in coordinates.items():
        if len(ps) < 2: raise ValueError('Invalid road geometry')
        starts[point(ps[0])].append(k)
    implied = {(k, j) for k, ps in coordinates.items() for j in starts[point(ps[-1])]}
    if implied != connections:
        raise ValueError('Endpoint graph differs from author connection table')
    return roads, coordinates, connections


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--archive-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--directed-carrier', action='store_true',
                   help='Opt in to source-directed DFR carrier; never modify old resources')
    p.add_argument('--segment-edges', action='store_true',
                   help='Represent source polylines by their existing directed geometry segments')
    a = p.parse_args(); started = time.monotonic()
    if a.out.exists(): p.error('Choose a new output directory')
    if sha(a.archive) != a.archive_sha256: raise ValueError('Archive changed')
    with zipfile.ZipFile(a.archive) as z:
        roads, coordinates, connections = original_graph(z)
        source_files = {name: __import__('hashlib').sha256(z.read(name)).hexdigest() for name in
                        ('porto_roadmap_edge/porto_roadmap_edge.geo','porto_roadmap_edge/porto_roadmap_edge.rel')}
    import geopandas as gpd
    from shapely.geometry import LineString
    from pyproj import Transformer
    project = Transformer.from_crs(4326, 32629, always_xy=True)
    # Stable derived public node IDs; never described as original OSM IDs.
    all_points = sorted({point(p) for ps in coordinates.values() for p in ps})
    nodes = {p: i+1 for i,p in enumerate(all_points)}
    records = []; mapping = {}; ways = []
    segment_ids = {}
    if a.segment_edges:
        segments = sorted({(point(u),point(v)) for ps in coordinates.values()
                           for u,v in zip(ps,ps[1:]) if point(u)!=point(v)})
        segment_ids = {pair:i+1 for i,pair in enumerate(segments)}
        for (u,v), eid in segment_ids.items():
            geom = LineString([project.transform(*u),project.transform(*v)])
            records.append(dict(id=eid,source=nodes[u],target=nodes[v],
                                length_m=float(geom.length),geometry=geom))
    for edge, k in enumerate(sorted(roads), 1):
        ps=coordinates[k]; source=nodes[point(ps[0])]; target=nodes[point(ps[-1])]
        geometry=LineString([project.transform(*p[:2]) for p in ps])
        if geometry.length <= 0: raise ValueError('Zero public geometry length')
        if not a.segment_edges:
            records.append(dict(id=edge, source=source, target=target, length_m=float(geometry.length),
                                highway=roads[k]['highway'], geometry=geometry))
        bound_edges = ([segment_ids[point(u),point(v)] for u,v in zip(ps,ps[1:]) if point(u)!=point(v)]
                       if a.segment_edges else [edge])
        if not bound_edges: raise ValueError('Empty source-road representation')
        mapping[str(k)]=dict(edges=bound_edges, source=source,target=target,status='EXACT_UNIQUE_CONNECTED')
        ways.append(dict(id=edge,nodes=[nodes[point(p)] for p in ps],
                         geometry=[dict(lon=p[0],lat=p[1]) for p in ps],
                         tags=dict(highway=roads[k]['highway'],oneway='yes'),
                         source='START_pre_vocabulary_road',source_road_id=k))
        if a.directed_carrier:
            ways[-1]['graph_policy'] = 'source_directed_v1'
    a.out.mkdir(parents=True)
    gpd.GeoDataFrame(records,geometry='geometry',crs='EPSG:32629').to_file(a.out/'network.shp',index=False)
    (a.out/'road_mapping.json').write_text(json.dumps(mapping,indent=2),encoding='utf-8')
    with (a.out/'public_ways.pkl').open('wb') as f:pickle.dump(ways,f,pickle.HIGHEST_PROTOCOL)
    bounds=gpd.GeoSeries([LineString(ps) for ps in coordinates.values()],crs=4326).total_bounds
    manifest=dict(dataset='porto',status='AUTHOR_PRE_VOCABULARY_GRAPH_EXPORTED',projected_crs='EPSG:32629',
        bbox=[41.1,41.2,-8.7,-8.55],geometry_extent_lon_lat=bounds.tolist(),
        archive_sha256=a.archive_sha256,archive_members=source_files,road_count=len(roads),relation_count=len(connections),
        topology='author directed road polylines; all endpoint adjacencies equal original rel including self loops',
        mapping=('source road to its ordered existing geometry segments; identical directed segments share IDs'
                 if a.segment_edges else 'one source road to one public directed polyline'),
        edge_count=len(records), representation='directed_segments' if a.segment_edges else 'directed_polylines',
        provenance='Author-provided pre-vocabulary graph; use authorized by user on 2026-10-28',
        source_limit='Original OSM extraction date and upstream extraction recipe are not included in the archive',
        osm_compatibility='Derived way representation, not original OSM node/way IDs; no trajectory reads',
        coordinate_order='source lon/lat; network UTM zone29N',
        carrier_policy='source_directed_v1' if a.directed_carrier else 'legacy_undirected',
        argv=[sys.executable,*sys.argv],code_sha256=sha(__file__),elapsed_seconds=time.monotonic()-started,
        outputs={f.name:sha(f) for f in a.out.iterdir() if f.is_file()})
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()

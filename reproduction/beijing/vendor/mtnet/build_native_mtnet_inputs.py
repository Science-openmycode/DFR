"""Compile FMM output into the unmodified MTNet demo file contract."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

import geopandas as gpd


def heading(geom) -> float:
    pts = list(geom.coords)
    if len(pts) < 2:
        return 0.0
    x1, y1 = pts[0]; x2, y2 = pts[-1]
    return math.degrees(math.atan2(x2 - x1, y2 - y1))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--demo-temporal', type=Path, required=True)
    a = p.parse_args()
    prepared, out = a.prepared.resolve(), a.out.resolve()
    manifest = json.loads((prepared / 'run_manifest.json').read_text(encoding='utf-8'))
    retained_count = int(manifest['match'].get('retained_route_count', manifest['match'].get('retained_L20', 0)))
    if retained_count < 10:
        raise SystemExit('Not enough retained FMM routes to create MTNet data.')
    out.mkdir(parents=True, exist_ok=True)
    gdf = gpd.read_file(prepared / 'fmm_network.shp')
    edges = {int(row.id): row for row in gdf.itertuples()}
    max_id = max(edges)
    outgoing: dict[int, list[int]] = defaultdict(list)
    for edge_id, row in edges.items():
        outgoing[int(row.source)].append(edge_id)
    adjs: dict[int, list[int]] = {}
    for edge_id, row in edges.items():
        adjs[edge_id] = sorted(outgoing[int(row.target)])
    width = max(1, max(map(len, adjs.values())))
    kinds = {'motorway': 0, 'trunk': 1, 'primary': 2, 'secondary': 3, 'tertiary': 4,
             'residential': 5, 'service': 6}
    with (out / 'edge_property.txt').open('w', encoding='utf-8') as fp, (out / 'edge_adj.txt').open('w', encoding='utf-8') as fa:
        for edge_id in range(1, max_id + 1):
            row = edges.get(edge_id)
            if row is None:
                fp.write(f'{edge_id},0,0,0,LINESTRING EMPTY\n')
                fa.write(','.join(['-1'] * width) + '\n')
                continue
            road_type = kinds.get(str(row.highway).split(';')[0], 6)
            fp.write(f'{edge_id},{float(row.length_m):.6f},{road_type},{heading(row.geometry):.6f},{row.geometry.wkt}\n')
            values = adjs[edge_id] + [-1] * (width - len(adjs[edge_id]))
            fa.write(','.join(map(str, values)) + '\n')
    shutil.copy2(prepared / 'trajs_demo.csv', out / 'trajs_demo.csv')
    shutil.copy2(prepared / 'tstamps_demo.csv', out / 'tstamps_demo.csv')
    shutil.copy2(a.demo_temporal, out / 'temporal_32.emb')
    (out / 'native_input_manifest.json').write_text(json.dumps({
        'source_preprocessing': str(prepared), 'edge_id_contract': 'FMM ids retained; absent ids are mask-only rows',
        'edge_count_active': len(edges), 'edge_embedding_rows': max_id + 2, 'adjacency_width': width,
        'trajectories': retained_count, 'max_route_edges': manifest['paper_constraints']['max_route_edges'],
        'train_test': manifest['match']['split'],
        'non_dp': True, 'mtr_components_used': False}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

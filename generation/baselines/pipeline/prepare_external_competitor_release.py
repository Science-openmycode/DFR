"""Normalize external MTNet/PUTS outputs for the strict Figure-2 renderer."""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import wkt


def edge_routes_to_latlon(
    route_file: Path, edge_property: Path, source_crs: str
) -> list[np.ndarray]:
    """Convert MTNet's native edge geometry into WGS84 [lat, lon] paths.

    MTNet's Beijing ``edge_property.txt`` follows the FMM network CRS
    (WGS84 / UTM zone 50N), rather than storing longitude/latitude directly.
    Treating its meter coordinates as degrees silently produces an empty map
    panel and invalid road metrics.
    """
    with route_file.open('rb') as f:
        payload = pickle.load(f)
    routes = payload['mtnet_paper_dpsgd']
    geometry = {}
    with edge_property.open('r', encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split(',', 4)
            if len(parts) != 5:
                continue
            try:
                geometry[int(parts[0])] = wkt.loads(parts[4].strip().strip('"'))
            except (ValueError, TypeError):
                continue
    transformer = Transformer.from_crs(source_crs, 'EPSG:4326', always_xy=True)
    out = []
    for route in routes:
        points = []
        for edge in route:
            geom = geometry.get(int(edge))
            if geom is None:
                continue
            coords = list(geom.coords)
            latlon = []
            for x, y in coords:
                lon, lat = transformer.transform(x, y)
                if np.isfinite(lat) and np.isfinite(lon):
                    latlon.append([lat, lon])
            if points and latlon and np.allclose(points[-1], latlon[0]):
                latlon = latlon[1:]
            points.extend(latlon)
        if len(points) >= 2:
            out.append(np.asarray(points, dtype=float))
    return out


def load_puts(path: Path) -> list[np.ndarray]:
    with path.open('rb') as f:
        raw = pickle.load(f)
    out = []
    for trajectory in raw:
        arr = np.asarray(trajectory, dtype=float)
        if arr.ndim == 2 and arr.shape[1] >= 2 and len(arr) >= 2:
            out.append(arr[:, :2])
    return out


def save(path: Path, trajectories: list[np.ndarray], expected: int, label: str) -> None:
    if len(trajectories) != expected:
        raise RuntimeError(f'{label} has {len(trajectories)} drawable trajectories; expected {expected}')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as f:
        pickle.dump(trajectories, f, protocol=pickle.HIGHEST_PROTOCOL)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--mtnet-routes', type=Path, required=True)
    p.add_argument('--edge-property', type=Path, required=True,
                   help='MTNet-native continuous edge-index geometry file')
    p.add_argument('--mtnet-out', type=Path, required=True)
    p.add_argument('--source-crs', default='EPSG:32650',
                   help='CRS of MTNet edge_property geometry (Beijing FMM: EPSG:32650)')
    p.add_argument('--puts-input', type=Path)
    p.add_argument('--puts-out', type=Path)
    p.add_argument('--expected-count', type=int, required=True)
    a = p.parse_args()
    save(a.mtnet_out, edge_routes_to_latlon(a.mtnet_routes, a.edge_property, a.source_crs), a.expected_count, 'MTNet')
    if (a.puts_input is None) != (a.puts_out is None):
        p.error('--puts-input and --puts-out must be supplied together')
    if a.puts_input is not None:
        save(a.puts_out, load_puts(a.puts_input), a.expected_count, 'PUTS')


if __name__ == '__main__':
    main()

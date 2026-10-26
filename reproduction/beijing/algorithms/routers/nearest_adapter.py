"""Nearest-public-road router for coordinate M outputs."""

from __future__ import annotations

import gzip
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np


ROUTER = "Nearest"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pickle(path: Path):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as handle:
        return pickle.load(handle)


def _edge_nodes(path: Path) -> dict[int, tuple[int, int]]:
    value = load_pickle(path)
    if not isinstance(value, dict) or "edge_nodes" not in value:
        raise ValueError("edge cache must contain edge_nodes")
    return {int(k): tuple(map(int, v)) for k, v in value["edge_nodes"].items()}


def _connected(edge_ids: list[int], edge_nodes: dict[int, tuple[int, int]]) -> bool:
    return bool(edge_ids) and all(
        edge_ids[i] in edge_nodes and edge_ids[i + 1] in edge_nodes
        and edge_nodes[edge_ids[i]][1] == edge_nodes[edge_ids[i + 1]][0]
        for i in range(len(edge_ids) - 1)
    )


def run_nearest(measurement: Path, out_dir: Path, *, network: Path, edge_cache: Path, input_srs: str = "EPSG:4326") -> dict:
    """Map each published coordinate to its nearest public edge.

    This baseline intentionally does not fill gaps between nearest-edge
    choices. Disconnected sequences remain rejected instead of being silently
    completed by a shortest-path query.
    """
    import geopandas as gpd
    from pyproj import Transformer
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    for path, label in ((measurement, "measurement"), (network, "public network"), (edge_cache, "edge cache")):
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite route output: {out_dir}")
    out_dir.mkdir(parents=True)
    try:
        trajectories = load_pickle(measurement)
        frame = gpd.read_file(network)
    except Exception as error:
        manifest = {
            "schema_version": 1, "kind": "route_cell", "router": ROUTER,
            "route_generation": "executed_public_nearest_edge", "status": "INVALID",
            "raw_source_used": False, "measurement": str(measurement.resolve()),
            "measurement_sha256": sha256(measurement) if measurement.is_file() else None,
            "public_network": str(network.resolve()),
            "public_network_sha256": sha256(network) if network.is_file() else None,
            "edge_cache": str(edge_cache.resolve()),
            "edge_cache_sha256": sha256(edge_cache) if edge_cache.is_file() else None,
            "error_type": type(error).__name__, "error": str(error),
        }
        (out_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    if "id" not in frame.columns:
        raise ValueError("public network must provide an id column")
    edge_nodes = _edge_nodes(edge_cache)
    if not frame.crs:
        raise ValueError("public network has no CRS")
    transformer = Transformer.from_crs(input_srs, frame.crs, always_xy=True)
    geometries = list(frame.geometry)
    tree = STRtree(geometries)
    routes = []
    reasons: dict[str, int] = {}
    for index, trajectory in enumerate(trajectories):
        edge_ids: list[int] = []
        try:
            for point in np.asarray(trajectory, dtype=float)[:, :2]:
                lat, lon = float(point[0]), float(point[1])
                x, y = transformer.transform(lon, lat)
                nearest = tree.nearest(Point(x, y))
                position = int(nearest) if isinstance(nearest, (int, np.integer)) else geometries.index(nearest)
                edge_ids.append(int(frame.iloc[position]["id"]))
            deduped: list[int] = []
            for edge_id in edge_ids:
                if not deduped or deduped[-1] != edge_id:
                    deduped.append(edge_id)
            if not deduped:
                reason = "empty"
            elif any(edge_id not in edge_nodes for edge_id in deduped):
                reason = "unknown_edge"
            elif not _connected(deduped, edge_nodes):
                reason = "disconnected"
            else:
                reason = "accepted"
        except (TypeError, ValueError, IndexError, OverflowError):
            deduped, reason = [], "invalid_coordinate"
        accepted = reason == "accepted"
        reasons[reason] = reasons.get(reason, 0) + 1
        routes.append({"source_index": index, "accepted": accepted, "cpath": deduped if accepted else [], "reason": reason})
    output = out_dir / "synthetic_routes.pkl.gz"
    with gzip.open(output, "wb", compresslevel=6) as handle:
        pickle.dump(routes, handle, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {"schema_version": 1, "kind": "route_cell", "router": ROUTER, "route_generation": "executed_public_nearest_edge", "status": "VALID", "raw_source_used": False, "measurement": str(measurement.resolve()), "measurement_sha256": sha256(measurement), "public_network": str(network.resolve()), "public_network_sha256": sha256(network), "edge_cache": str(edge_cache.resolve()), "edge_cache_sha256": sha256(edge_cache), "input_srs": input_srs, "records": len(routes), "reasons": reasons, "output": str(output), "output_sha256": sha256(output)}
    (out_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest

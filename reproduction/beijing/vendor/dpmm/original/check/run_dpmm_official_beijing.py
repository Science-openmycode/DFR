"""Run the released official DPMM implementation on public-protocol data.

The adapter deliberately delegates the private trajectory transformation to
``lbnl-cybersecurity/DPMM``'s ``MapMatching`` class.  It builds the same three
objects expected by that class (projected edge GeoDataFrame, projected node
GeoDataFrame, and directed NetworkX road graph) from the repository's cached
OSM extract.  It then invokes the official clean-map-match, RDP waypoint,
Planar-Laplace OD, A* candidate, exponential-selection, and loop-removal
methods in their published order.

Only two compatibility changes live in the vendored official file: an import
guard and a parameterized UTM zone.  See ``DPMM_OFFICIAL_ALIGNMENT_AUDIT.md``.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import importlib.util
import json
import pickle
import random
import sys
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import LineString, Point, box

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
OFFICIAL_ROOT = PUBLIC_RELEASE / "check" / "official_repos" / "dpmm"
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))
if str(OFFICIAL_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFICIAL_ROOT))

from public_utils import (  # noqa: E402
    bbox_dict,
    filter_osm_ways_by_bbox,
    load_osm_ways,
    load_trajectories,
    parse_bbox,
    save_trajectories_pkl,
    write_json,
)


DRIVE_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road",
}

# Each DPMM invocation is a per-input-record mechanism.  These process-local
# objects let independent records use the authors' exact routine concurrently
# without sharing mutable matcher state or changing candidate semantics.
_WORKER_MM = None
_WORKER_OFFICIAL = None
_WORKER_MODE = "rdp"
_WORKER_SEED = 0
_WORKER_MAX_WAYPOINTS = None


def log(message: str) -> None:
    print(f"[DPMM official] {time.strftime('%H:%M:%S')} {message}", flush=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Official DPMM adapter for cached public OSM and trajectory files.")
    p.add_argument("--data", default="geolife")
    p.add_argument("--input-pkl", default=None, help="Optional aligned trajectory pickle; bypasses dataset loader for a declared audit subset.")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    p.add_argument("--epsilon", type=float, default=1.0, help="official DPMM epsilon passed to each trajectory release")
    p.add_argument("--limit", type=int, default=None, help="optional deterministic input prefix for an audit smoke test")
    p.add_argument(
        "--max-input-points",
        type=int,
        default=None,
        help="retain only trajectories with at most this many raw points; used for official-entrypoint frequency audits",
    )
    p.add_argument("--seed", type=int, default=20260714, help="global seed before the official per-link seeding")
    p.add_argument("--zone-radius-m", type=float, default=25.0, help="official example's initial buffer radius in metres")
    p.add_argument("--utm-zone-number", type=int, default=50)
    p.add_argument("--utm-zone-letter", default="S")
    p.add_argument(
        "--clean-seed-waypoint-mode",
        choices=["raw", "rdp"],
        default="rdp",
        help=(
            "raw reproduces the released example's all-point clean seed pass; "
            "rdp applies the paper Algorithm-3 waypoint representation before that seed pass"
        ),
    )
    p.add_argument(
        "--max-waypoints", type=int, default=None,
        help="optional public endpoint-preserving cap after official RDP waypoint selection",
    )
    p.add_argument("--checkpoint-every", type=int, default=25, help="write a monitor-only partial release every N processed records; 0 disables")
    p.add_argument("--workers", type=int, default=1, help="independent official per-record workers; 1 preserves serial execution")
    p.add_argument("--resume", action="store_true", help="continue from this tag's monitor-only prefix checkpoint")
    p.add_argument("--out-dir", default=str(PUBLIC_RELEASE / "outputs" / "external_competitors" / "dpmm_official_beijing"))
    p.add_argument("--tag", default="dpmm_official_eps1_full")
    return p


def load_official_module():
    path = OFFICIAL_ROOT / "map_matcher_traj_AStar_clean_taxi.py"
    if not path.exists():
        raise FileNotFoundError(f"official DPMM source missing: {path}")
    spec = importlib.util.spec_from_file_location("official_dpmm", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the official DPMM module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # OSMnx 2 moved this helper; preserve the function signature used by the
    # official source rather than changing its trajectory algorithm.
    if not hasattr(module.ox, "project_gdf"):
        module.ox.project_gdf = ox.projection.project_gdf
    return module, path


def _node_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(float(lat), 7), round(float(lon), 7))


def build_official_inputs(osm_ways: list[dict], bbox_values: tuple[float, float, float, float]):
    """Build the public OSMnx-style input objects consumed by official DPMM."""
    node_ids: dict[tuple[float, float], int] = {}
    node_records: list[dict] = []
    directed: dict[tuple[int, int], dict] = {}

    def node_id(lat: float, lon: float) -> int:
        key = _node_key(lat, lon)
        if key not in node_ids:
            idx = len(node_ids)
            node_ids[key] = idx
            node_records.append({"node": idx, "geometry": Point(float(lon), float(lat))})
        return node_ids[key]

    for way in osm_ways:
        tags = way.get("tags", {}) if isinstance(way, dict) else {}
        highway = str(tags.get("highway", ""))
        if highway not in DRIVE_HIGHWAYS:
            continue
        geometry = way.get("geometry", [])
        coords = [(float(p["lat"]), float(p["lon"])) for p in geometry if "lat" in p and "lon" in p]
        for (a_lat, a_lon), (b_lat, b_lon) in zip(coords[:-1], coords[1:]):
            if (a_lat, a_lon) == (b_lat, b_lon):
                continue
            a, b = node_id(a_lat, a_lon), node_id(b_lat, b_lon)
            row = {
                "u": a,
                "v": b,
                "osmid": int(way.get("id", 0)),
                "highway": highway,
                "geometry": LineString([(a_lon, a_lat), (b_lon, b_lat)]),
            }
            directed.setdefault((a, b), row)
            if str(tags.get("oneway", "")).lower() not in {"yes", "1", "true"}:
                reverse = {
                    "u": b,
                    "v": a,
                    "osmid": int(way.get("id", 0)),
                    "highway": highway,
                    "geometry": LineString([(b_lon, b_lat), (a_lon, a_lat)]),
                }
                directed.setdefault((b, a), reverse)

    if not directed:
        raise RuntimeError("cached OSM extract produced zero drivable directed edges")
    nodes = gpd.GeoDataFrame(node_records, geometry="geometry", crs="EPSG:4326").set_index("node")
    edges = gpd.GeoDataFrame(list(directed.values()), geometry="geometry", crs="EPSG:4326").set_index(["u", "v"])
    nodes_projected = ox.projection.project_gdf(nodes)
    edges_projected = ox.projection.project_gdf(edges, to_crs=nodes_projected.crs)
    graph = nx.DiGraph()
    graph.add_nodes_from(int(idx) for idx in nodes_projected.index)
    for (u, v), row in edges_projected.iterrows():
        graph.add_edge(int(u), int(v), length=float(row.geometry.length))
    lat_min, lat_max, lon_min, lon_max = bbox_values
    roi_geo = gpd.GeoDataFrame(geometry=[box(lon_min, lat_min, lon_max, lat_max)], crs="EPSG:4326")
    roi = ox.projection.project_gdf(roi_geo, to_crs=nodes_projected.crs).geometry.iloc[0]
    return edges_projected, nodes_projected, graph, roi


def _trajectory_gdf(traj: np.ndarray) -> gpd.GeoDataFrame:
    arr = np.asarray(traj, dtype=float)
    return gpd.GeoDataFrame({"geometry": [Point(float(lon), float(lat)) for lat, lon in arr[:, :2]]}, crs="EPSG:4326")


def _edge_path_to_trajectory(edge_frame: gpd.GeoDataFrame) -> np.ndarray | None:
    latlon = ox.projection.project_gdf(edge_frame, to_latlong=True)
    pts: list[list[float]] = []
    for geom in latlon.geometry:
        if geom is None or geom.is_empty:
            continue
        geoms = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        for line in geoms:
            for lon, lat in line.coords:
                point = [float(lat), float(lon)]
                if not pts or pts[-1] != point:
                    pts.append(point)
    return np.asarray(pts, dtype=float) if len(pts) >= 2 else None


def cap_waypoints(points, maximum: int | None):
    """Public, endpoint-preserving cap applied after the official RDP rule."""
    if maximum is None or len(points) <= maximum:
        return points
    if maximum < 2:
        raise ValueError("--max-waypoints must be at least 2")
    keep = np.linspace(0, len(points) - 1, int(maximum)).round().astype(int)
    return [points[int(index)] for index in keep]


def official_process_one(mm, official, traj: np.ndarray, clean_seed_waypoint_mode: str, max_waypoints: int | None = None) -> np.ndarray | None:
    """Memory-only version of the official file orchestration using its methods."""
    utm_trajectory = official.ox.project_gdf(_trajectory_gdf(traj))
    utm_trajectory = utm_trajectory.loc[utm_trajectory.intersects(official.ROI)].reset_index(drop=True)
    if len(utm_trajectory) <= 1:
        return None
    sample_points = cap_waypoints(mm.sample_waypoints(utm_trajectory), max_waypoints)
    if clean_seed_waypoint_mode == "rdp":
        clean_waypoints = gpd.GeoDataFrame({"geometry": sample_points}, crs=utm_trajectory.crs)
        clean_points = mm.trajectory_points(clean_waypoints)
    else:
        clean_points = mm.trajectory_points(utm_trajectory)
    clean_paths = mm.matched_links_traj_clean(clean_points)
    clean_nodes = mm.final_edge_path(clean_paths)
    if len(clean_nodes) < 2:
        return None
    try:
        mm.links = mm.path_to_df(clean_nodes)
    except Exception:
        return None
    if len(mm.links) == 0:
        return None
    noisy_paths = mm.matched_links_traj_noisy(sample_points)
    noisy_nodes = mm.remove_edges(mm.final_edge_path(noisy_paths))
    if len(noisy_nodes) < 2:
        return None
    try:
        return _edge_path_to_trajectory(mm.path_to_df(noisy_nodes))
    except Exception:
        return None


def install_semantic_path_cache(mm, max_entries: int = 100_000) -> None:
    """Memoize the official A* result without changing its candidate semantics.

    The released ``gen_path_list`` calls A* twice per candidate pair: once for
    the node sequence and once for its length. This wrapper computes the same
    nonnegative-length shortest-path result once per public source within a
    candidate call, then derives all target distances from it. Candidate nodes,
    distance scores, exponential selection, and loop removal are unchanged.
    """
    cache: dict[tuple[int, int], tuple[list[int], float] | None] = {}

    def gen_path_list(source_nodes, target_nodes):
        paths, distances = [], []
        for source in source_nodes:
            try:
                source_distances, source_paths = nx.single_source_dijkstra(mm.graph, int(source), weight="length")
            except Exception:
                continue
            for target in target_nodes:
                if source == target:
                    continue
                key = (int(source), int(target))
                result = cache.get(key, "missing")
                if result == "missing":
                    try:
                        result = (source_paths[int(target)], float(source_distances[int(target)]))
                    except Exception:
                        result = None
                    if len(cache) >= max_entries:
                        cache.clear()
                    cache[key] = result
                if result is not None:
                    path, length = result
                    paths.append(path)
                    distances.append(length)
        return paths, distances

    mm.gen_path_list = gen_path_list
    mm._official_adapter_path_cache = cache


def _build_matcher(config: dict):
    bbox_values = tuple(config["bbox"])
    osm = filter_osm_ways_by_bbox(load_osm_ways(config["osm_cache"]), bbox_values)
    edges, nodes, graph, roi = build_official_inputs(osm, bbox_values)
    official, official_path = load_official_module()
    official.ROI = roi
    mm = official.MapMatching(
        float(config["zone_radius_m"]), "Beijing", edges.copy(), nodes, graph, "", "",
        int(config["utm_zone_number"]), str(config["utm_zone_letter"]),
    )
    mm.folder_init(float(config["epsilon"]), "")
    install_semantic_path_cache(mm)
    return mm, official, official_path


def _init_worker(config: dict) -> None:
    global _WORKER_MM, _WORKER_OFFICIAL, _WORKER_MODE, _WORKER_SEED, _WORKER_MAX_WAYPOINTS
    _WORKER_MM, _WORKER_OFFICIAL, _ = _build_matcher(config)
    _WORKER_MODE = str(config["clean_seed_waypoint_mode"])
    _WORKER_SEED = int(config["seed"])
    _WORKER_MAX_WAYPOINTS = config.get("max_waypoints")


def _worker_process(item: tuple[int, np.ndarray]) -> tuple[int, np.ndarray | None]:
    index, trajectory = item
    # Parallel scheduling changes neither the official mechanism nor its
    # support; deterministic per-record seeding makes the artifact replayable.
    np.random.seed(_WORKER_SEED + int(index))
    random.seed(_WORKER_SEED + int(index))
    return index, official_process_one(_WORKER_MM, _WORKER_OFFICIAL, np.asarray(trajectory, dtype=float), _WORKER_MODE, _WORKER_MAX_WAYPOINTS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parser().parse_args()
    np.random.seed(args.seed)
    bbox_values = parse_bbox(args.bbox)
    log(f"loading public trajectories: {args.data}")
    if args.input_pkl:
        with Path(args.input_pkl).open("rb") as handle:
            real = [np.asarray(value, dtype=float) for value in pickle.load(handle)]
        if args.limit is not None:
            real = real[: int(args.limit)]
    else:
        real = load_trajectories(args.data, limit=args.limit)
    if args.max_input_points is not None:
        before = len(real)
        real = [t for t in real if len(t) <= int(args.max_input_points)]
        log(f"frequency audit filter <= {args.max_input_points} raw points retained {len(real):,}/{before:,} trajectories")
    log(f"loaded {len(real):,} input trajectories")
    osm = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox_values)
    log(f"building official DPMM graph from {len(osm):,} cached OSM ways")
    edges, nodes, graph, roi = build_official_inputs(osm, bbox_values)
    log(f"official graph ready: {len(nodes):,} nodes, {len(edges):,} directed edges")
    official, official_path = load_official_module()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    released: list[np.ndarray] = []
    released_input_indices: list[int] = []
    failed = 0
    started = time.time()
    partial_path = out_dir / f"{args.tag}.partial.pkl"
    partial_manifest_path = out_dir / f"{args.tag}.partial.json"
    start_index = 0
    if args.resume and partial_path.exists() and partial_manifest_path.exists():
        payload = json.loads(partial_manifest_path.read_text(encoding="utf-8"))
        start_index = int(payload.get("processed_count", 0))
        released = load_trajectories(str(partial_path), limit=None)
        released_input_indices = [int(value) for value in payload.get("released_input_indices", [])]
        if len(released_input_indices) != len(released):
            raise RuntimeError(
                "The checkpoint does not contain a complete released_input_indices ledger. "
                "Do not resume it for a recordwise audit; rerun with the current adapter."
            )
        failed = int(payload.get("failed_count", 0))
        if start_index > len(real):
            raise RuntimeError(f"checkpoint processed_count={start_index} exceeds input_count={len(real)}")
        log(f"resuming official prefix checkpoint: processed {start_index:,}/{len(real):,}; released {len(released):,}; failed {failed:,}")

    config = {
        "bbox": bbox_values, "osm_cache": args.osm_cache, "zone_radius_m": args.zone_radius_m,
        "utm_zone_number": args.utm_zone_number, "utm_zone_letter": args.utm_zone_letter,
        "epsilon": args.epsilon, "clean_seed_waypoint_mode": args.clean_seed_waypoint_mode,
        "max_waypoints": args.max_waypoints, "seed": args.seed,
    }
    pending = [(i, np.asarray(t, dtype=float)) for i, t in enumerate(real[start_index:], start=start_index + 1)]
    if int(args.workers) > 1:
        iterator = ProcessPoolExecutor(max_workers=int(args.workers), initializer=_init_worker, initargs=(config,)).map(_worker_process, pending, chunksize=1)
        serial_mm = serial_official = None
    else:
        serial_mm, serial_official, _ = _build_matcher(config)
        iterator = ((i, official_process_one(serial_mm, serial_official, trajectory, args.clean_seed_waypoint_mode, args.max_waypoints)) for i, trajectory in pending)

    for i, output in iterator:
        if i == 1 or i % 100 == 0:
            log(f"starting trajectory {i:,}/{len(real):,}")
        if output is None:
            failed += 1
        else:
            released.append(output)
            # DPMM is a recordwise mechanism and may fail to emit an output for
            # an input. Preserve the exact source pairing for release-yield and
            # recordwise attacks such as official RAoPT; never infer it later
            # from list position after failures have been dropped.
            released_input_indices.append(int(i - 1))
        if i == 1 or i % 100 == 0 or i == len(real):
            elapsed = max(time.time() - started, 1e-9)
            log(
                f"processed {i:,}/{len(real):,}; released {len(released):,}; "
                f"failed {failed:,}; {i / elapsed:.2f} trajectories/s"
            )
        if int(args.checkpoint_every) > 0 and (i % int(args.checkpoint_every) == 0 or i == len(real)):
            save_trajectories_pkl(partial_path, released)
            write_json(
                partial_manifest_path,
                {
                    "status": "in_progress" if i < len(real) else "finalizing",
                    "processed_count": i,
                    "released_count": len(released),
                    "released_input_indices": released_input_indices,
                    "failed_count": failed,
                    "input_count": len(real),
                    "output_yield_so_far": float(len(released) / max(i, 1)),
                    "elapsed_seconds": float(time.time() - started),
                    "method": "DPMM-official-adapter",
                    "clean_seed_waypoint_mode": args.clean_seed_waypoint_mode,
                    "max_waypoints": args.max_waypoints,
                    "workers": int(args.workers),
                },
            )
            log(f"checkpoint -> {partial_path.name} after {i:,} inputs")
    output_path = save_trajectories_pkl(out_dir / f"{args.tag}.pkl", released)
    manifest = {
        "method": "DPMM-official-adapter",
        "paper": "Haydari et al., ACSAC 2022, Differentially Private Map Matching for Mobility Trajectories",
        "official_repository": "https://github.com/lbnl-cybersecurity/DPMM",
        "official_entrypoint": str(official_path.resolve()),
        "official_entrypoint_sha256_after_documented_compatibility_patches": sha256(official_path),
        "privacy_unit": "per-input-trajectory link-level sanitization",
        "comparison_scope": "DPMM receives and sanitizes each source trajectory; MTR releases a central-DP synthetic population. Metrics are reported with this privacy-unit distinction.",
        "epsilon": float(args.epsilon),
        "official_code_parameters": {
            "rdp_epsilon_degrees": 0.001,
            "initial_buffer_radius_m": float(args.zone_radius_m),
            "road_buffer_link_threshold": 5,
            "path_algorithm": "official NetworkX A* with length weight",
            "path_selection": "official normalized-distance exponential selection",
            "loop_adjustment": "official remove_edges",
            "public_path_cache": "memoized official A* node-pair results; length is summed over the same selected official A* path",
            "clean_seed_waypoint_mode": args.clean_seed_waypoint_mode,
            "max_waypoints": args.max_waypoints,
            "workers": int(args.workers),
            "parallelization": "independent per-input official calls; deterministic per-record derived seeds; ordered merge",
        },
        "public_city_adapter": {
            "bbox": bbox_dict(bbox_values),
            "osm_cache": str(Path(args.osm_cache).resolve() if Path(args.osm_cache).is_absolute() else (Path.cwd() / args.osm_cache).resolve()),
            "utm_zone": f"{args.utm_zone_number}{args.utm_zone_letter}",
            "drivable_highway_classes": sorted(DRIVE_HIGHWAYS),
        },
        "input_count": len(real),
        "input_pkl": str(Path(args.input_pkl).resolve()) if args.input_pkl else None,
        "max_input_points_filter": args.max_input_points,
        "output_count": len(released),
        "released_input_indices": released_input_indices,
        "failed_count": failed,
        "output_yield": float(len(released) / max(len(real), 1)),
        "seed": int(args.seed),
        "outputs": {"pkl": str(output_path.resolve())},
        "elapsed_seconds": float(time.time() - started),
        "monitoring_checkpoint": str(partial_manifest_path.resolve()),
    }
    write_json(out_dir / f"{args.tag}.json", manifest)
    log(f"completed: {len(released):,}/{len(real):,} official DPMM releases -> {output_path}")


if __name__ == "__main__":
    main()

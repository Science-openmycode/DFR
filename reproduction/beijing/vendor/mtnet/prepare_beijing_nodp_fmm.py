"""Prepare a non-DP MTNet transfer dataset with the published input protocol.

This is deliberately separate from the withdrawn local road-edge port.  It
uses only raw GeoLife GPS, public OSM and the upstream FMM executable.  It does
not use MTR, candidate paths, anchors, rerouting or any private learned
post-processing.  The MTNet paper states FMM but not its FMM hyperparameters;
the defaults exposed by upstream FMM v0.1.1 are recorded in ``run_manifest``
instead of being presented as author-supplied settings.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString


HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parents[1]
RAW = PUBLIC / "data" / "trajectories" / "geolife" / "Geolife Trajectories 1.3" / "Data"
OSM = PUBLIC / "data" / "osm" / "osm_cache_beijing.pkl"
FMM_ROOT = PUBLIC / "third_party" / "fmm-v0.1.1" / "cyang-kth-fmm-344fb8c"
FMM = FMM_ROOT / "build" / "Release" / "fmm.exe"
UBODT = FMM_ROOT / "build" / "Release" / "ubodt_gen.exe"
BBOX = (39.75, 40.15, 116.10, 116.65)  # lat_min, lat_max, lon_min, lon_max
L = 20
csv.field_size_limit(sys.maxsize)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=HERE / "beijing_nodp_fmm")
    p.add_argument("--max-files", type=int, default=0, help="0 means every GeoLife .plt file")
    p.add_argument("--candidates", type=int, default=8, help="upstream FMM default; paper does not disclose it")
    p.add_argument("--radius-m", type=float, default=300.0, help="upstream FMM default")
    p.add_argument("--gps-error-m", type=float, default=50.0, help="upstream FMM default")
    p.add_argument("--ubodt-delta-m", type=float, default=3000.0, help="upstream FMM default")
    p.add_argument("--max-route-edges", type=int, default=L, help="finite MTNet sequence threshold L")
    p.add_argument("--workers", type=int, default=0, help="FMM OpenMP; 0 leaves its runtime default")
    p.add_argument("--resume-existing", action="store_true", help="parse already-created FMM files without rematching")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def oneway(tags: dict) -> int:
    value = str(tags.get("oneway", "")).lower()
    if value in {"yes", "true", "1"}:
        return 1
    if value in {"-1", "reverse"}:
        return -1
    return 0


def build_network(out: Path) -> tuple[Path, dict[int, float], dict[int, tuple[float, float]]]:
    """Create FMM's directed OSM edge shapefile and retain edge metadata."""
    with OSM.open("rb") as f:
        ways = pickle.load(f)
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    node_map: dict[str, int] = {}
    rows: list[dict] = []
    next_node, next_edge = 1, 1

    def node_id(osm_node: object) -> int:
        nonlocal next_node
        key = str(osm_node)
        if key not in node_map:
            node_map[key] = next_node
            next_node += 1
        return node_map[key]

    def append_edge(points: list[tuple[float, float]], start_node: object, end_node: object, highway: str) -> None:
        nonlocal next_edge
        if len(points) < 2:
            return
        coords = [to_utm.transform(lon, lat) for lat, lon in points]
        geom = LineString(coords)
        if geom.length <= 0:
            return
        rows.append({"id": next_edge, "source": node_id(start_node), "target": node_id(end_node),
                     "length_m": float(geom.length), "highway": highway[:30], "geometry": geom})
        next_edge += 1

    for way in ways:
        if not isinstance(way, dict) or way.get("type") != "way":
            continue
        tags = way.get("tags") or {}
        if "highway" not in tags:
            continue
        geom = way.get("geometry") or []
        points = [(float(p["lat"]), float(p["lon"])) for p in geom if "lat" in p and "lon" in p]
        nodes = way.get("nodes") or []
        if len(nodes) < 2 or len(points) < 2:
            continue
        direction = oneway(tags)
        if direction >= 0:
            append_edge(points, nodes[0], nodes[-1], str(tags["highway"]))
        if direction <= 0:
            append_edge(list(reversed(points)), nodes[-1], nodes[0], str(tags["highway"]))

    graph = nx.DiGraph()
    graph.add_edges_from((r["source"], r["target"]) for r in rows)
    largest = max(nx.weakly_connected_components(graph), key=len)
    rows = [r for r in rows if r["source"] in largest and r["target"] in largest]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:32650")
    network = out / "fmm_network.shp"
    gdf.to_file(network, index=False)
    lengths = {int(r["id"]): float(r["length_m"]) for r in rows}
    centroids = {int(r["id"]): (float(r["geometry"].centroid.x), float(r["geometry"].centroid.y)) for r in rows}
    return network, lengths, centroids


def read_geolife(max_files: int, gps_path: Path) -> tuple[list[dict], dict[str, int]]:
    """Read raw files without artificial path-windowing or resampling.

    A file may leave the city and return.  Such visits are distinct contiguous
    observations, not one trajectory with its outside points deleted.
    """
    out: list[dict] = []
    stats: Counter[str] = Counter()
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    with gps_path.open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.writer(fcsv, delimiter=";")
        writer.writerow(["id", "x", "y", "timestamp"])
        for i, path in enumerate(sorted(RAW.glob("*/Trajectory/*.plt")), start=1):
            if max_files and i > max_files:
                break
            stats["files_seen"] += 1
            current: list[tuple[float, float, float]] = []
            kept = 0

            def flush_segment() -> None:
                nonlocal current, kept
                if len(current) < 2:
                    current = []
                    return
                rec_id = len(out) + 1
                for lat, lon, ts in current:
                    x, y = to_utm.transform(lon, lat)
                    writer.writerow([rec_id, f"{x:.3f}", f"{y:.3f}", f"{ts:.3f}"])
                out.append({"id": rec_id, "start_ts": current[0][2], "end_ts": current[-1][2], "source": f"{path}#segment{kept}"})
                stats["segments_retained"] += 1
                stats["gps_points"] += len(current)
                kept += 1
                current = []

            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(6):
                    next(f, None)
                for line in f:
                    fields = line.strip().split(",")
                    if len(fields) < 7:
                        continue
                    try:
                        lat, lon = float(fields[0]), float(fields[1])
                        ts = datetime.strptime(fields[5] + " " + fields[6], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                    except ValueError:
                        continue
                    if BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]:
                        current.append((lat, lon, ts))
                    else:
                        flush_segment()
            flush_segment()
            if kept:
                stats["files_retained"] += 1
    return out, dict(stats)


def run(command: list[str], cwd: Path) -> None:
    print("[run]", " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def parse_matches(match_file: Path, records: list[dict], lengths: dict[int, float], out: Path, max_route_edges: int) -> dict:
    by_id = {str(r["id"]): r for r in records}
    retained: list[tuple[list[int], list[float]]] = []
    stats: Counter[str] = Counter()
    with match_file.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            stats["fmm_rows"] += 1
            ids = [int(x) for x in (row.get("cpath") or "").split(",") if x.strip().isdigit()]
            rec = by_id.get(str(row.get("id")))
            if not rec or not ids:
                stats["empty_or_invalid_match"] += 1
                continue
            if len(ids) > max_route_edges:
                stats["over_L"] += 1
                continue
            total_seconds = max(1.0, rec["end_ts"] - rec["start_ts"])
            edge_lengths = np.asarray([lengths.get(e, 0.0) for e in ids], dtype=float)
            if edge_lengths.sum() <= 0:
                stats["unknown_edge"] += 1
                continue
            tcosts = (total_seconds * edge_lengths / edge_lengths.sum()).tolist()
            retained.append((ids + [0], [rec["start_ts"]] + tcosts))
            stats[f"retained_L{max_route_edges}"] += 1
    rng = np.random.default_rng(20260711)
    order = rng.permutation(len(retained)) if retained else np.array([], dtype=int)
    split = int(0.8 * len(retained))
    split_info = {"seed": 20260711, "train": int(split), "test": int(len(retained) - split)}
    with (out / "trajs_demo.csv").open("w", encoding="utf-8") as ft, (out / "tstamps_demo.csv").open("w", encoding="utf-8") as fs:
        for idx in order:
            edges, times = retained[int(idx)]
            ft.write(" ".join(map(str, edges)) + "\n")
            fs.write(" ".join(f"{x:.3f}" for x in times) + "\n")
    return {**dict(stats), "retained_route_count": len(retained), "split": split_info,
            "retained_route_lengths": {str(k): int(v) for k, v in Counter(len(x[0]) - 1 for x in retained).items()}}


def records_from_gps_csv(path: Path) -> list[dict]:
    """Recover the only metadata needed for time interpolation after FMM."""
    records: list[dict] = []
    current_id: str | None = None
    start_ts = end_ts = 0.0
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            rid = row["id"]
            ts = float(row["timestamp"])
            if current_id is None:
                current_id, start_ts = rid, ts
            elif rid != current_id:
                records.append({"id": int(current_id), "start_ts": start_ts, "end_ts": end_ts, "source": "recovered_from_gps_csv"})
                current_id, start_ts = rid, ts
            end_ts = ts
    if current_id is not None:
        records.append({"id": int(current_id), "start_ts": start_ts, "end_ts": end_ts, "source": "recovered_from_gps_csv"})
    return records


def main() -> None:
    a = parse_args()
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()) and not a.overwrite:
        raise SystemExit(f"{out} already exists; pass --overwrite to reuse it")
    out.mkdir(parents=True, exist_ok=True)
    if a.resume_existing:
        network = out / "fmm_network.shp"
        gps = out / "raw_gps_points.csv"
        matched = out / "fmm_matches.csv"
        if not (network.exists() and gps.exists() and matched.exists()):
            raise SystemExit("--resume-existing requires fmm_network.shp, raw_gps_points.csv and fmm_matches.csv")
        gdf = gpd.read_file(network)
        lengths = {int(row.id): float(row.length_m) for row in gdf.itertuples()}
        records = records_from_gps_csv(gps)
        match_stats = parse_matches(matched, records, lengths, out, a.max_route_edges)
        manifest = {"method": "MTNet non-DP transfer preprocessing", "resumed_parse": True,
                    "paper_constraints": {"FMM": True, "directed_public_OSM": True, "max_route_edges": a.max_route_edges,
                                          "time_interpolation": "linear by matched edge length", "split": "shuffled 80/20"},
                    "not_claimed": ["author-certified Beijing preprocessing", "paper-disclosed FMM hyperparameters", "DP guarantee", "MTR or any MTR component"],
                    "network_edges": len(lengths), "matched_records": len(records), "match": match_stats}
        (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(manifest, indent=2), flush=True)
        return
    if not FMM.exists() or not UBODT.exists():
        raise SystemExit("FMM executables are missing; build public_release/third_party/fmm-v0.1.1 first")
    network, lengths, _ = build_network(out)
    gps = out / "raw_gps_points.csv"
    records, gps_stats = read_geolife(a.max_files, gps)
    ubodt = out / "ubodt.txt"
    run([str(UBODT), "--network", str(network), "--network_id", "id", "--source", "source", "--target", "target", "--delta", str(a.ubodt_delta_m), "--output", str(ubodt), "--use_omp"], out)
    matched = out / "fmm_matches.csv"
    command = [str(FMM), "--ubodt", str(ubodt), "--network", str(network), "--network_id", "id", "--source", "source", "--target", "target", "--gps", str(gps), "--gps_point", "--gps_id", "id", "--gps_x", "x", "--gps_y", "y", "--gps_timestamp", "timestamp", "--candidates", str(a.candidates), "--radius", str(a.radius_m), "--error", str(a.gps_error_m), "--output", str(matched), "--output_fields", "cpath,offset,error,spdist,mgeom", "--use_omp"]
    run(command, out)
    match_stats = parse_matches(matched, records, lengths, out, a.max_route_edges)
    manifest = {"method": "MTNet non-DP transfer preprocessing", "paper_constraints": {"FMM": True, "directed_public_OSM": True, "max_route_edges": a.max_route_edges, "time_interpolation": "linear by matched edge length", "split": "shuffled 80/20"}, "not_claimed": ["author-certified Beijing preprocessing", "paper-disclosed FMM hyperparameters", "DP guarantee", "MTR or any MTR component"], "fmm": {"source": "cyang-kth/fmm v0.1.1", "candidates": a.candidates, "radius_m": a.radius_m, "gps_error_m": a.gps_error_m, "ubodt_delta_m": a.ubodt_delta_m}, "gps": gps_stats, "network_edges": len(lengths), "match": match_stats}
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()

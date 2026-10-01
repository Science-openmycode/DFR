from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import (
    PUBLIC_ROOT,
    filter_osm_ways_by_bbox,
    jsonable,
    load_osm_ways,
    load_trajectories,
    write_json,
)


EARTH_KM = 6371.0088
TASKS = ["map_matching", "route_recovery", "route_similarity", "eta_readiness", "simulation"]


def log(message: str) -> None:
    print(f"[downstream] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Evaluate road-network downstream tasks on already-generated "
            "synthetic trajectory datasets. This script does not train or run "
            "a synthesizer."
        )
    )
    p.add_argument("--real", default="geolife", help="real reference trajectories")
    p.add_argument("--real-limit", type=int, default=None, help="public limit for loading the real reference corpus")
    p.add_argument("--synthetic", action="append", default=[], help="synthetic trajectory file; repeatable")
    p.add_argument("--synthetic-dir", default=None, help="directory containing .npz/.pkl/.pickle/.npy/.json releases")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--task", choices=[*TASKS, "all"], default="all")
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "downstream_tasks"))
    p.add_argument("--road-sample-step-km", type=float, default=0.08)
    p.add_argument("--signature-grid", type=int, default=32)
    return p


def latlon_to_xy(points: np.ndarray, lat0: float) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    x = np.deg2rad(pts[:, 1]) * EARTH_KM * math.cos(math.radians(lat0))
    y = np.deg2rad(pts[:, 0]) * EARTH_KM
    return np.column_stack([x, y])


def segment_lengths_km(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    if len(arr) < 2:
        return np.zeros(0, dtype=float)
    lat1 = np.deg2rad(arr[:-1, 0])
    lat2 = np.deg2rad(arr[1:, 0])
    dlat = lat2 - lat1
    dlon = np.deg2rad(arr[1:, 1] - arr[:-1, 1])
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def turn_angles(arr: np.ndarray) -> np.ndarray:
    if len(arr) < 3:
        return np.zeros(0, dtype=float)
    lat0 = float(np.mean(arr[:, 0]))
    xy = latlon_to_xy(arr, lat0)
    v1 = xy[1:-1] - xy[:-2]
    v2 = xy[2:] - xy[1:-1]
    n1 = np.linalg.norm(v1, axis=1)
    n2 = np.linalg.norm(v2, axis=1)
    ok = (n1 > 1e-9) & (n2 > 1e-9)
    if not np.any(ok):
        return np.zeros(0, dtype=float)
    cosang = np.sum(v1[ok] * v2[ok], axis=1) / (n1[ok] * n2[ok])
    return np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))


def sampled_points(arr: np.ndarray, max_points: int = 128) -> np.ndarray:
    if len(arr) <= max_points:
        return arr
    idx = np.linspace(0, len(arr) - 1, max_points).round().astype(int)
    return arr[idx]


def sample_osm_points(osm_ways: list[dict], lat0: float, step_km: float) -> np.ndarray:
    samples: list[tuple[float, float]] = []
    total = len(osm_ways)
    for i, way in enumerate(osm_ways, start=1):
        if i == 1 or i == total or i % 5000 == 0:
            log(f"sampling OSM road geometry {i:,}/{total:,}")
        geom = way.get("geometry", []) if isinstance(way, dict) else []
        coords = [(float(p["lat"]), float(p["lon"])) for p in geom if "lat" in p and "lon" in p]
        if len(coords) < 2:
            continue
        arr = np.asarray(coords, dtype=float)
        samples.extend(map(tuple, arr))
        xy = latlon_to_xy(arr, lat0)
        for i in range(len(arr) - 1):
            dist = float(np.linalg.norm(xy[i + 1] - xy[i]))
            n = max(0, int(dist / max(step_km, 1e-6)) - 1)
            for alpha in np.linspace(0.0, 1.0, n + 2)[1:-1]:
                p = arr[i] * (1.0 - alpha) + arr[i + 1] * alpha
                samples.append((float(p[0]), float(p[1])))
    if not samples:
        raise RuntimeError("OSM cache produced no road samples")
    return np.asarray(samples, dtype=float)


def full_bbox(trajs: list[np.ndarray], pad: float = 1e-6) -> tuple[float, float, float, float]:
    pts = np.vstack([np.asarray(t, dtype=float)[:, :2] for t in trajs if len(t) >= 2])
    return (
        float(np.min(pts[:, 0]) - pad),
        float(np.max(pts[:, 0]) + pad),
        float(np.min(pts[:, 1]) - pad),
        float(np.max(pts[:, 1]) + pad),
    )


def cell_signature(arr: np.ndarray, bbox: tuple[float, float, float, float], grid: int) -> set[tuple[int, int]]:
    lat_min, lat_max, lon_min, lon_max = bbox
    pts = sampled_points(arr, max_points=96)
    yi = np.floor((pts[:, 0] - lat_min) / max(lat_max - lat_min, 1e-12) * grid).astype(int)
    xi = np.floor((pts[:, 1] - lon_min) / max(lon_max - lon_min, 1e-12) * grid).astype(int)
    yi = np.clip(yi, 0, grid - 1)
    xi = np.clip(xi, 0, grid - 1)
    return set(zip(yi.tolist(), xi.tolist()))


def traj_quality(trajs: list[np.ndarray], road_tree: cKDTree, lat0: float) -> list[dict]:
    rows = []
    total_trajs = len(trajs)
    for idx, arr in enumerate(trajs):
        if idx == 0 or idx + 1 == total_trajs or (idx + 1) % 5000 == 0:
            log(f"computing trajectory quality {idx + 1:,}/{total_trajs:,}")
        arr = np.asarray(arr, dtype=float)
        seg = segment_lengths_km(arr)
        pts = sampled_points(arr)
        dists, _ = road_tree.query(latlon_to_xy(pts, lat0), k=1)
        path_total = float(seg.sum())
        direct = float(segment_lengths_km(arr[[0, -1]])[0]) if len(arr) >= 2 else 0.0
        angles = turn_angles(arr)
        rows.append(
            {
                "idx": idx,
                "n_points": int(len(arr)),
                "mean_step_km": float(seg.mean()) if len(seg) else 0.0,
                "max_step_km": float(seg.max()) if len(seg) else 0.0,
                "jump1_share": float(np.mean(seg > 1.0)) if len(seg) else 0.0,
                "jump2_share": float(np.mean(seg > 2.0)) if len(seg) else 0.0,
                "road100_share": float(np.mean(dists <= 0.10)) if len(dists) else 0.0,
                "road200_share": float(np.mean(dists <= 0.20)) if len(dists) else 0.0,
                "path_len_km": path_total,
                "direct_len_km": direct,
                "stretch": path_total / max(direct, 1e-6),
                "turn_mean_deg": float(np.mean(angles)) if len(angles) else 0.0,
                "turn_p90_deg": float(np.percentile(angles, 90)) if len(angles) else 0.0,
            }
        )
    return rows


def flags(rows: list[dict]) -> dict[str, np.ndarray]:
    return {
        "map_matching": np.asarray(
            [r["road200_share"] >= 0.95 and r["jump2_share"] <= 0.02 for r in rows], dtype=bool
        ),
        "strict_map_matching": np.asarray(
            [r["road100_share"] >= 0.90 and r["jump1_share"] <= 0.02 for r in rows], dtype=bool
        ),
        "route_recovery": np.asarray(
            [
                r["road200_share"] >= 0.95
                and r["jump2_share"] <= 0.02
                and r["n_points"] >= 8
                and 1.05 <= r["stretch"] <= 25.0
                for r in rows
            ],
            dtype=bool,
        ),
        "eta_readiness": np.asarray(
            [
                r["road200_share"] >= 0.95
                and r["jump1_share"] <= 0.02
                and r["path_len_km"] > 0.2
                and 1.0 <= r["stretch"] <= 35.0
                for r in rows
            ],
            dtype=bool,
        ),
        "simulation": np.asarray(
            [r["road200_share"] >= 0.95 and r["max_step_km"] <= 1.0 and r["n_points"] >= 4 for r in rows],
            dtype=bool,
        ),
    }


def summarize_admission(task: str, rows: list[dict], task_flags: np.ndarray) -> dict:
    accepted = [r for r, ok in zip(rows, task_flags) if ok]
    return {
        "task": task,
        "n_total": len(rows),
        "n_accepted": int(np.sum(task_flags)),
        "accept_rate": float(np.mean(task_flags)) if len(rows) else 0.0,
        "road200_mean": float(np.mean([r["road200_share"] for r in rows])) if rows else 0.0,
        "jump2_mean": float(np.mean([r["jump2_share"] for r in rows])) if rows else 0.0,
        "path_len_mean_accepted": float(np.mean([r["path_len_km"] for r in accepted])) if accepted else 0.0,
        "stretch_mean_accepted": float(np.mean([r["stretch"] for r in accepted])) if accepted else 0.0,
    }


def route_similarity_summary(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    real_rows: list[dict],
    syn_rows: list[dict],
    bbox: tuple[float, float, float, float],
    grid: int,
) -> dict:
    real_ok = flags(real_rows)["route_recovery"]
    syn_ok = flags(syn_rows)["route_recovery"]
    real_sigs = [cell_signature(t, bbox, grid) for t, ok in zip(real, real_ok) if ok]
    syn_sigs = [cell_signature(t, bbox, grid) for t, ok in zip(syn, syn_ok) if ok]
    if not real_sigs or not syn_sigs:
        return {
            "task": "route_similarity",
            "real_route_ready": int(len(real_sigs)),
            "synthetic_route_ready": int(len(syn_sigs)),
            "query_coverage": 0.0,
            "mean_best_jaccard": 0.0,
            "note": "No route-ready query or index trajectories.",
        }
    syn_union = set().union(*syn_sigs)
    best = []
    covered = 0
    for sig in real_sigs:
        if sig and len(sig & syn_union) / len(sig) >= 0.50:
            covered += 1
        sample = syn_sigs if len(syn_sigs) <= 2000 else syn_sigs[:: max(1, len(syn_sigs) // 2000)]
        vals = [len(sig & s) / max(len(sig | s), 1) for s in sample]
        best.append(max(vals) if vals else 0.0)
    return {
        "task": "route_similarity",
        "real_route_ready": int(len(real_sigs)),
        "synthetic_route_ready": int(len(syn_sigs)),
        "query_coverage": float(covered / len(real_sigs)),
        "mean_best_jaccard": float(np.mean(best)),
        "signature_grid": int(grid),
    }


def discover_synthetic(args: argparse.Namespace) -> list[Path]:
    paths = [Path(p) for p in args.synthetic]
    if args.synthetic_dir:
        root = Path(args.synthetic_dir)
        if not root.is_absolute():
            root = Path.cwd() / root
        for suffix in ["*.npz", "*.pkl", "*.pickle", "*.npy"]:
            paths.extend(sorted(root.glob(suffix)))
    seen = set()
    by_stem: dict[str, Path] = {}
    priority = {".npz": 0, ".pkl": 1, ".pickle": 1, ".npy": 2}
    for path in paths:
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and str(path) not in seen:
            key = str(path.with_suffix(""))
            prev = by_stem.get(key)
            if prev is None or priority.get(path.suffix.lower(), 9) < priority.get(prev.suffix.lower(), 9):
                by_stem[key] = path
            seen.add(str(path))
    uniq = sorted(by_stem.values())
    if not uniq:
        raise RuntimeError("provide --synthetic and/or --synthetic-dir")
    return uniq


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: jsonable(v) for k, v in row.items()} for row in rows])


def main() -> None:
    args = build_parser().parse_args()
    t0 = time.time()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    limit_note = "full corpus" if args.real_limit is None else f"first {args.real_limit:,} public-protocol trajectories"
    log(f"loading real trajectories from {args.real} ({limit_note})")
    real = load_trajectories(args.real, limit=args.real_limit)
    if not real:
        raise RuntimeError("no real trajectories loaded")
    log(f"loaded {len(real):,} real trajectories")
    log("computing full-real bbox and latitude origin")
    lat0 = float(np.mean(np.vstack([t[[0, -1]] for t in real if len(t) >= 2])[:, 0]))
    bbox = full_bbox(real)
    log(f"loading OSM cache from {args.osm_cache}")
    osm_ways_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
    log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")
    road_samples = sample_osm_points(osm_ways, lat0, args.road_sample_step_km)
    log(f"building road KDTree from {len(road_samples):,} sampled road points")
    road_tree = cKDTree(latlon_to_xy(road_samples, lat0))
    log("precomputing real trajectory quality rows")
    real_rows = traj_quality(real, road_tree, lat0)
    real_flags = flags(real_rows)
    real_summary = {
        "map_matching": summarize_admission("map_matching", real_rows, real_flags["map_matching"]),
        "strict_map_matching": summarize_admission("strict_map_matching", real_rows, real_flags["strict_map_matching"]),
        "route_recovery": summarize_admission("route_recovery", real_rows, real_flags["route_recovery"]),
        "eta_readiness": summarize_admission("eta_readiness", real_rows, real_flags["eta_readiness"]),
        "simulation": summarize_admission("simulation", real_rows, real_flags["simulation"]),
    }

    selected_tasks = TASKS if args.task == "all" else [args.task]
    task_rows: dict[str, list[dict]] = {task: [] for task in selected_tasks}
    all_rows: list[dict] = []

    syn_files = discover_synthetic(args)
    log(f"found {len(syn_files):,} synthetic release file(s)")
    for i, syn_path in enumerate(syn_files, start=1):
        log(f"[{i}/{len(syn_files)}] loading {syn_path.name}")
        syn = load_trajectories(str(syn_path), limit=None)
        log(f"[{i}/{len(syn_files)}] computing trajectory quality for {syn_path.stem} ({len(syn):,} trajectories)")
        syn_rows = traj_quality(syn, road_tree, lat0)
        syn_flags = flags(syn_rows)
        method = syn_path.stem
        for task in selected_tasks:
            log(f"[{i}/{len(syn_files)}] evaluating task {task} for {method}")
            if task == "map_matching":
                row = summarize_admission(task, syn_rows, syn_flags["map_matching"])
                row["strict_accept_rate"] = float(np.mean(syn_flags["strict_map_matching"])) if syn_rows else 0.0
                row["real_accept_rate"] = float(np.mean(real_flags["map_matching"]))
            elif task == "route_recovery":
                row = summarize_admission(task, syn_rows, syn_flags["route_recovery"])
                row["real_accept_rate"] = float(np.mean(real_flags["route_recovery"]))
            elif task == "simulation":
                row = summarize_admission(task, syn_rows, syn_flags["simulation"])
                row["real_accept_rate"] = float(np.mean(real_flags["simulation"]))
            elif task == "eta_readiness":
                row = summarize_admission(task, syn_rows, syn_flags["eta_readiness"])
                row["real_accept_rate"] = float(np.mean(real_flags["eta_readiness"]))
            elif task == "route_similarity":
                row = route_similarity_summary(real, syn, real_rows, syn_rows, bbox, args.signature_grid)
            else:
                raise AssertionError(task)
            row["method"] = method
            row["synthetic_file"] = str(syn_path.resolve())
            task_rows[task].append(row)
            all_rows.append(row)

    manifest = {
        "command_role": "evaluate_downstream",
        "real": args.real,
        "real_limit": args.real_limit,
        "real_count": len(real),
        "osm_cache": args.osm_cache,
        "road_sample_count": int(len(road_samples)),
        "tasks": selected_tasks,
        "real_summary": real_summary,
        "task_definition_note": (
            "Tasks are evaluated independently on an already-generated synthetic release. "
            "This is a downstream usability benchmark, not a synthesizer training script."
        ),
        "outputs": {},
    }
    for task, rows in task_rows.items():
        json_path = out_dir / f"{task}.json"
        csv_path = out_dir / f"{task}.csv"
        write_json(json_path, {"task": task, "rows": rows})
        write_csv(csv_path, rows)
        manifest["outputs"][task] = {"json": str(json_path.resolve()), "csv": str(csv_path.resolve())}
    summary_path = out_dir / "downstream_manifest.json"
    write_json(summary_path, manifest)
    log(f"completed in {time.time() - t0:.1f}s")
    print(f"wrote {summary_path}")
    for task, outputs in manifest["outputs"].items():
        print(f"wrote {task}: {outputs['json']}")


if __name__ == "__main__":
    main()

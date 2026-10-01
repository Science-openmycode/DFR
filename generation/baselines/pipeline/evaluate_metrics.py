from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.distance import jensenshannon

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import PUBLIC_ROOT, filter_osm_ways_by_bbox, jsonable, load_osm_ways, load_trajectories, write_json


EARTH_KM = 6371.0088


def log(message: str) -> None:
    print(f"[metrics] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Evaluate full-release trajectory utility metrics on already-generated "
            "synthetic datasets. This script does not run any synthesizer."
        )
    )
    p.add_argument("--real", default="geolife", help="real reference trajectories")
    p.add_argument("--real-limit", type=int, default=None, help="public limit for loading the real reference corpus")
    p.add_argument("--synthetic", action="append", default=[], help="synthetic trajectory file; repeatable")
    p.add_argument("--synthetic-dir", default=None, help="directory containing synthetic releases")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "metrics_full"))
    p.add_argument("--grid", type=int, default=64)
    p.add_argument("--road-sample-step-km", type=float, default=0.08)
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


def full_bbox(trajs: list[np.ndarray], pad_ratio: float = 0.02) -> tuple[float, float, float, float]:
    pts = np.vstack([np.asarray(t, dtype=float)[:, :2] for t in trajs if len(t) >= 2])
    mn = pts.min(axis=0)
    mx = pts.max(axis=0)
    span = np.maximum(mx - mn, 1e-9)
    return (
        float(mn[0] - pad_ratio * span[0]),
        float(mx[0] + pad_ratio * span[0]),
        float(mn[1] - pad_ratio * span[1]),
        float(mx[1] + pad_ratio * span[1]),
    )


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


def sampled_points(arr: np.ndarray, max_points: int = 128) -> np.ndarray:
    if len(arr) <= max_points:
        return arr
    idx = np.linspace(0, len(arr) - 1, max_points).round().astype(int)
    return arr[idx]


def hist_prob(values: np.ndarray, bins: np.ndarray) -> np.ndarray:
    h, _ = np.histogram(values, bins=bins)
    p = h.astype(float) + 1e-12
    return p / p.sum()


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    return float(jensenshannon(p, q, base=2.0) ** 2)


def cell_ids(points: np.ndarray, bbox: tuple[float, float, float, float], grid: int) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = bbox
    yi = np.floor((points[:, 0] - lat_min) / max(lat_max - lat_min, 1e-12) * grid).astype(int)
    xi = np.floor((points[:, 1] - lon_min) / max(lon_max - lon_min, 1e-12) * grid).astype(int)
    yi = np.clip(yi, 0, grid - 1)
    xi = np.clip(xi, 0, grid - 1)
    return yi * grid + xi


def occupancy_prob(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int) -> np.ndarray:
    h = np.zeros(grid * grid, dtype=float)
    for tr in trajs:
        pts = sampled_points(np.asarray(tr, dtype=float), 128)
        ids = cell_ids(pts, bbox, grid)
        for idx in np.unique(ids):
            h[int(idx)] += 1.0
    h += 1e-12
    return h / h.sum()


def od_prob(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int) -> np.ndarray:
    h = np.zeros(grid * grid * grid * grid, dtype=float)
    for tr in trajs:
        arr = np.asarray(tr, dtype=float)
        if len(arr) < 2:
            continue
        a = int(cell_ids(arr[[0]], bbox, grid)[0])
        b = int(cell_ids(arr[[-1]], bbox, grid)[0])
        h[a * grid * grid + b] += 1.0
    h += 1e-12
    return h / h.sum()


def road_metrics(trajs: list[np.ndarray], road_tree: cKDTree, lat0: float) -> dict:
    dists = []
    segs = []
    lengths = []
    point_counts = []
    for tr in trajs:
        arr = np.asarray(tr, dtype=float)
        if len(arr) < 2:
            continue
        seg = segment_lengths_km(arr)
        pts = sampled_points(arr)
        dist, _ = road_tree.query(latlon_to_xy(pts, lat0), k=1)
        dists.extend(dist.tolist())
        segs.extend(seg.tolist())
        lengths.append(float(seg.sum()))
        point_counts.append(len(arr))
    d = np.asarray(dists, dtype=float)
    s = np.asarray(segs, dtype=float)
    return {
        "n_traj": len(trajs),
        "mean_points": float(np.mean(point_counts)) if point_counts else 0.0,
        "road_100m": float(np.mean(d <= 0.10)) if len(d) else 0.0,
        "road_200m": float(np.mean(d <= 0.20)) if len(d) else 0.0,
        "road_mean_dist_km": float(np.mean(d)) if len(d) else 0.0,
        "jump_gt1km": float(np.mean(s > 1.0)) if len(s) else 0.0,
        "jump_gt2km": float(np.mean(s > 2.0)) if len(s) else 0.0,
        "step_mean_km": float(np.mean(s)) if len(s) else 0.0,
        "step_p95_km": float(np.percentile(s, 95)) if len(s) else 0.0,
        "length_mean_km": float(np.mean(lengths)) if lengths else 0.0,
    }


def distribution_metrics(real: list[np.ndarray], syn: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int) -> dict:
    real_lengths = np.asarray([segment_lengths_km(t).sum() for t in real if len(t) >= 2], dtype=float)
    syn_lengths = np.asarray([segment_lengths_km(t).sum() for t in syn if len(t) >= 2], dtype=float)
    real_steps = np.concatenate([segment_lengths_km(t) for t in real if len(t) >= 2])
    syn_steps = np.concatenate([segment_lengths_km(t) for t in syn if len(t) >= 2])
    max_len = max(float(np.percentile(real_lengths, 99)), float(np.percentile(syn_lengths, 99)), 1e-6)
    max_step = max(float(np.percentile(real_steps, 99)), float(np.percentile(syn_steps, 99)), 1e-6)
    return {
        "grid_occupancy_jsd": jsd(occupancy_prob(real, bbox, grid), occupancy_prob(syn, bbox, grid)),
        "od_jsd": jsd(od_prob(real, bbox, min(grid, 24)), od_prob(syn, bbox, min(grid, 24))),
        "length_jsd": jsd(hist_prob(real_lengths, np.linspace(0, max_len, 33)), hist_prob(syn_lengths, np.linspace(0, max_len, 33))),
        "step_jsd": jsd(hist_prob(real_steps, np.linspace(0, max_step, 33)), hist_prob(syn_steps, np.linspace(0, max_step, 33))),
    }


def discover_synthetic(paths: list[str], synthetic_dir: str | None) -> list[Path]:
    found = [Path(p) for p in paths]
    if synthetic_dir:
        root = Path(synthetic_dir)
        if not root.is_absolute():
            root = Path.cwd() / root
        for suffix in ["*.npz", "*.pkl", "*.pickle", "*.npy"]:
            found.extend(sorted(root.glob(suffix)))
    out = []
    seen = set()
    by_stem: dict[str, Path] = {}
    priority = {".npz": 0, ".pkl": 1, ".pickle": 1, ".npy": 2}
    for path in found:
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and str(path) not in seen:
            key = str(path.with_suffix(""))
            prev = by_stem.get(key)
            if prev is None or priority.get(path.suffix.lower(), 9) < priority.get(prev.suffix.lower(), 9):
                by_stem[key] = path
            seen.add(str(path))
    out = sorted(by_stem.values())
    if not out:
        raise RuntimeError("provide existing --synthetic and/or --synthetic-dir")
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({k for row in rows for k in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
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
    log(f"loaded {len(real):,} real trajectories")
    log("computing full-real bbox and latitude origin")
    bbox = full_bbox(real)
    lat0 = float(np.mean(np.vstack([t[[0, -1]] for t in real if len(t) >= 2])[:, 0]))
    log(f"loading OSM cache from {args.osm_cache}")
    osm_ways_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
    log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")
    road_samples = sample_osm_points(osm_ways, lat0, args.road_sample_step_km)
    log(f"building road KDTree from {len(road_samples):,} sampled road points")
    road_tree = cKDTree(latlon_to_xy(road_samples, lat0))

    rows = []
    syn_files = discover_synthetic(args.synthetic, args.synthetic_dir)
    log(f"found {len(syn_files):,} synthetic release file(s)")
    for i, syn_path in enumerate(syn_files, start=1):
        log(f"[{i}/{len(syn_files)}] loading {syn_path.name}")
        syn = load_trajectories(str(syn_path), limit=None)
        log(f"[{i}/{len(syn_files)}] evaluating {syn_path.stem} ({len(syn):,} trajectories)")
        row = {
            "method": syn_path.stem,
            "synthetic_file": str(syn_path.resolve()),
            "real": args.real,
            "real_count": len(real),
        }
        row.update(road_metrics(syn, road_tree, lat0))
        row.update(distribution_metrics(real, syn, bbox, args.grid))
        rows.append(row)
        log(f"[{i}/{len(syn_files)}] {syn_path.stem}: n={row['n_traj']} road200={row['road_200m']:.3f} jump2={row['jump_gt2km']:.3f}")

    payload = {
        "command_role": "evaluate_metrics",
        "real": args.real,
        "real_limit": args.real_limit,
        "real_count": len(real),
        "osm_cache": args.osm_cache,
        "grid": int(args.grid),
        "road_sample_count": int(len(road_samples)),
        "rows": rows,
    }
    write_json(out_dir / "metrics_full.json", payload)
    write_csv(out_dir / "metrics_full.csv", rows)
    log(f"completed in {time.time() - t0:.1f}s")
    print(f"wrote {out_dir / 'metrics_full.json'}")
    print(f"wrote {out_dir / 'metrics_full.csv'}")


if __name__ == "__main__":
    main()

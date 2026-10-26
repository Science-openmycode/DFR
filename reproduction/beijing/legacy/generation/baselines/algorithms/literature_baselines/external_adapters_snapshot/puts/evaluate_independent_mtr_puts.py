"""Evaluate independently generated MTR and original PUTS releases.

This is deliberately not the earlier graph-matched adapter diagnostic.  PUTS
keeps its native road representation and MTR keeps its full public-OSM
decoder; the methods share only the raw training subset, release size, public
Beijing bounding box, and coordinate-space evaluation protocol.
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PUBLIC_RELEASE = Path(__file__).resolve().parents[2]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import filter_osm_ways_by_bbox, load_osm_ways


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        return [np.asarray(x, dtype=float) for x in pickle.load(handle) if len(x) >= 2]


def haversine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    lat1, lon1 = np.radians(a[..., 0]), np.radians(a[..., 1])
    lat2, lon2 = np.radians(b[..., 0]), np.radians(b[..., 1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6_371_000.0 * 2.0 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def jsd(a: np.ndarray, b: np.ndarray) -> float:
    p, q = np.asarray(a, float) + 1e-12, np.asarray(b, float) + 1e-12
    p, q = p / p.sum(), q / q.sum()
    mid = 0.5 * (p + q)
    return float(0.5 * ((p * np.log(p / mid)).sum() + (q * np.log(q / mid)).sum()))


def lengths(data: list[np.ndarray]) -> np.ndarray:
    return np.asarray([haversine(t[:-1], t[1:]).sum() for t in data], dtype=float)


def metric_row(real: list[np.ndarray], syn: list[np.ndarray], roads: cKDTree, bbox: tuple[float, float, float, float]) -> dict[str, float]:
    lo = np.asarray([bbox[0], bbox[2]], float)
    span = np.asarray([bbox[1] - bbox[0], bbox[3] - bbox[2]], float)
    def grid(data: list[np.ndarray], size: int = 32) -> np.ndarray:
        hist = np.zeros((size, size), float)
        for t in data:
            cell = np.clip(((t - lo) / span * size).astype(int), 0, size - 1)
            np.add.at(hist, (cell[:, 0], cell[:, 1]), 1)
        return hist.ravel()
    def od(data: list[np.ndarray], size: int = 4) -> np.ndarray:
        hist = np.zeros((size * size, size * size), float)
        for t in data:
            a = np.clip(((t[0] - lo) / span * size).astype(int), 0, size - 1)
            b = np.clip(((t[-1] - lo) / span * size).astype(int), 0, size - 1)
            hist[a[0] * size + a[1], b[0] * size + b[1]] += 1
        return hist.ravel()
    rlen, slen = lengths(real), lengths(syn)
    len_edges = np.linspace(0, max(float(np.quantile(np.r_[rlen, slen], .99)), 1.0), 31)
    rstep = np.concatenate([haversine(t[:-1], t[1:]) for t in real])
    sstep = np.concatenate([haversine(t[:-1], t[1:]) for t in syn])
    step_edges = np.linspace(0, max(float(np.quantile(np.r_[rstep, sstep], .99)), 1.0), 31)
    pts = np.vstack(syn)
    dist_m = roads.query(pts)[0] * 111_000.0
    return {
        "n_release": len(syn),
        "grid_jsd": jsd(grid(real), grid(syn)),
        "od_jsd": jsd(od(real), od(syn)),
        "length_jsd": jsd(np.histogram(rlen, len_edges)[0], np.histogram(slen, len_edges)[0]),
        "step_jsd": jsd(np.histogram(rstep, step_edges)[0], np.histogram(sstep, step_edges)[0]),
        "jump_gt_100m": float(np.mean(sstep > 100.0)),
        "jump_gt_200m": float(np.mean(sstep > 200.0)),
        "road_within_100m": float(np.mean(dist_m <= 100.0)),
        "road_within_200m": float(np.mean(dist_m <= 200.0)),
        "road_mean_m": float(np.mean(dist_m)),
        "mean_length_m": float(slen.mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Common coordinate-space evaluation for independent MTR and PUTS releases")
    ap.add_argument("--real", type=Path, required=True)
    ap.add_argument("--mtr", type=Path, required=True)
    ap.add_argument("--puts", type=Path, required=True)
    ap.add_argument("--osm-cache", type=Path, required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    bbox = tuple(args.bbox)
    print("[1/3] Loading independent releases and the common public OSM evaluator...", flush=True)
    real, mtr, puts = load(args.real), load(args.mtr), load(args.puts)
    ways = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox)
    road_pts = np.vstack([[[p["lat"], p["lon"]] for p in way.get("geometry", [])] for way in ways if len(way.get("geometry", [])) >= 2])
    tree = cKDTree(road_pts)
    print(f"[2/3] Evaluating {len(mtr):,} MTR and {len(puts):,} PUTS trajectories against {len(road_pts):,} public OSM points...", flush=True)
    rows = []
    for name, corpus in [("MTR-DP-GSRT (full public OSM)", mtr), ("Original PUTS (native road representation)", puts)]:
        row = {"method": name, **metric_row(real, corpus, tree, bbox)}
        rows.append(row)
        print(name, {k: round(v, 4) if isinstance(v, float) else v for k, v in row.items() if k != "method"}, flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f"[3/3] Wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()

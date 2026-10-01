"""Evaluate the graph-matched PUTS reduced-road diagnostic.

All three corpora are compared against the same 3,000 PUTS road geometries.
This avoids importing full-city OSM into a diagnostic whose public graph is
PUTS's restricted native segment graph.
"""
from __future__ import annotations

import argparse
import csv
import pickle
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from run_mtr_dp_gsrt_on_puts_native_graph import read_lines, read_selected_lines


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        return [np.asarray(x, dtype=float) for x in pickle.load(handle) if len(x) >= 2]


def haversine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    lat1, lon1 = np.radians(a[..., 0]), np.radians(a[..., 1])
    lat2, lon2 = np.radians(b[..., 0]), np.radians(b[..., 1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371000.0 * 2.0 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def length_meters(traj: np.ndarray) -> float:
    return float(haversine(traj[:-1], traj[1:]).sum())


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    p = p.astype(float) + 1e-12; q = q.astype(float) + 1e-12
    p /= p.sum(); q /= q.sum(); m = .5 * (p + q)
    return float(.5 * ((p * np.log(p / m)).sum() + (q * np.log(q / m)).sum()))


def histogram(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.histogram(values, bins=edges)[0].astype(float)


def corpus_metrics(real: list[np.ndarray], synthetic: list[np.ndarray], road_tree: cKDTree) -> dict[str, float]:
    all_points = np.vstack(real)
    lo, hi = all_points.min(0), all_points.max(0)
    span = np.maximum(hi - lo, 1e-12)
    def grid(corpus: list[np.ndarray]) -> np.ndarray:
        counts = np.zeros((32, 32), dtype=float)
        for traj in corpus:
            cell = np.clip(((traj - lo) / span * 32).astype(int), 0, 31)
            np.add.at(counts, (cell[:, 0], cell[:, 1]), 1)
        return counts.ravel()
    def od(corpus: list[np.ndarray]) -> np.ndarray:
        counts = np.zeros((16, 16), dtype=float)
        for traj in corpus:
            a = np.clip(((traj[0] - lo) / span * 4).astype(int), 0, 3)
            b = np.clip(((traj[-1] - lo) / span * 4).astype(int), 0, 3)
            counts[a[0] * 4 + a[1], b[0] * 4 + b[1]] += 1
        return counts.ravel()
    real_len = np.asarray([length_meters(x) for x in real])
    syn_len = np.asarray([length_meters(x) for x in synthetic])
    upper = max(float(np.quantile(np.r_[real_len, syn_len], .99)), 1.0)
    edges = np.linspace(0, upper, 31)
    step = np.r_[*[haversine(x[:-1], x[1:]) for x in real]]
    syn_step = np.r_[*[haversine(x[:-1], x[1:]) for x in synthetic]]
    step_upper = max(float(np.quantile(np.r_[step, syn_step], .99)), 1.0)
    step_edges = np.linspace(0, step_upper, 31)
    points = np.vstack(synthetic)
    # KD-tree is in degrees; convert locally using a conservative latitude scale.
    distances_deg, _ = road_tree.query(points)
    distances_m = distances_deg * 111000.0
    jumps = np.r_[*[haversine(x[:-1], x[1:]) for x in synthetic]]
    return {
        "n": len(synthetic),
        "grid_jsd": jsd(grid(real), grid(synthetic)),
        "od_jsd": jsd(od(real), od(synthetic)),
        "length_jsd": jsd(histogram(real_len, edges), histogram(syn_len, edges)),
        "step_jsd": jsd(histogram(step, step_edges), histogram(syn_step, step_edges)),
        "jump_gt_100m": float(np.mean(jumps > 100.0)),
        "jump_gt_200m": float(np.mean(jumps > 200.0)),
        "road_within_100m": float(np.mean(distances_m <= 100.0)),
        "road_within_200m": float(np.mean(distances_m <= 200.0)),
        "road_mean_m": float(np.mean(distances_m)),
        "mean_length_m": float(syn_len.mean()),
        "mean_points": float(np.mean([len(x) for x in synthetic])),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--geometry", type=Path, required=True)
    p.add_argument("--real", type=Path, required=True)
    p.add_argument("--mtr", type=Path, required=True)
    p.add_argument("--puts", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n-roads", type=int, default=3000)
    p.add_argument("--road-ids", type=Path, default=None)
    a = p.parse_args()
    print("[1/3] Loading native graph road geometry...", flush=True)
    roads = (read_selected_lines(a.geometry, [int(x) for x in a.road_ids.read_text().splitlines() if x.strip()])
             if a.road_ids else read_lines(a.geometry, a.n_roads))
    # Densify only by existing stored vertices: same public road representation.
    tree = cKDTree(np.vstack(roads))
    print("[2/3] Loading real, MTR-native, and PUTS releases...", flush=True)
    real, mtr, puts = load(a.real), load(a.mtr), load(a.puts)
    print("[3/3] Computing common reduced-graph utility metrics...", flush=True)
    rows = []
    for name, corpus in [("MTR-DP-GSRT native graph", mtr), ("PUTS reduced-road adaptation", puts)]:
        row = {"method": name, **corpus_metrics(real, corpus, tree)}
        rows.append(row)
        print(name, {k: round(v, 4) if isinstance(v, float) else v for k, v in row.items() if k != "method"}, flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {a.out}", flush=True)


if __name__ == "__main__":
    main()

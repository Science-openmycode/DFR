"""Evaluate the two-stratum 3,000-parent Beijing appendix protocol.

This evaluator deliberately keeps MTR/DPMM population-release measurements
separate from PUTS's FMM-eligible branch. It never truncates a release merely
to make a table look count-matched.
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
sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import filter_osm_ways_by_bbox, load_osm_ways  # noqa: E402


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        return [np.asarray(x, dtype=float) for x in pickle.load(handle) if len(x) >= 2]


def haversine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    lat1, lon1 = np.radians(a[..., 0]), np.radians(a[..., 1])
    lat2, lon2 = np.radians(b[..., 0]), np.radians(b[..., 1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6_371_000.0 * 2 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def jsd(a: np.ndarray, b: np.ndarray) -> float:
    p, q = np.asarray(a, float) + 1e-12, np.asarray(b, float) + 1e-12
    p, q = p / p.sum(), q / q.sum()
    m = 0.5 * (p + q)
    return float(0.5 * ((p * np.log(p / m)).sum() + (q * np.log(q / m)).sum()))


def metrics(real: list[np.ndarray], release: list[np.ndarray], tree: cKDTree, bbox: tuple[float, ...]) -> dict[str, float]:
    lo = np.asarray([bbox[0], bbox[2]]); span = np.asarray([bbox[1] - bbox[0], bbox[3] - bbox[2]])
    def density(data: list[np.ndarray]) -> np.ndarray:
        h = np.zeros((32, 32), dtype=float)
        for t in data:
            c = np.clip(((t - lo) / span * 32).astype(int), 0, 31)
            np.add.at(h, (c[:, 0], c[:, 1]), 1)
        return h.ravel()
    def length(data: list[np.ndarray]) -> np.ndarray:
        return np.asarray([haversine(t[:-1], t[1:]).sum() for t in data])
    rl, sl = length(real), length(release)
    bins = np.linspace(0, max(float(np.quantile(np.r_[rl, sl], .99)), 1), 31)
    steps = np.concatenate([haversine(t[:-1], t[1:]) for t in release])
    d = tree.query(np.vstack(release))[0] * 111_000.0
    return {"n_real": len(real), "n_release": len(release), "grid_density_jsd": jsd(density(real), density(release)),
            "path_length_jsd": jsd(np.histogram(rl, bins)[0], np.histogram(sl, bins)[0]),
            "trip_error_ratio": float(abs(sl.mean() - rl.mean()) / max(rl.mean(), 1.0)),
            "long_jump_gt_200m": float(np.mean(steps > 200.0)), "road_within_100m": float(np.mean(d <= 100.0)),
            "road_mean_m": float(np.mean(d)), "mean_length_m": float(sl.mean())}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent-real", type=Path, required=True)
    p.add_argument("--mtr", type=Path, required=True)
    p.add_argument("--dpmm", type=Path, required=True)
    p.add_argument("--puts-real", type=Path, required=True)
    p.add_argument("--puts", type=Path, required=True)
    p.add_argument("--osm-cache", type=Path, required=True)
    p.add_argument("--bbox", nargs=4, type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(); bbox = tuple(a.bbox)
    roads = filter_osm_ways_by_bbox(load_osm_ways(a.osm_cache), bbox)
    points = np.vstack([[[x["lat"], x["lon"]] for x in way["geometry"]] for way in roads if len(way.get("geometry", [])) >= 2])
    tree = cKDTree(points)
    parent, mtr, dpmm, puts_real, puts = (load(x) for x in (a.parent_real, a.mtr, a.dpmm, a.puts_real, a.puts))
    rows = []
    for stratum, reference, name, release, interface in [
        ("parent_3000", parent, "MTR / DP-GSRT", mtr, "central-DP population release"),
        ("parent_3000", parent, "DPMM (official)", dpmm, "per-input DP map matching"),
        ("puts_eligible", puts_real, "PUTS (upstream)", puts, "FMM-eligible road-sequence synthesis"),
    ]:
        row = {"stratum": stratum, "method": name, "interface": interface, **metrics(reference, release, tree, bbox)}
        rows.append(row); print(row, flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    main()

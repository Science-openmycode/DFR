"""Describe aggregate differences between two complete adjacent DP releases.

This is deliberately *not* an empirical DP proof or an epsilon estimator.  One
pair of independent releases cannot support a probability-ratio estimate.  The
script therefore compares only release-level, public observer statistics and
records that limitation beside every result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def route_lengths_km(routes: list[np.ndarray]) -> np.ndarray:
    result = []
    for route in routes:
        points = np.asarray(route, dtype=float)
        if len(points) < 2:
            result.append(0.0)
            continue
        latitude = np.deg2rad(points[:, 0])
        longitude = np.deg2rad(points[:, 1])
        dlat, dlon = np.diff(latitude), np.diff(longitude)
        a = np.sin(dlat / 2) ** 2 + np.cos(latitude[:-1]) * np.cos(latitude[1:]) * np.sin(dlon / 2) ** 2
        result.append(float(np.sum(6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))))
    return np.asarray(result)


def normalized_histogram(points: np.ndarray, bbox: tuple[float, float, float, float], bins: int) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = bbox
    hist, _, _ = np.histogram2d(points[:, 0], points[:, 1], bins=bins, range=((lat_min, lat_max), (lon_min, lon_max)))
    return hist.ravel() / max(float(hist.sum()), 1.0)


def tv(left: np.ndarray, right: np.ndarray) -> float:
    return float(0.5 * np.abs(left - right).sum())


def jsd(left: np.ndarray, right: np.ndarray) -> float:
    midpoint = (left + right) / 2
    def kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = a > 0
        return float(np.sum(a[mask] * np.log2(a[mask] / np.clip(b[mask], 1e-15, None))))
    return 0.5 * kl(left, midpoint) + 0.5 * kl(right, midpoint)


def summary(routes: list[np.ndarray]) -> dict[str, object]:
    lengths = route_lengths_km(routes)
    start = np.asarray([np.asarray(route)[0] for route in routes if len(route)], dtype=float)
    end = np.asarray([np.asarray(route)[-1] for route in routes if len(route)], dtype=float)
    all_points = np.vstack([np.asarray(route, dtype=float) for route in routes if len(route)])
    return {"count": len(routes), "points": int(len(all_points)), "lengths": lengths, "start": start, "end": end, "points_array": all_points}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--neighbor-release", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--bins", type=int, default=24)
    args = parser.parse_args()
    left = summary(pickle.loads(args.release.read_bytes()))
    right = summary(pickle.loads(args.neighbor_release.read_bytes()))
    both = np.vstack([left["points_array"], right["points_array"]])
    bbox = (float(both[:, 0].min()), float(both[:, 0].max()), float(both[:, 1].min()), float(both[:, 1].max()))
    def compare(name: str, a: np.ndarray, b: np.ndarray) -> dict[str, float]:
        return {"tv": tv(a, b), "jsd_bits": jsd(a, b)}
    length_edges = np.linspace(0, max(float(left["lengths"].max()), float(right["lengths"].max()), 1.0), args.bins + 1)
    lhist = np.histogram(left["lengths"], bins=length_edges)[0].astype(float); lhist /= max(lhist.sum(), 1)
    rhist = np.histogram(right["lengths"], bins=length_edges)[0].astype(float); rhist /= max(rhist.sum(), 1)
    payload = {
        "purpose": "descriptive adjacent-release canary comparison",
        "critical_limit": "One independently randomized adjacent pair cannot estimate an output probability ratio or validate epsilon. The certified DP guarantee remains the formal ledgered proof; these values are release-level diagnostics only.",
        "release": {"path": str(args.release.resolve()), "sha256": digest(args.release)},
        "neighbor_release": {"path": str(args.neighbor_release.resolve()), "sha256": digest(args.neighbor_release)},
        "grid_bins": args.bins,
        "bbox": {"lat_min": bbox[0], "lat_max": bbox[1], "lon_min": bbox[2], "lon_max": bbox[3]},
        "left": {"routes": left["count"], "points": left["points"], "length_mean_km": float(np.mean(left["lengths"])), "length_median_km": float(np.median(left["lengths"]))},
        "right": {"routes": right["count"], "points": right["points"], "length_mean_km": float(np.mean(right["lengths"])), "length_median_km": float(np.median(right["lengths"]))},
        "absolute_differences": {"length_mean_km": float(abs(np.mean(left["lengths"]) - np.mean(right["lengths"]))), "length_median_km": float(abs(np.median(left["lengths"]) - np.median(right["lengths"])))},
        "distribution_differences": {
            "start_grid": compare("start", normalized_histogram(left["start"], bbox, args.bins), normalized_histogram(right["start"], bbox, args.bins)),
            "end_grid": compare("end", normalized_histogram(left["end"], bbox, args.bins), normalized_histogram(right["end"], bbox, args.bins)),
            "point_occupancy_grid": compare("points", normalized_histogram(left["points_array"], bbox, args.bins), normalized_histogram(right["points_array"], bbox, args.bins)),
            "road_length": compare("length", lhist, rhist),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

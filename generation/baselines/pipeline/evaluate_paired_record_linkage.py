"""Evaluate paired trajectory record linkage with a fixed public landmark map.

This script is intended for releases that explicitly preserve one output record
per input record (for example DPMM).  It is not appropriate for a population
synthesizer such as MTR, where no record-level correspondence is released.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def fixed_landmarks(frame: pd.DataFrame, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Return IDs and linearly indexed latitude/longitude landmarks."""
    trajectories: list[tuple[int, np.ndarray]] = []
    for trajectory_id, group in frame.groupby("trajectory_id", sort=True):
        points = group[["latitude", "longitude"]].to_numpy(dtype=float)
        if len(points) == 0:
            continue
        positions = np.linspace(0.0, len(points) - 1, count)
        lower = np.floor(positions).astype(int)
        upper = np.ceil(positions).astype(int)
        weight = (positions - lower)[:, None]
        landmarks = points[lower] * (1.0 - weight) + points[upper] * weight
        trajectories.append((int(trajectory_id), landmarks))
    ids = np.asarray([item[0] for item in trajectories], dtype=int)
    values = np.stack([item[1] for item in trajectories])
    return ids, values


def mean_haversine_matrix(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """All-pairs mean landmark distance in metres, chunked over queries."""
    radius_m = 6_371_008.8
    q_lat = np.radians(query[:, None, :, 0])
    q_lon = np.radians(query[:, None, :, 1])
    c_lat = np.radians(candidates[None, :, :, 0])
    c_lon = np.radians(candidates[None, :, :, 1])
    h = np.sin((c_lat - q_lat) / 2.0) ** 2 + np.cos(q_lat) * np.cos(c_lat) * np.sin((c_lon - q_lon) / 2.0) ** 2
    return (2.0 * radius_m * np.arcsin(np.minimum(1.0, np.sqrt(h)))).mean(axis=2)


def evaluate(query_csv: Path, originals_csv: Path, landmarks: int) -> tuple[pd.DataFrame, dict[str, float]]:
    query_ids, query = fixed_landmarks(pd.read_csv(query_csv), landmarks)
    original_ids, originals = fixed_landmarks(pd.read_csv(originals_csv), landmarks)
    if set(query_ids) != set(original_ids):
        raise ValueError("Query and original CSV files must have exactly the same trajectory IDs.")
    original_order = {trajectory_id: idx for idx, trajectory_id in enumerate(original_ids)}
    ranks: list[int] = []
    true_distances: list[float] = []
    nearest_distances: list[float] = []
    for start in range(0, len(query), 32):
        distances = mean_haversine_matrix(query[start:start + 32], originals)
        sorted_indices = np.argsort(distances, axis=1)
        for local_idx, trajectory_id in enumerate(query_ids[start:start + 32]):
            true_index = original_order[int(trajectory_id)]
            rank = int(np.flatnonzero(sorted_indices[local_idx] == true_index)[0]) + 1
            ranks.append(rank)
            true_distances.append(float(distances[local_idx, true_index]))
            nearest_distances.append(float(distances[local_idx, sorted_indices[local_idx, 0]]))
    result = pd.DataFrame({
        "trajectory_id": query_ids,
        "rank_of_true_original": ranks,
        "true_original_distance_m": true_distances,
        "nearest_candidate_distance_m": nearest_distances,
    })
    n = len(result)
    summary = {
        "candidate_pool_size": n,
        "landmarks": landmarks,
        "top1_accuracy": float((result["rank_of_true_original"] <= 1).mean()),
        "top5_accuracy": float((result["rank_of_true_original"] <= 5).mean()),
        "median_true_rank": float(result["rank_of_true_original"].median()),
        "mean_true_rank": float(result["rank_of_true_original"].mean()),
        "random_top1": 1.0 / n,
        "random_top5": min(5.0 / n, 1.0),
    }
    return result, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, type=Path)
    parser.add_argument("--originals", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--landmarks", type=int, default=16)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows, summary = evaluate(args.query, args.originals, args.landmarks)
    rows.to_csv(args.out_dir / "per_trajectory_ranks.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

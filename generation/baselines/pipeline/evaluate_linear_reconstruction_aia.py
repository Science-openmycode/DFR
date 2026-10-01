"""Run a trajectory adaptation of Annamalai et al.'s linear reconstruction AIA.

The attack reconstructs a binary, destination-region secret from publicly known
trajectory quasi-identifiers and 3-way conditional marginals measured on a
synthetic release.  It implements the paper's bounded L1 linear program.

This command evaluates a *static-release diagnostic*.  The formal privacy game
in Annamalai et al. additionally randomizes each target's secret and regenerates
the synthetic release.  Use --formal-game only with such independently
generated challenge releases; this script otherwise labels the result as a
population-confounded diagnostic rather than individual-leakage evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, hstack, identity


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        value = pickle.load(handle)
    if isinstance(value, dict):
        for key in ("trajectories", "synthetic", "routes", "data", "dp_gsrt_portal_qrsp"):
            if key in value:
                value = value[key]
                break
    result = []
    for item in value:
        array = np.asarray(item, dtype=float)
        if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] >= 2:
            result.append(array[:, :2])
    if not result:
        raise ValueError(f"No coordinate trajectories found in {path}")
    return result


def haversine_km(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    radius = 6371.0088
    lat1, lon1 = np.radians(a[:, 0]), np.radians(a[:, 1])
    lat2, lon2 = np.radians(b[:, 0]), np.radians(b[:, 1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * radius * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def trajectory_table(trajectories: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int, length_cut_km: float) -> tuple[np.ndarray, np.ndarray]:
    lat0, lat1, lon0, lon1 = bbox
    rows, secrets = [], []
    for trace in trajectories:
        start, end = trace[0], trace[-1]
        origin_cell = int(np.clip((start[0] - lat0) / (lat1 - lat0) * grid, 0, grid - 1)) * grid + int(np.clip((start[1] - lon0) / (lon1 - lon0) * grid, 0, grid - 1))
        angle = np.arctan2(end[0] - start[0], end[1] - start[1])
        heading_bin = int(np.floor(((angle + np.pi) / (2.0 * np.pi)) * 8.0)) % 8
        segment_lengths = haversine_km(trace[:-1], trace[1:])
        length_bin = min(7, int(np.floor(np.log2(max(0.25, float(segment_lengths.sum()))))))
        rows.append((origin_cell, heading_bin, length_bin))
        secrets.append(int(float(segment_lengths.sum()) >= length_cut_km))
    return np.asarray(rows, dtype=int), np.asarray(secrets, dtype=int)


def query_matrix(target_qi: np.ndarray, generated_qi: np.ndarray, generated_secret: np.ndarray, max_queries: int, seed: int) -> tuple[csr_matrix, np.ndarray, list[tuple[int, int, int, int]]]:
    """Sample 3-way (two QI attributes plus binary secret) conditional queries."""
    rng = np.random.default_rng(seed)
    choices = []
    for left in range(target_qi.shape[1]):
        for right in range(left + 1, target_qi.shape[1]):
            for a in np.unique(target_qi[:, left]):
                for b in np.unique(target_qi[:, right]):
                    target_mask = (target_qi[:, left] == a) & (target_qi[:, right] == b)
                    generated_mask = (generated_qi[:, left] == a) & (generated_qi[:, right] == b)
                    if target_mask.sum() >= 2 and generated_mask.sum() >= 2:
                        choices.append((left, right, int(a), int(b)))
    if not choices:
        raise RuntimeError("No nonempty 3-way conditional queries under the selected quasi-identifiers")
    if len(choices) > max_queries:
        choices = [choices[i] for i in rng.choice(len(choices), max_queries, replace=False)]
    data, row_ids, col_ids, rhs = [], [], [], []
    n = len(target_qi)
    for row, (left, right, a, b) in enumerate(choices):
        target_mask = (target_qi[:, left] == a) & (target_qi[:, right] == b)
        generated_mask = (generated_qi[:, left] == a) & (generated_qi[:, right] == b)
        selected = np.flatnonzero(target_mask)
        row_ids.extend([row] * len(selected))
        col_ids.extend(selected.tolist())
        data.extend([1.0] * len(selected))
        probability = float(generated_secret[generated_mask].mean())
        rhs.append(probability * float(target_mask.mean()) * n)
    return csr_matrix((data, (row_ids, col_ids)), shape=(len(choices), n)), np.asarray(rhs, dtype=float), choices


def reconstruct(matrix: csr_matrix, rhs: np.ndarray) -> np.ndarray:
    """min ||A t-b||_1 subject to 0<=t<=1, exactly as the bounded LP form."""
    q, n = matrix.shape
    equality = hstack([matrix, -identity(q, format="csr"), identity(q, format="csr")], format="csr")
    objective = np.r_[np.zeros(n), np.ones(2 * q)]
    solution = linprog(
        objective,
        A_eq=equality,
        b_eq=rhs,
        bounds=[(0.0, 1.0)] * n + [(0.0, None)] * (2 * q),
        method="highs",
    )
    if not solution.success:
        raise RuntimeError(f"linear reconstruction failed: {solution.message}")
    return solution.x[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path, help="records whose quasi-identifiers are known to the attacker")
    parser.add_argument("--release", nargs=2, action="append", required=True, metavar=("NAME", "PATH"))
    parser.add_argument("--bbox", required=True, nargs=4, type=float)
    parser.add_argument("--grid", type=int, default=16)
    parser.add_argument("--length-cut-km", type=float, default=5.0, help="public fixed binary secret threshold")
    parser.add_argument("--max-targets", type=int, default=1000)
    parser.add_argument("--max-queries", type=int, default=1000)
    parser.add_argument("--formal-game", action="store_true", help="assert that each release was regenerated after challenge-secret randomization")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    target = load(args.targets)
    rng = np.random.default_rng(args.seed)
    if len(target) > args.max_targets:
        target = [target[i] for i in rng.choice(len(target), args.max_targets, replace=False)]
    bbox = tuple(args.bbox)
    target_qi, target_secret = trajectory_table(target, bbox, args.grid, args.length_cut_km)
    rows = []
    for index, (name, release_path) in enumerate(args.release):
        release_qi, release_secret = trajectory_table(load(Path(release_path)), bbox, args.grid, args.length_cut_km)
        matrix, rhs, queries = query_matrix(target_qi, release_qi, release_secret, args.max_queries, args.seed + index)
        reconstruction = reconstruct(matrix, rhs)
        guess = (reconstruction >= 0.5).astype(int)
        accuracy = float((guess == target_secret).mean())
        base_rate = max(float(target_secret.mean()), 1.0 - float(target_secret.mean()))
        rows.append({
            "method": name,
            "attack": "Advrecon-3way-conditional",
            "accuracy": accuracy,
            "base_rate_accuracy": base_rate,
            "advantage_over_base_rate": accuracy - base_rate,
            "targets": len(target),
            "queries": len(queries),
            "secret": f"trajectory_length_km>={args.length_cut_km}",
            "formal_randomized_secret_game": bool(args.formal_game),
        })
        print(f"[Advrecon] {name}: accuracy={accuracy:.4f}, base-rate={base_rate:.4f}, queries={len(queries)}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.out.with_suffix(".json").write_text(json.dumps({
        "attack": "linear reconstruction attribute inference",
        "citation": "Annamalai, Gadotti, and Rocher, A Linear Reconstruction Approach for Attribute Inference Attacks against Synthetic Data, USENIX Security 2024",
        "implementation": "3-way conditional-marginal bounded L1 linear program",
        "formal_game_warning": "Without independently regenerating each release after randomized target-secret challenges, this is a static-release diagnostic and cannot alone establish individual-level leakage.",
        "rows": rows,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

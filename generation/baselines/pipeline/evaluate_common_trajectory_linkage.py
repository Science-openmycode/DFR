"""Run two literature-grounded black-box trajectory linkage attacks.

Both attacks receive only a synthetic trajectory release and candidate raw
trajectories.  They deliberately do not use an input/output pairing, model
parameters, private OSM features, or a method-specific decoder:

* endpoint-pair: known origin/destination linkage, motivated by the known
  location side-information setting in trajectory re-identification work;
* fingerprint-8: known multi-location trajectory fingerprint linkage, motivated
  by the four-point uniqueness setting and nearest-sample attacks such as
  GAN-Leaks.

The script is a membership-linkage game: it ranks frozen member candidates
against matched non-members.  It is suitable for comparing releases produced
by DPMM, MTNet, and MTR only after all three releases were trained/generated
from the same frozen manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score


RADIUS_M = 6_371_008.8


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if isinstance(payload, dict):
        for key in ("trajectories", "synthetic", "routes", "data", "dp_gsrt_portal_qrsp"):
            if key in payload:
                payload = payload[key]
                break
    result = []
    for trajectory in payload:
        array = np.asarray(trajectory, dtype=float)
        if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] >= 2:
            result.append(array[:, :2])
    if not result:
        raise ValueError(f"No coordinate trajectories found in {path}")
    return result


def landmarks(trajectories: list[np.ndarray], count: int) -> np.ndarray:
    """Fixed arcless positional landmarks; a public feature extractor."""
    vectors = []
    for trajectory in trajectories:
        locations = np.linspace(0.0, len(trajectory) - 1, count)
        low = np.floor(locations).astype(int)
        high = np.ceil(locations).astype(int)
        fraction = (locations - low)[:, None]
        vectors.append(trajectory[low] * (1.0 - fraction) + trajectory[high] * fraction)
    return np.stack(vectors)


def nearest_mean_haversine(query: np.ndarray, release: np.ndarray, batch_size: int, release_batch_size: int) -> np.ndarray:
    """For every query, return its closest released trajectory's mean distance."""
    output = []
    for start in range(0, len(query), batch_size):
        block = query[start:start + batch_size]
        qlat = np.radians(block[:, None, :, 0])
        qlon = np.radians(block[:, None, :, 1])
        closest = np.full(len(block), np.inf)
        for release_start in range(0, len(release), release_batch_size):
            release_block = release[release_start:release_start + release_batch_size]
            release_lat = np.radians(release_block[None, :, :, 0])
            release_lon = np.radians(release_block[None, :, :, 1])
            h = np.sin((release_lat - qlat) / 2.0) ** 2 + np.cos(qlat) * np.cos(release_lat) * np.sin((release_lon - qlon) / 2.0) ** 2
            distances = 2.0 * RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(h)))
            closest = np.minimum(closest, distances.mean(axis=2).min(axis=1))
        output.append(closest)
    return np.concatenate(output)


def operating_point(scores: np.ndarray, labels: np.ndarray, fpr_limit: float) -> dict[str, float]:
    negatives = np.sort(scores[labels == 0])[::-1]
    # Largest threshold with empirical FPR <= limit; scores are larger = member.
    allowed = int(np.floor(fpr_limit * len(negatives)))
    threshold = float("inf") if allowed == 0 else float(negatives[allowed - 1])
    predicted = scores >= threshold
    fpr = float(predicted[labels == 0].mean())
    tpr = float(predicted[labels == 1].mean())
    return {"fpr_limit": fpr_limit, "realized_fpr": fpr, "tpr": tpr, "advantage": tpr - fpr, "threshold": threshold}


def bootstrap_auc(scores: np.ndarray, labels: np.ndarray, rng: np.random.Generator, rounds: int) -> list[float]:
    values = []
    member_idx = np.flatnonzero(labels == 1)
    nonmember_idx = np.flatnonzero(labels == 0)
    for _ in range(rounds):
        indices = np.r_[rng.choice(member_idx, len(member_idx), replace=True), rng.choice(nonmember_idx, len(nonmember_idx), replace=True)]
        values.append(float(roc_auc_score(labels[indices], scores[indices])))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members", required=True, type=Path)
    parser.add_argument("--nonmembers", required=True, type=Path)
    parser.add_argument("--release", nargs=2, action="append", required=True, metavar=("NAME", "PATH"))
    parser.add_argument("--attack", choices=("endpoint-pair", "fingerprint-8"), required=True)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--release-batch-size", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    anchor_count = 2 if args.attack == "endpoint-pair" else 8
    rng = np.random.default_rng(args.seed)
    members, nonmembers = load(args.members), load(args.nonmembers)
    n = min(len(members), len(nonmembers), args.max_candidates)
    members = [members[i] for i in rng.choice(len(members), n, replace=False)]
    nonmembers = [nonmembers[i] for i in rng.choice(len(nonmembers), n, replace=False)]
    queries = np.concatenate([landmarks(members, anchor_count), landmarks(nonmembers, anchor_count)])
    labels = np.r_[np.ones(n, dtype=int), np.zeros(n, dtype=int)]

    rows = []
    for name, release_path in args.release:
        release = landmarks(load(Path(release_path)), anchor_count)
        distances = nearest_mean_haversine(queries, release, args.batch_size, args.release_batch_size)
        scores = -distances
        auc_ci = bootstrap_auc(scores, labels, np.random.default_rng(args.seed + len(rows) * 101), args.bootstrap)
        row = {
            "method": name,
            "attack": args.attack,
            "anchors": anchor_count,
            "candidate_members": n,
            "release_size": len(release),
            "auc": float(roc_auc_score(labels, scores)),
            "auc_bootstrap95_low": auc_ci[0],
            "auc_bootstrap95_high": auc_ci[1],
            "member_nearest_distance_m_mean": float(distances[:n].mean()),
            "nonmember_nearest_distance_m_mean": float(distances[n:].mean()),
        }
        for limit, prefix in ((0.01, "at1pct"), (0.05, "at5pct")):
            point = operating_point(scores, labels, limit)
            row.update({f"{prefix}_{key}": value for key, value in point.items() if key != "fpr_limit"})
        rows.append(row)
        print(f"[{args.attack}] {name}: AUC={row['auc']:.4f}, TPR@1%={row['at1pct_tpr']:.4f}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(json.dumps({
        "attack": args.attack,
        "threat_model": "black-box synthetic release plus known candidate locations; no model, decoder, pairing, or private condition access",
        "literature": {
            "endpoint_pair": "de Montjoye et al., Scientific Reports 2013; known-location trajectory re-identification setting",
            "fingerprint_8": "de Montjoye et al., Scientific Reports 2013; Chen et al., CCS 2020 GAN-Leaks nearest-sample MIA",
        },
        "warning": "Compare methods only when every release was independently generated from the same frozen training manifest.",
        "seed": args.seed,
        "rows": rows,
    }, indent=2), encoding="utf-8")
    with args.out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

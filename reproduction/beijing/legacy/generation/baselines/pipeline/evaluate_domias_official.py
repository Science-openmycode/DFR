"""Run DOMIAS authors' public no-box attacks on fixed-length trajectory views.

The attack implementations are imported from the authors' DOMIAS repository:
https://github.com/vanderschaarlab/DOMIAS .  This wrapper only supplies a
public, fixed trajectory representation (equally indexed latitude/longitude
landmarks normalized by a declared bbox) and records the protocol.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        value = pickle.load(handle)
    if isinstance(value, dict):
        value = next(value[k] for k in ("trajectories", "routes", "synthetic", "data") if k in value)
    return [np.asarray(x, dtype=float)[:, :2] for x in value if np.asarray(x).ndim == 2 and len(x) >= 2]


def landmarks(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], count: int) -> np.ndarray:
    lat0, lat1, lon0, lon1 = bbox
    vectors = []
    for traj in trajs:
        indices = np.linspace(0, len(traj) - 1, count).round().astype(int)
        points = traj[indices].copy()
        points[:, 0] = (points[:, 0] - lat0) / (lat1 - lat0)
        points[:, 1] = (points[:, 1] - lon0) / (lon1 - lon0)
        vectors.append(points.ravel())
    return np.asarray(vectors, dtype=float)


def bootstrap_auc(scores: np.ndarray, labels: np.ndarray, seed: int, rounds: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    members = np.flatnonzero(labels == 1)
    nonmembers = np.flatnonzero(labels == 0)
    values = []
    for _ in range(rounds):
        indices = np.r_[rng.choice(members, len(members), replace=True), rng.choice(nonmembers, len(nonmembers), replace=True)]
        values.append(float(roc_auc_score(labels[indices], scores[indices])))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def tpr_at_fpr(scores: np.ndarray, labels: np.ndarray, limit: float) -> tuple[float, float]:
    negatives = np.sort(scores[labels == 0])[::-1]
    allowed = max(1, int(np.floor(limit * len(negatives))))
    threshold = float(negatives[allowed - 1])
    predicted = scores >= threshold
    return float(predicted[labels == 0].mean()), float(predicted[labels == 1].mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domias-root", required=True, type=Path)
    parser.add_argument("--members", required=True, type=Path)
    parser.add_argument("--nonmembers", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--release", nargs=2, action="append", required=True, metavar=("NAME", "PATH"))
    parser.add_argument("--bbox", required=True, nargs=4, type=float)
    parser.add_argument("--landmarks", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.domias_root / "src"))
    from domias.baselines import GAN_leaks, GAN_leaks_cal, compute_metrics_baseline, kde_baseline  # type: ignore

    rng = np.random.default_rng(args.seed)
    members, nonmembers = load(args.members), load(args.nonmembers)
    n = min(len(members), len(nonmembers), args.max_candidates)
    members = [members[i] for i in rng.choice(len(members), n, replace=False)]
    nonmembers = [nonmembers[i] for i in rng.choice(len(nonmembers), n, replace=False)]
    bbox = tuple(args.bbox)
    x_test = np.vstack([landmarks(members, bbox, args.landmarks), landmarks(nonmembers, bbox, args.landmarks)])
    labels = np.r_[np.ones(n), np.zeros(n)]
    ref = landmarks(load(args.reference), bbox, args.landmarks)

    rows: list[dict[str, object]] = []
    for release_index, (name, release_path) in enumerate(args.release):
        generated = landmarks(load(Path(release_path)), bbox, args.landmarks)
        eq1, eq2 = kde_baseline(x_test, generated, ref)
        attacks = {
            "DOMIAS-Eq1-KDE": eq1,
            "DOMIAS-Eq2-KDE": eq2,
            "GAN-Leaks": GAN_leaks(x_test, generated),
            "GAN-Leaks-calibrated": GAN_leaks_cal(x_test, generated, ref),
        }
        for attack_index, (attack, scores) in enumerate(attacks.items()):
            accuracy, aucroc = compute_metrics_baseline(scores, labels)
            scores = np.asarray(scores, dtype=float)
            ci_low, ci_high = bootstrap_auc(scores, labels, args.seed + release_index * 1009 + attack_index, args.bootstrap)
            fpr1, tpr1 = tpr_at_fpr(scores, labels, 0.01)
            fpr5, tpr5 = tpr_at_fpr(scores, labels, 0.05)
            rows.append({
                "method": name,
                "attack": attack,
                "aucroc": float(aucroc),
                "auc_bootstrap95_low": ci_low,
                "auc_bootstrap95_high": ci_high,
                "accuracy": float(accuracy),
                "tpr_at_1pct_fpr": tpr1,
                "realized_fpr_at_1pct": fpr1,
                "tpr_at_5pct_fpr": tpr5,
                "realized_fpr_at_5pct": fpr5,
                "members": n,
                "reference": len(ref),
            })
            print(f"[DOMIAS] {name}/{attack}: AUC={aucroc:.4f}, accuracy={accuracy:.4f}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    args.out.with_suffix(".json").write_text(json.dumps({"implementation": "vanderschaarlab/DOMIAS official functions", "bbox": bbox, "landmarks": args.landmarks, "rows": rows}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

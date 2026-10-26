"""Release-only membership attack for an MTNet private-condition diagnostic.

The target release contains paths decoded after forwarding private source-road
conditions.  Given a candidate's map-matched source edge, an attacker scores
it by that edge's released frequency.  This is deliberately specific to the
invalid private-condition protocol; it is not an attack on MTNet public-seed
releases.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score


def bootstrap_auc(scores: np.ndarray, labels: np.ndarray, seed: int, rounds: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    pos, neg = np.flatnonzero(labels == 1), np.flatnonzero(labels == 0)
    values = []
    for _ in range(rounds):
        indices = np.r_[rng.choice(pos, len(pos), replace=True), rng.choice(neg, len(neg), replace=True)]
        values.append(float(roc_auc_score(labels[indices], scores[indices])))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def tpr_at_fpr(scores: np.ndarray, labels: np.ndarray, limit: float) -> tuple[float, float]:
    negative = np.sort(scores[labels == 0])[::-1]
    threshold = float(negative[max(1, int(np.floor(len(negative) * limit))) - 1])
    predicted = scores >= threshold
    return float(predicted[labels == 0].mean()), float(predicted[labels == 1].mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--release-key", default="mtnet_paper_dpsgd")
    parser.add_argument("--max-per-class", type=int, default=71)
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    with args.candidates.open("rb") as handle:
        candidates = pickle.load(handle)["records"]
    with args.release.open("rb") as handle:
        release = pickle.load(handle)[args.release_key]
    starts = Counter(int(route[0]) for route in release if route)
    rng = np.random.default_rng(args.seed)
    selected = []
    for label in (0, 1):
        group = [item for item in candidates if int(item["label"]) == label]
        selected.extend(group[i] for i in rng.choice(len(group), min(len(group), args.max_per_class), replace=False))
    rng.shuffle(selected)
    labels = np.asarray([int(item["label"]) for item in selected])
    # Score only uses a candidate's known start road edge and the released paths.
    scores = np.asarray([np.log1p(starts.get(int(item["route"][0]), 0)) for item in selected], dtype=float)
    low, high = bootstrap_auc(scores, labels, args.seed, args.bootstrap)
    fpr1, tpr1 = tpr_at_fpr(scores, labels, 0.01)
    fpr5, tpr5 = tpr_at_fpr(scores, labels, 0.05)
    row = {
        "attack": "MTNet_private_origin_frequency_MIA",
        "auc": float(roc_auc_score(labels, scores)),
        "auc_bootstrap95_low": low,
        "auc_bootstrap95_high": high,
        "tpr_at_1pct_fpr": tpr1,
        "realized_fpr_at_1pct": fpr1,
        "tpr_at_5pct_fpr": tpr5,
        "realized_fpr_at_5pct": fpr5,
        "members": int((labels == 1).sum()),
        "nonmembers": int((labels == 0).sum()),
        "release_size": len(release),
        "private_origin_forwarded": True,
    }
    out = args.out.resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps({
        "threat_model": "release-only: candidate source edge plus released MTNet routes; no model access or record pairing",
        "scope": "private-condition diagnostic only; not valid for a public-seed DP release",
        "result": row,
    }, indent=2), encoding="utf-8")
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
    print(json.dumps(row, indent=2), flush=True)


if __name__ == "__main__":
    main()

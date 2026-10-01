"""Conditional Monte-Carlo membership inference against an MTNet checkpoint.

The attack follows Hilprecht et al. (2019): for a candidate trajectory t, it
queries the target generator repeatedly and uses the distance to the closest
sample as its membership score.  Here the only query condition is MTNet's
native public interface: source road edge and departure-time slot.  The
candidate's remaining path is never passed to ``Model.sample``.

This command is intentionally model-specific and must not be compared to
release-only attacks on DPMM or MTR.  It evaluates whether an MTNet model
memorizes complete routes conditional on the information it accepts at query
time.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import random
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score


def read_candidates(path: Path) -> list[dict]:
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    records = payload["records"] if isinstance(payload, dict) else payload
    result = []
    for record in records:
        route = [int(x) for x in record["route"] if int(x) > 0]
        if len(route) >= 2:
            result.append({"route": route, "departure": float(record["departure"]), "label": int(record["label"])})
    if not result:
        raise ValueError("candidate file contains no valid FMM routes")
    return result


def levenshtein_normalized(first: list[int], second: list[int]) -> float:
    """Unit-cost route edit distance divided by the longer route length."""
    if len(first) < len(second):
        first, second = second, first
    previous = list(range(len(second) + 1))
    for i, value in enumerate(first, start=1):
        current = [i]
        for j, other in enumerate(second, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (value != other)))
        previous = current
    return previous[-1] / max(1, len(first))


def bootstrap_auc(scores: np.ndarray, labels: np.ndarray, seed: int, rounds: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    positive, negative = np.flatnonzero(labels == 1), np.flatnonzero(labels == 0)
    values = []
    for _ in range(rounds):
        indices = np.r_[rng.choice(positive, len(positive), replace=True), rng.choice(negative, len(negative), replace=True)]
        values.append(float(roc_auc_score(labels[indices], scores[indices])))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def tpr_at_fpr(scores: np.ndarray, labels: np.ndarray, limit: float) -> tuple[float, float]:
    negative = np.sort(scores[labels == 0])[::-1]
    threshold = float(negative[max(1, int(np.floor(len(negative) * limit))) - 1])
    predicted = scores >= threshold
    return float(predicted[labels == 0].mean()), float(predicted[labels == 1].mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path, help="FMM-matched member/non-member candidate records")
    parser.add_argument("--mtnet-root", required=True, type=Path, help="unmodified MTNet source directory")
    parser.add_argument("--data-parent", required=True, type=Path, help="author-format MTNet data parent")
    parser.add_argument("--city", required=True)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--max-route-edges", type=int, default=100)
    parser.add_argument("--samples-per-condition", type=int, default=32)
    parser.add_argument("--max-per-class", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    # Resolve caller-supplied artifact paths before switching into the author
    # repository, whose relative imports require it as the current directory.
    candidates_path = args.candidates.resolve()
    model_path = args.model.resolve()
    data_parent = args.data_parent.resolve()
    output_path = args.out.resolve()
    records = read_candidates(candidates_path)
    rng = np.random.default_rng(args.seed)
    selected = []
    for label in (1, 0):
        rows = [row for row in records if row["label"] == label]
        if not rows:
            raise ValueError(f"candidate set has no label={label} records")
        count = min(len(rows), args.max_per_class)
        selected.extend(rows[i] for i in rng.choice(len(rows), count, replace=False))
    rng.shuffle(selected)

    root = args.mtnet_root.resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    import torch
    from util import config
    import mtnet

    config.DATA_BASE = str(data_parent) + os.sep
    config.CITY = args.city
    config.TRAJ_FIX_LEN = args.max_route_edges + 1
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    model = mtnet.Model()
    checkpoint = torch.load(model_path, map_location=config.device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    official_step = model.step

    def dtype_compatible_step(xt, departure_slot, hs, cs):
        return official_step(xt, departure_slot.long(), hs, cs)

    model.step = dtype_compatible_step
    closest = np.full(len(selected), np.inf)
    for draw in range(args.samples_per_condition):
        for start in range(0, len(selected), args.batch_size):
            stop = min(len(selected), start + args.batch_size)
            batch = selected[start:stop]
            origin = torch.as_tensor([[item["route"][0]] for item in batch], dtype=torch.long, device=config.device)
            # Match util.dataloader.load_trajs_raw exactly: raw UTC epoch
            # starts are converted to the model's UTC+8 time-of-day domain
            # before Model.sample divides them into 30-minute slots.
            departure_values = [((item["departure"] + 8 * 3600) % config.T_LOOP) for item in batch]
            departure = torch.as_tensor([[value] for value in departure_values], dtype=torch.float32, device=config.device)
            empty_cost = torch.zeros((len(batch), 0), dtype=torch.float32, device=config.device)
            with torch.no_grad():
                suffix, _ = model.sample(origin, departure, empty_cost)
            for offset, (item, generated) in enumerate(zip(batch, suffix.cpu().tolist())):
                route = [item["route"][0]] + [int(edge) for edge in generated if int(edge) > 0]
                closest[start + offset] = min(closest[start + offset], levenshtein_normalized(item["route"], route))
        print(f"[MTNet conditional MC-MIA] sampled {draw + 1}/{args.samples_per_condition}", flush=True)

    labels = np.asarray([item["label"] for item in selected], dtype=int)
    scores = -closest
    auc = float(roc_auc_score(labels, scores))
    ci_low, ci_high = bootstrap_auc(scores, labels, args.seed, args.bootstrap)
    fpr1, tpr1 = tpr_at_fpr(scores, labels, 0.01)
    fpr5, tpr5 = tpr_at_fpr(scores, labels, 0.05)
    row = {
        "attack": "conditional_monte_carlo_reconstruction_mia",
        "auc": auc,
        "auc_bootstrap95_low": ci_low,
        "auc_bootstrap95_high": ci_high,
        "accuracy": float(((scores >= np.median(scores)) == labels).mean()),
        "tpr_at_1pct_fpr": tpr1,
        "realized_fpr_at_1pct": fpr1,
        "tpr_at_5pct_fpr": tpr5,
        "realized_fpr_at_5pct": fpr5,
        "members": int((labels == 1).sum()),
        "nonmembers": int((labels == 0).sum()),
        "samples_per_condition": args.samples_per_condition,
        "distance": "normalized road-edge Levenshtein distance",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    output_path.with_suffix(".json").write_text(json.dumps({
        "citation": "Hilprecht, Haerterich, and Bernau, Reconstruction and Membership Inference Attacks against Generative Models, 2019",
        "threat_model": "black-box conditional sampling; only the candidate origin edge and departure time are passed to MTNet",
        "target_model": str(model_path),
        "candidate_file": str(candidates_path),
        "result": row,
    }, indent=2), encoding="utf-8")
    print(json.dumps(row, indent=2), flush=True)


if __name__ == "__main__":
    main()

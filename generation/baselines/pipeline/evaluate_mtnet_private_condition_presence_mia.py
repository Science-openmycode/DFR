"""Targeted membership inference caused by forwarding private MTNet origins.

The local conditional-generation interface draws a real source edge for every
output and serializes that edge as the first edge of the released route.  This
script evaluates a *targeted rare-origin presence game*: an adversary knows a
candidate's source road edge and declares membership when that edge occurs in
the release.  The game is deliberately restricted to source edges that occur
once in the fitting corpus for members and zero times for non-members, making
the event a clean test of private-condition forwarding rather than population
frequency modelling.
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


def load_routes(path: Path) -> list[list[int]]:
    return [
        [int(token) for token in line.split() if int(token) > 0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training-routes", type=Path, required=True)
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--release-size", type=int, default=17123)
    p.add_argument("--trials", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20260720)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    routes = load_routes(a.training_routes)
    starts = np.asarray([route[0] for route in routes if route], dtype=int)
    if not len(starts):
        raise RuntimeError("training route file contains no non-empty routes")
    counts = Counter(starts.tolist())
    population_multiplicity = np.asarray([counts[int(edge)] for edge in starts], dtype=int)
    with a.candidates.open("rb") as handle:
        candidates = pickle.load(handle)["records"]
    members = [row for row in candidates if int(row["label"]) == 1 and counts.get(int(row["route"][0]), 0) == 1]
    nonmembers = [row for row in candidates if int(row["label"]) == 0 and counts.get(int(row["route"][0]), 0) == 0]
    if len(members) < 5:
        raise RuntimeError(f"need at least five unique-origin members; found {len(members)}")
    rng = np.random.default_rng(a.seed)
    # The primary game is a standard neighbouring-dataset membership game:
    # D contains one target with a unique origin e; D' removes it.  It does
    # not require a coincidentally absent held-out edge, which is rare in a
    # dense city network and not required by the DP definition.
    n = min(len(members), 100)
    members = [members[i] for i in rng.choice(len(members), n, replace=False)]
    candidate_starts = np.asarray([int(row["route"][0]) for row in members], dtype=int)
    trial_rows = []
    for trial in range(a.trials):
        emitted_starts = starts[rng.integers(0, len(starts), size=a.release_size)]
        observed = set(emitted_starts.tolist())
        # For every selected target, D' removes its unique edge.  The
        # forwarding event is therefore impossible under D' but observable
        # under D whenever the source sampler selects the target.
        positives = np.asarray([edge in observed for edge in candidate_starts], dtype=float)
        tpr = float(positives.mean())
        fpr = 0.0
        trial_rows.append({"trial": trial, "auc": 0.5 * (1.0 + tpr), "tpr": tpr, "fpr": fpr,
                           "advantage": tpr, "observed_member_origins": int(positives.sum())})
    trials = {key: np.asarray([row[key] for row in trial_rows], dtype=float) for key in trial_rows[0] if key != "trial"}
    # All retained member origins occur once in the n-record source population.
    theoretical_tpr = 1.0 - (1.0 - 1.0 / len(starts)) ** a.release_size
    anonymity = np.asarray([counts[int(row["route"][0])] for row in members], dtype=int)
    result = {
        "attack": "targeted_rare_origin_presence_membership_inference",
        "threat_model": "black-box release plus target origin road edge; attacker observes released first edges, not model weights or a paired record identifier",
        "release_interface": "one private source origin is forwarded as the first edge of each MTNet output",
        "training_records": int(len(starts)), "release_size": int(a.release_size), "trials": int(a.trials),
        "target_unique_origins": int(n), "heldout_absent_origin_candidates": int(len(nonmembers)),
        "member_origin_multiplicity": {"min": int(anonymity.min()), "median": float(np.median(anonymity)), "max": int(anonymity.max())},
        "population_origin_linkability": {
            "distinct_origins": int(len(counts)),
            "records_with_unique_origin": int((population_multiplicity == 1).sum()),
            "unique_origin_record_fraction": float((population_multiplicity == 1).mean()),
            "median_anonymity_set_size": float(np.median(population_multiplicity)),
            "expected_top1_linkage_from_origin_only": float(np.mean(1.0 / population_multiplicity)),
        },
        "theoretical_member_origin_observation_probability": float(theoretical_tpr),
        "empirical": {key: {"mean": float(values.mean()), "q025": float(np.quantile(values, .025)), "q975": float(np.quantile(values, .975))} for key, values in trials.items()},
        "dp_witness": {
            "event": "at least one released trajectory starts with the target's unique private origin edge",
            "neighbor_probability_without_target": 0.0,
            "neighbor_probability_with_target": float(theoretical_tpr),
            "consequence": "for this forwarded-condition release, any record-DP claim requires delta at least this event probability; no finite pure-DP epsilon can bound a zero-probability neighbor event",
        },
        "scope": "This is a targeted neighbouring-dataset attack on a private-condition forwarding interface. It does not apply when source conditions are public and independent of the protected data.",
    }
    out = a.out.resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trial_rows[0]))
        writer.writeheader(); writer.writerows(trial_rows)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()

"""Aggregate completed DFR epsilon-sweep profiles and draw reproducible curves."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


METRICS = ["RoadYield", "DirValid", "WitnessValid", "TripSim", "GridSim", "LengthSim", "NextRoadAcc", "RouteMRR", "RouteBest5F1"]
EPS = [0.2, 0.4, 0.7, 1.0, 1.4, 2.0, 3.0]


def bootstrap_ci(values: list[float], seed: int = 20261003) -> tuple[float, float]:
    if len(values) < 2:
        return values[0], values[0]
    rng = np.random.default_rng(seed)
    samples = rng.choice(np.asarray(values), size=(2000, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, default=Path("experiment_results/sensitivity/local_budget"))
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()
    root = args.input_dir.resolve()
    out = (args.output_dir or root).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for p in sorted(root.glob("profile_eps_*_seed*/results.csv")):
        parts = p.parent.name.split("_")
        # profile_eps_0_2_seed20260719
        eps = float(parts[2] + "." + parts[3])
        seed = int(parts[4].replace("seed", ""))
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["metric"] in METRICS and r.get("status", "VALID") == "VALID":
                    rows.append({"epsilon": eps, "seed": seed, "metric": r["metric"], "value": float(r["value"]), "source": str(p)})
    expected = len(EPS) * 5 * len(METRICS)
    if len(rows) != expected:
        raise SystemExit(f"incomplete sweep: {len(rows)} rows, expected {expected}")
    with (out / "metrics_long.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["epsilon", "seed", "metric", "value", "source"])
        w.writeheader(); w.writerows(rows)
    summary = []
    for eps in EPS:
        for metric in METRICS:
            vals = [float(r["value"]) for r in rows if r["epsilon"] == eps and r["metric"] == metric]
            lo, hi = bootstrap_ci(vals)
            summary.append({"epsilon": eps, "metric": metric, "n_seeds": len(vals), "mean": float(np.mean(vals)), "std": float(np.std(vals, ddof=1)), "ci95_low": lo, "ci95_high": hi})
    with (out / "metrics_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    fig, axes = plt.subplots(3, 3, figsize=(13, 10), sharex=True)
    colors = {"RoadYield": "#1f77b4", "DirValid": "#2ca02c", "WitnessValid": "#9467bd", "TripSim": "#d62728", "GridSim": "#ff7f0e", "LengthSim": "#8c564b", "NextRoadAcc": "#17becf", "RouteMRR": "#e377c2", "RouteBest5F1": "#7f7f7f"}
    for ax, metric in zip(axes.ravel(), METRICS):
        s = [r for r in summary if r["metric"] == metric]
        x = np.array([r["epsilon"] for r in s]); y = np.array([r["mean"] for r in s]); lo = np.array([r["ci95_low"] for r in s]); hi = np.array([r["ci95_high"] for r in s])
        ax.plot(x, y, marker="o", color=colors[metric], linewidth=2); ax.fill_between(x, lo, hi, color=colors[metric], alpha=.16)
        ax.set_title(metric); ax.grid(alpha=.22); ax.set_xscale("log"); ax.set_xticks(EPS); ax.set_xticklabels(["1/5", "2/5", "7/10", "1", "7/5", "2", "3"], rotation=35)
        ax.set_ylim(0, 1.05)
    fig.suptitle("MTR-DFR privacy-budget sensitivity (five seeds)")
    fig.tight_layout(); fig.savefig(out / "dfr_epsilon_sensitivity_5seed.png", dpi=240); fig.savefig(out / "dfr_epsilon_sensitivity_5seed.pdf")
    (out / "aggregation_manifest.json").write_text(json.dumps({"status": "complete", "epsilons": EPS, "seeds": [20260719, 20260720, 20260721, 20260722, 20260723], "metrics": METRICS, "classification": "RESEARCH_ONLY_REPRODUCIBLE_NOISE_DO_NOT_RELEASE", "rows": len(rows)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

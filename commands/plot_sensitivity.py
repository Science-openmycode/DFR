"""Plot the completed DFR resolution and privacy-budget sensitivity results."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


METRICS = ["TripSim", "GridSim", "LengthSim", "NextRoadAcc", "RouteMRR", "RouteBest5F1"]


def plot_one(df: pd.DataFrame, parameter: str, out: Path, title: str) -> None:
    pivot = df.pivot(index=parameter, columns="metric", values="value")
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for ax, metric in zip(axes.flat, METRICS):
        if metric not in pivot:
            ax.set_visible(False)
            continue
        series = pivot[metric].sort_index()
        ax.plot(series.index, series.values, marker="o", linewidth=2, color="#1f5a94")
        ax.set_title(metric)
        ax.set_xlabel(parameter)
        ax.set_ylim(0, 1.02)
        ax.grid(alpha=0.25)
    fig.suptitle(title)
    fig.savefig(out, dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("experiment_results/sensitivity/dfr_sensitivity_summary.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("experiment_results/sensitivity"))
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    k = df[df.sweep == "resolution"].rename(columns={"K": "parameter"})
    e = df[df.sweep == "epsilon"].rename(columns={"epsilon": "parameter"})
    plot_one(k, "parameter", args.out_dir / "dfr_resolution_k_sensitivity.png", "DFR resolution sensitivity")
    plot_one(e, "parameter", args.out_dir / "dfr_epsilon_sensitivity.png", "DFR privacy-budget sensitivity")


if __name__ == "__main__":
    main()

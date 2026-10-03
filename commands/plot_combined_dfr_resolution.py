"""Combine the original and extended DFR resolution sweeps in one figure.

The original K=2--64 points and the continuation K=48--384 were run in
different environments.  This script preserves their provenance in the CSV
while presenting one ordered resolution curve for visual comparison.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


METRICS = ["TripSim", "GridSim", "LengthSim", "NextRoadAcc", "RouteMRR", "RouteBest5F1"]


def load_original(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["sweep"].eq("resolution")].copy()
    df["K"] = pd.to_numeric(df["K"], errors="raise").astype(int)
    df["source"] = "original_resolution_sweep"
    return df[["K", "seed", "metric", "value", "source"]]


def load_extended(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["K"] = pd.to_numeric(df["parameter"].astype(str).str.replace("K=", "", regex=False), errors="raise").astype(int)
    df["source"] = "local_extended_resolution_sweep"
    return df[["K", "seed", "metric", "value", "source"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original", type=Path, default=Path("experiment_results/sensitivity/dfr_sensitivity_summary.csv"))
    ap.add_argument("--extended", type=Path, default=Path("experiment_results/sensitivity/local_extended/dfr_resolution_local_extended_summary.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("experiment_results/sensitivity"))
    args = ap.parse_args()

    df = pd.concat([load_original(args.original), load_extended(args.extended)], ignore_index=True)
    df = df[df.metric.isin(METRICS)].sort_values(["K", "metric", "seed"])
    if df.duplicated(["K", "metric", "seed"]).any():
        raise ValueError("duplicate K/metric/seed rows in combined sweep")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "dfr_resolution_k_sensitivity_combined.csv"
    df.to_csv(csv_path, index=False)

    # One point per K. Original points are single-seed; continuation points
    # are summarized over the available seed(s), retaining all raw rows above.
    summary = df.groupby(["K", "metric"], as_index=False)["value"].agg(["mean", "std", "count"]).reset_index()
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.2), constrained_layout=True)
    all_k = sorted(summary.K.unique())
    label_k = [k for k in [2, 4, 8, 16, 32, 48, 64, 96, 128, 192, 256, 384] if k in all_k]
    for ax, metric in zip(axes.flat, METRICS):
        s = summary[summary.metric.eq(metric)].sort_values("K")
        ax.plot(s["K"], s["mean"], marker="o", linewidth=2.1, color="#1f5a94", label="combined")
        ax.fill_between(s["K"], s["mean"] - s["std"].fillna(0), s["mean"] + s["std"].fillna(0), color="#1f5a94", alpha=0.12)
        ax.set_title(metric)
        ax.set_xlabel("resolution K (log2 scale)")
        ax.set_ylabel("utility (higher is better)")
        ax.set_ylim(0, 1.02)
        ax.set_xscale("log", base=2)
        ax.set_xticks(label_k)
        ax.set_xticklabels([str(k) for k in label_k], rotation=45, ha="right", fontsize=8)
        ax.axvline(64, color="#7f7f7f", linestyle="--", linewidth=1, alpha=0.7)
        ax.text(0.98, 0.06, "old / extended boundary", transform=ax.transAxes, ha="right", fontsize=7, color="#666666")
        ax.grid(alpha=0.25)
    fig.suptitle("DFR resolution sensitivity: original and extended K sweep", fontsize=14)
    png = args.out_dir / "dfr_resolution_k_sensitivity_combined.png"
    pdf = args.out_dir / "dfr_resolution_k_sensitivity_combined.pdf"
    fig.savefig(png, dpi=260)
    fig.savefig(pdf)
    plt.close(fig)
    print(f"rows={len(df)} K={sorted(df.K.unique())}")
    print(f"csv={csv_path}")
    print(f"png={png}")
    print(f"pdf={pdf}")


if __name__ == "__main__":
    main()

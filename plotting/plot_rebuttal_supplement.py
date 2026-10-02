"""Plot the committed rebuttal supplement CSV artifacts.

This script intentionally plots only already materialized CSV files. It does not
regenerate a private release or alter the frozen experiment ledger.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

BLUE = "#1f4e79"
ORANGE = "#d97706"
GREEN = "#2f855a"

def partition(args):
    df = pd.read_csv(args.input)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(df["fine_regions"], df["portal_global_cpc_mean"], marker="o", color=BLUE, label="Global CPC")
    ax.plot(df["fine_regions"], df["portal_context_ndcg_mean"], marker="s", color=GREEN, label="Context NDCG")
    ax.set_xlabel("Fine regions (K)"); ax.set_ylabel("Score"); ax.grid(alpha=.25); ax.legend(frameon=False)
    args.out_dir.mkdir(parents=True, exist_ok=True); fig.tight_layout(); fig.savefig(args.out_dir / "q5_partition_granularity_sensitivity.pdf"); fig.savefig(args.out_dir / "q5_partition_granularity_sensitivity.png", dpi=220); plt.close(fig)

def multicity(args):
    df = pd.read_csv(args.input_dir / "q6_multicity_five_seed_summary.csv")
    cols = [("Grid_mean", "Grid"), ("Trip_mean", "Trip"), ("RouteMRR_mean", "Route MRR")]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, (col, label) in zip(axes, cols):
        ax.bar(df["city"], df[col], color=[BLUE, GREEN]); ax.set_title(label); ax.tick_params(axis="x", rotation=30); ax.grid(axis="y", alpha=.25)
    args.out_dir.mkdir(parents=True, exist_ok=True); fig.tight_layout(); fig.savefig(args.out_dir / "q6_multicity_five_seed.png", dpi=220); fig.savefig(args.out_dir / "q6_multicity_five_seed.pdf"); plt.close(fig)

def low_epsilon(args):
    df = pd.read_csv(args.input_dir / "q6_full_release_utility_summary.csv")
    x = df["epsilon"].astype(str); fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(x, df["RouteMRR_mean"], marker="o", color=BLUE, label="Route MRR")
    ax.plot(x, df["RC_NDCG_mean"], marker="s", color=ORANGE, label="RC-NDCG")
    ax.set_xlabel("epsilon"); ax.set_ylabel("Mean score"); ax.grid(alpha=.25); ax.legend(frameon=False)
    args.out_dir.mkdir(parents=True, exist_ok=True); fig.tight_layout(); fig.savefig(args.out_dir / "q6_low_epsilon.png", dpi=220); fig.savefig(args.out_dir / "q6_low_epsilon.pdf"); plt.close(fig)

def portal_ablation(args):
    df = pd.read_csv(args.input)
    metrics = ["RC-CPC", "RC-NDCG", "NextRoadAcc"]
    x = range(len(metrics)); fig, ax = plt.subplots(figsize=(7.2, 4.2)); w=.36
    a=df.set_index("metric")
    ax.bar([i-w/2 for i in x], [a.loc[m, "MTR-GSRT"] for m in metrics], width=w, color=BLUE, label="MTR-GSRT")
    ax.bar([i+w/2 for i in x], [a.loc[m, "No Portal unit"] for m in metrics], width=w, color=ORANGE, label="No Portal unit")
    ax.set_xticks(list(x), metrics); ax.set_ylim(0,1); ax.grid(axis="y", alpha=.25); ax.legend(frameon=False)
    args.out_dir.mkdir(parents=True, exist_ok=True); fig.tight_layout(); fig.savefig(args.out_dir / "portal_fiber_ablation.png", dpi=220); fig.savefig(args.out_dir / "portal_fiber_ablation.pdf"); plt.close(fig)

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="stage", required=True)
    for name, fn in [("partition",partition),("multicity",multicity),("low-epsilon",low_epsilon),("portal-ablation",portal_ablation)]:
        q=sub.add_parser(name); q.set_defaults(fn=fn); q.add_argument("--out-dir", type=Path, required=True)
        if name in {"partition","portal-ablation"}: q.add_argument("--input", type=Path, required=True)
        else: q.add_argument("--input-dir", type=Path, required=True)
    a=p.parse_args(); a.fn(a)
if __name__ == "__main__": main()

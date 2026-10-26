"""Render the strict held-out task results from the persisted TSTR CSV."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


METHODS = ["SPRT", "PrivTrace", "DPTraj-PM", "MTR/DP-GSRT"]
LABELS = ["SPRT", "PrivTrace", "DPTraj-PM", "MTR/DP-GSRT"]
COLORS = ["#bc4b51", "#8b5fa8", "#b7791f", "#0b8f72"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with a.csv.open(newline="", encoding="utf-8") as f:
        rows = {r["method"]: r for r in csv.DictReader(f)}
    metrics = [
        ("range_query_are", "Range-query ARE", "lower"),
        ("next_road_hit_at_5", "Next-road Hit@5", "higher"),
        ("route_popularity_hit_at_10", "Route-popularity Hit@10", "higher"),
        ("trajectory_suffix_accuracy", "Suffix continuation", "higher"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(12.8, 3.0), constrained_layout=True)
    x = np.arange(len(METHODS))
    for ax, (key, title, direction) in zip(axes, metrics):
        values = [float(rows[m][key]) for m in METHODS]
        ax.bar(x, values, color=COLORS, width=.72)
        real = float(rows["Real-train"][key])
        ax.axhline(real, color="#1f4e8c", linewidth=1.45, linestyle="--", label="Real-train")
        ax.set_title(title + (" (lower)" if direction == "lower" else " (higher)"), fontsize=9)
        ax.set_xticks(x); ax.set_xticklabels(LABELS, rotation=32, ha="right", fontsize=7)
        ax.grid(axis="y", color="#d6dde0", linewidth=.55); ax.set_axisbelow(True)
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out.with_suffix(".png"), dpi=320, bbox_inches="tight", facecolor="white")
    fig.savefig(a.out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print(f"wrote {a.out.with_suffix('.png')}", flush=True)


if __name__ == "__main__":
    main()

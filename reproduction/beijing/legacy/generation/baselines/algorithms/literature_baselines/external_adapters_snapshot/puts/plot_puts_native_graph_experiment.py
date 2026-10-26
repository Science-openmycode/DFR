"""Plot the fair reduced-road Beijing PUTS diagnostic as a three-panel figure."""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from run_mtr_dp_gsrt_on_puts_native_graph import read_lines, read_selected_lines


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        return [np.asarray(x, dtype=float) for x in pickle.load(handle) if len(x) >= 2]


def panel(ax, data: list[np.ndarray], roads: list[np.ndarray], title: str, note: str, color: str) -> None:
    road_segments = [line[:, [1, 0]] for line in roads if len(line) >= 2]
    ax.add_collection(LineCollection(road_segments, colors="#7f8b96", linewidths=.18, alpha=.16, zorder=1))
    trajectories = [line[:, [1, 0]] for line in data if len(line) >= 2]
    ax.add_collection(LineCollection(trajectories, colors=color, linewidths=.68, alpha=.48, zorder=2))
    all_points = np.vstack(roads)
    pad = .002
    ax.set_xlim(all_points[:, 1].min() - pad, all_points[:, 1].max() + pad)
    ax.set_ylim(all_points[:, 0].min() - pad, all_points[:, 0].max() + pad)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)
    ax.text(.02, .02, note, transform=ax.transAxes, fontsize=8.4, color="#20252a", va="bottom",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": .78, "pad": 2.4})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--geometry", type=Path, required=True)
    p.add_argument("--real", type=Path, required=True)
    p.add_argument("--mtr", type=Path, required=True)
    p.add_argument("--puts", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n-roads", type=int, default=3000)
    p.add_argument("--road-ids", type=Path, default=None)
    p.add_argument("--n-train", type=int, default=1000)
    p.add_argument("--epsilon", type=float, default=1.20)
    a = p.parse_args()
    print("[1/2] Loading graph-matched corpora and native PUTS road segments...", flush=True)
    roads = (read_selected_lines(a.geometry, [int(x) for x in a.road_ids.read_text().splitlines() if x.strip()])
             if a.road_ids else read_lines(a.geometry, a.n_roads))
    real, mtr, puts = load(a.real), load(a.mtr), load(a.puts)
    print("[2/2] Rendering three panels...", flush=True)
    fig, axes = plt.subplots(1, 3, figsize=(16.8, 5.4), constrained_layout=True)
    graph_note = f"shared {len(roads):,}-road PUTS native graph"
    panel(axes[0], real, roads, "Real Beijing subset", f"n = {len(real):,} private training trajectories\n{graph_note}", "#2467a4")
    panel(axes[1], mtr, roads, "MTR / DP-GSRT native-graph adapter", f"n = {len(mtr):,} fixed DP release slots\nε = {a.epsilon:.2f}; public candidates + DP sketch tilt", "#087f5b")
    panel(axes[2], puts, roads, "Original PUTS", f"n = {len(puts):,} fixed released trajectories\n{graph_note}", "#9148a7")
    fig.suptitle("Beijing reduced-road diagnostic: graph-matched comparison, not a full-city PUTS benchmark", fontsize=14, fontweight="bold")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(a.out.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {a.out.with_suffix('.png')} and PDF", flush=True)


if __name__ == "__main__":
    main()

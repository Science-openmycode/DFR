"""Render separate parent-corpus and PUTS-eligible appendix panels."""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import filter_osm_ways_by_bbox, load_osm_ways  # noqa: E402


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as f: return [np.asarray(x, float) for x in pickle.load(f) if len(x) >= 2]


def draw(ax, data, roads, bbox, title, color):
    road_lines = [np.asarray([[p["lon"], p["lat"]] for p in w["geometry"]], float) for w in roads if len(w.get("geometry", [])) >= 2]
    ax.add_collection(LineCollection(road_lines, colors="#b9c4ca", linewidths=.22, alpha=.22, zorder=1))
    ax.add_collection(LineCollection([t[:, [1, 0]] for t in data], colors=color, linewidths=.6, alpha=.53, zorder=2))
    ax.set(xlim=(bbox[2], bbox[3]), ylim=(bbox[0], bbox[1]), aspect="equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{title}\nn={len(data):,}", fontsize=11, fontweight="bold", pad=6)


def save_panels(path, panels, roads, bbox, heading):
    fig, axes = plt.subplots(1, len(panels), figsize=(5.0 * len(panels), 5.1), constrained_layout=True)
    for ax, (title, data, color) in zip(np.atleast_1d(axes), panels): draw(ax, data, roads, bbox, title, color)
    fig.suptitle(heading, fontsize=13, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path.with_suffix(".png"), dpi=320, bbox_inches="tight"); fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    print(f"wrote {path.with_suffix('.png')}", flush=True)


def save_combined(path, parent, mtr, dpmm, puts_real, puts_mtr, puts, roads, bbox):
    """Keep native interfaces visible in one appendix figure without truncation."""
    fig, axes = plt.subplots(2, 3, figsize=(15.6, 9.8))
    top = [("Real central parent", parent, "#2369a6"), ("MTR / DP-GSRT", mtr, "#07825e"), ("DPMM official", dpmm, "#9d3d70")]
    bottom = [
        ("Real FMM-eligible branch", puts_real, "#2369a6"),
        ("MTR / DP-GSRT", puts_mtr, "#07825e"),
        ("PUTS upstream", puts, "#b34b8e"),
    ]
    for ax, (title, data, color) in zip(axes[0], top): draw(ax, data, roads, bbox, title, color)
    for ax, (title, data, color) in zip(axes[1], bottom): draw(ax, data, roads, bbox, title, color)
    fig.suptitle("Beijing appendix: native method interfaces under one shared public OSM renderer", fontsize=14, fontweight="bold", y=.985)
    fig.subplots_adjust(left=.035, right=.99, bottom=.045, top=.90, wspace=.02, hspace=.24)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=320, bbox_inches="tight"); fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    print(f"wrote {path.with_suffix('.png')}", flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ("parent-real", "mtr", "dpmm", "puts-real", "puts-mtr", "puts", "osm-cache"): p.add_argument("--" + x, type=Path, required=True)
    p.add_argument("--bbox", nargs=4, type=float, required=True); p.add_argument("--out-dir", type=Path, required=True); a=p.parse_args(); bbox=tuple(a.bbox)
    roads=filter_osm_ways_by_bbox(load_osm_ways(a.osm_cache), bbox)
    parent,mtr,dpmm,puts_real,puts_mtr,puts=(load(getattr(a,x.replace('-','_'))) for x in ("parent_real","mtr","dpmm","puts_real","puts_mtr","puts"))
    save_panels(a.out_dir / "parent_3000_mtr_dpmm", [("Real parent corpus",parent,"#2369a6"),("MTR / DP-GSRT",mtr,"#07825e"),("DPMM official",dpmm,"#9d3d70")],roads,bbox,"Beijing parent-corpus diagnostic: methods retain their native output counts")
    save_panels(a.out_dir / "puts_eligible_86", [("Real FMM-eligible records",puts_real,"#2369a6"),("PUTS upstream",puts,"#b34b8e")],roads,bbox,"Beijing PUTS eligibility diagnostic: upstream prerequisite branch")
    save_combined(a.out_dir / "appendix_puts_mtr_dpmm_beijing", parent, mtr, dpmm, puts_real, puts_mtr, puts, roads, bbox)


if __name__=="__main__": main()

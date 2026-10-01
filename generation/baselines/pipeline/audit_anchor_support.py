"""Audit DP-GSRT spatial-anchor support.

This is a research/debugging tool, not an additional release mechanism. It
reimplements the audited anchor query exactly: each trajectory contributes a
unit L1 mass distributed over the visited public-bbox cells, Laplace noise is
added with the requested anchor budget, and the top-A noisy cells are retained.

Coverage fields in the output are computed against the local raw corpus and
are therefore research diagnostics only. They must not be published as a
non-private release statistic.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PUBLIC_ROOT = Path(__file__).resolve().parents[1]
if str(PUBLIC_ROOT) not in sys.path:
    sys.path.insert(0, str(PUBLIC_ROOT))

from public_utils import load_trajectories, parse_bbox  # noqa: E402


def build_noisy_histogram(trajectories, bbox, grid, epsilon_anchor, seed):
    lat_min, lat_max, lon_min, lon_max = bbox
    span_lat = max(lat_max - lat_min, 1e-12)
    span_lon = max(lon_max - lon_min, 1e-12)
    hist = np.zeros((grid, grid), dtype=float)
    for idx, trajectory in enumerate(trajectories, start=1):
        arr = np.asarray(trajectory, dtype=float)
        if len(arr) < 2:
            continue
        cells = set()
        for lat, lon in arr[:, :2]:
            row = min(grid - 1, max(0, int((lat - lat_min) / span_lat * grid)))
            col = min(grid - 1, max(0, int((lon - lon_min) / span_lon * grid)))
            cells.add((row, col))
        mass = 1.0 / max(len(cells), 1)
        for row, col in cells:
            hist[row, col] += mass
        if idx % 2000 == 0:
            print(f"[anchor-audit] processed {idx:,}/{len(trajectories):,}", flush=True)
    rng = np.random.default_rng(seed)
    noisy = hist + rng.laplace(0.0, 1.0 / max(epsilon_anchor, 1e-12), size=hist.shape)
    return hist, noisy


def choose_cells(noisy, anchor_count):
    flat = np.argsort(noisy.ravel())[-anchor_count:][::-1]
    width = noisy.shape[1]
    return [(int(i // width), int(i % width)) for i in flat]


def coverage_diagnostics(trajectories, bbox, cells, grid):
    lat_min, lat_max, lon_min, lon_max = bbox
    span_lat = max(lat_max - lat_min, 1e-12)
    span_lon = max(lon_max - lon_min, 1e-12)
    selected = set(cells)
    point_total = point_hit = 0
    trajectory_total = trajectory_hit = 0
    latitudes = []
    for trajectory in trajectories:
        arr = np.asarray(trajectory, dtype=float)
        if len(arr) < 2:
            continue
        trajectory_total += 1
        hit_this = False
        for lat, lon in arr[:, :2]:
            row = min(grid - 1, max(0, int((lat - lat_min) / span_lat * grid)))
            col = min(grid - 1, max(0, int((lon - lon_min) / span_lon * grid)))
            hit = (row, col) in selected
            point_total += 1
            point_hit += int(hit)
            hit_this = hit_this or hit
            latitudes.append(float(lat))
        trajectory_hit += int(hit_this)
    selected_lat = [lat_min + (row + 0.5) / grid * span_lat for row, _ in cells]
    return {
        "raw_corpus_audit_only": True,
        "trajectory_count": trajectory_total,
        "point_count": point_total,
        "point_support_coverage": point_hit / max(point_total, 1),
        "trajectory_support_coverage": trajectory_hit / max(trajectory_total, 1),
        "point_latitude_min": min(latitudes) if latitudes else None,
        "point_latitude_max": max(latitudes) if latitudes else None,
        "selected_anchor_latitude_min": min(selected_lat) if selected_lat else None,
        "selected_anchor_latitude_max": max(selected_lat) if selected_lat else None,
        "selected_anchor_count_below_lat_39_95": sum(lat < 39.95 for lat in selected_lat),
        "selected_anchor_count_below_lat_40": sum(lat < 40.0 for lat in selected_lat),
    }


def plot_audit(trajectories, bbox, cells, grid, out_path):
    lat_min, lat_max, lon_min, lon_max = bbox
    fig, ax = plt.subplots(figsize=(8.5, 7.0), dpi=180)
    for trajectory in trajectories:
        arr = np.asarray(trajectory, dtype=float)
        if len(arr) >= 2:
            ax.plot(arr[:, 1], arr[:, 0], color="#6b7280", alpha=0.025, linewidth=0.25)
    for row, col in cells:
        y0 = lat_min + row / grid * (lat_max - lat_min)
        y1 = lat_min + (row + 1) / grid * (lat_max - lat_min)
        x0 = lon_min + col / grid * (lon_max - lon_min)
        x1 = lon_min + (col + 1) / grid * (lon_max - lon_min)
        ax.fill_between([x0, x1], y0, y1, color="#d94841", alpha=0.38, edgecolor="#8b1e1e", linewidth=0.45)
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("DP-GSRT anchor-support audit: noisy top-A cells")
    ax.grid(alpha=0.15, linewidth=0.4)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="geolife")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    parser.add_argument("--grid", type=int, default=20)
    parser.add_argument("--anchor-count", type=int, default=25)
    parser.add_argument("--epsilon-anchor", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="outputs/anchor_support_audit")
    args = parser.parse_args()
    if args.grid <= 0 or args.anchor_count <= 0 or args.anchor_count > args.grid * args.grid:
        raise SystemExit("grid and anchor-count must be positive, with anchor-count <= grid^2")
    bbox = parse_bbox(args.bbox)
    print(f"[anchor-audit] loading {args.data}", flush=True)
    trajectories = load_trajectories(args.data, limit=None)
    print(f"[anchor-audit] loaded {len(trajectories):,} trajectories", flush=True)
    _hist, noisy = build_noisy_histogram(trajectories, bbox, args.grid, args.epsilon_anchor, args.seed)
    cells = choose_cells(noisy, args.anchor_count)
    diag = coverage_diagnostics(trajectories, bbox, cells, args.grid)
    diag.update(
        {
            "dataset": args.data,
            "bbox": list(bbox),
            "grid": int(args.grid),
            "anchor_count": int(args.anchor_count),
            "epsilon_anchor": float(args.epsilon_anchor),
            "seed": int(args.seed),
            "selected_cells_row_col": [[r, c] for r, c in cells],
            "selected_noisy_scores": [float(noisy[r, c]) for r, c in cells],
            "public_dp_artifact_note": "Selected cells are post-processing of the noisy histogram; raw-corpus coverage fields are local research diagnostics only.",
        }
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"anchor_audit_A{args.anchor_count}_g{args.grid}_seed{args.seed}.json"
    png_path = out_dir / f"anchor_audit_A{args.anchor_count}_g{args.grid}_seed{args.seed}.png"
    json_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    plot_audit(trajectories, bbox, cells, args.grid, png_path)
    print(json.dumps({"json": str(json_path.resolve()), "figure": str(png_path.resolve()), "diagnostics": diag}, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

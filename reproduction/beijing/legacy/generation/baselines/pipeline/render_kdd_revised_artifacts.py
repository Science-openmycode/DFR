"""Render completed central-DP KDD tables and figures from frozen artifacts.

The central release benchmark is self-contained.  DPMM has a distinct
per-record interface and is rendered only when a complete official artifact
is explicitly supplied; partial checkpoints are never accepted.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
ARA = PUBLIC_RELEASE.parent
PAPER_DIRS = [ARA / "paper_latex" / "mod_paper_change"]

MAIN_ORDER = ["Real-vs-real calibration", "SPRT", "PrivTrace", "DPTraj-PM", "MTR/DP-GSRT"]
TASK_ORDER = ["Real-train", "SPRT", "PrivTrace", "DPTraj-PM", "MTR/DP-GSRT"]


def rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {row["method"]: row for row in csv.DictReader(f)}


def f(row: dict[str, str], key: str, digits: int = 3) -> str:
    value = float(row[key])
    return f"{value:.{digits}f}"


def display_name(name: str) -> str:
    return "MTR / DP-GSRT" if name == "MTR/DP-GSRT" else name


def require(data: dict[str, dict[str, str]], names: list[str], label: str) -> None:
    missing = [name for name in names if name not in data]
    if missing:
        raise RuntimeError(f"{label} is incomplete; missing rows: {missing}")


def write_text_all(name: str, content: str) -> None:
    for paper in PAPER_DIRS:
        (paper / name).write_text(content, encoding="utf-8")


def main_table(data: dict[str, dict[str, str]]) -> str:
    lines = [
        r"\begin{tabular}{lrrrrrrr}", r"\toprule",
        r"Method & Grid JSD$\downarrow$ & Trip Error$\downarrow$ & Path JSD$\downarrow$ & cNN-DTW$\downarrow$ & Road-seg. JSD$\downarrow$ & Directed validity$\uparrow$ & Route yield$\uparrow$\\",
        r"\midrule",
    ]
    for name in MAIN_ORDER:
        row = data[name]
        lines.append(
            f"{display_name(name)} & {f(row, 'grid_density_jsd')} & {f(row, 'trip_error')} & {f(row, 'path_length_jsd')} & {f(row, 'conditional_nn_dtw_km')} & {f(row, 'road_segment_jsd')} & {f(row, 'directed_road_validity')} & {f(row, 'route_compatible_yield')}\\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def task_table(data: dict[str, dict[str, str]]) -> str:
    keys = ["range_query_are", "next_road_hit_at_5", "route_popularity_hit_at_10", "route_popularity_ndcg_at_10", "trajectory_suffix_accuracy"]
    labels = [r"Range ARE$\downarrow$", r"Next-road Hit@5$\uparrow$", r"Route-pop. Hit@10$\uparrow$", r"Route-pop. NDCG@10$\uparrow$", r"Suffix acc.$\uparrow$"]
    lines = [r"\begin{tabular}{lrrrrr}", r"\toprule", "Method & " + " & ".join(labels) + r"\\", r"\midrule"]
    for name in TASK_ORDER:
        row = data[name]
        lines.append(display_name(name) + " & " + " & ".join(f(row, key) for key in keys) + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def dpmm_table(data: dict[str, dict[str, str]]) -> str:
    names = ["MTR/DP-GSRT", "DPMM (official)"]
    lines = [
        r"\begin{tabular}{lrrrrrrr}", r"\toprule",
        r"Method & Release/Input & Grid JSD$\downarrow$ & Trip error$\downarrow$ & Path JSD$\downarrow$ & Road-seg. JSD$\downarrow$ & Directed validity$\uparrow$ & Route-compatible yield$\uparrow$\\",
        r"\midrule",
    ]
    for name in names:
        row = data[name]
        ratio = f"{int(float(row['release_count'])):,}/{int(float(row['input_count'])):,}"
        lines.append(f"{name} & {ratio} & {f(row, 'grid_density_jsd')} & {f(row, 'trip_error')} & {f(row, 'path_length_jsd')} & {f(row, 'road_segment_jsd')} & {f(row, 'directed_road_validity')} & {f(row, 'route_compatible_yield')}\\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def calibration_figure(data: dict[str, dict[str, str]], output: Path) -> None:
    names = ["SPRT", "PrivTrace", "DPTraj-PM", "MTR/DP-GSRT"]
    metrics = [("grid_density_jsd", "Grid JSD"), ("trip_error", "Trip error"), ("path_length_jsd", "Path JSD"), ("road_segment_jsd", "Road-seg. JSD")]
    fig, axes = plt.subplots(1, 4, figsize=(12.6, 2.65), constrained_layout=True)
    colors = ["#c43c39", "#7b3294", "#8c510a", "#0a8e4e"]
    for ax, (key, label) in zip(axes, metrics):
        calibration = float(data["Real-vs-real calibration"][key])
        values = [float(data[name][key]) for name in names]
        ax.bar(np.arange(len(names)), values, color=colors, width=.72)
        ax.axhline(calibration, color="#164eb0", linewidth=1.6, linestyle="--", label="Real-vs-real")
        ax.set_title(label, fontsize=9)
        ax.set_xticks(np.arange(len(names)))
        ax.set_xticklabels(["SPRT", "PT", "DPM", "GSRT"], rotation=32, ha="right", fontsize=7)
        ax.grid(axis="y", color="#d9d9d9", linewidth=.5, alpha=.8)
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def copy_asset(source: Path, name: str) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    for paper in PAPER_DIRS:
        target = paper / "figures" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def plot(real: str, synthetic: list[Path], name: str, expected: int | None, output: Path, title: str) -> None:
    script = PUBLIC_RELEASE / "pipeline" / "plot_trajectory_panels.py"
    cmd = [sys.executable, str(script), "--real", real]
    for path in synthetic:
        cmd.extend(["--synthetic", str(path)])
    cmd += ["--display-count", "all", "--out-dir", str(output.parent), "--name", name, "--paper-figure2-style", "--title", title]
    if expected is not None:
        cmd += ["--strict-full-size", "--expected-count", str(expected)]
    subprocess.run(cmd, check=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-root", default=str(PUBLIC_RELEASE / "outputs" / "kdd_revised"))
    p.add_argument("--dpmm", default=None, help="optional complete official DPMM release for its separate appendix diagnostic")
    args = p.parse_args()
    out = Path(args.out_root).resolve()
    # The paper benchmark is intentionally wired to the certified native
    # baseline artifacts, rather than the old generic local adapters.
    main = rows(out / "final_release_evaluation" / "main_statistics.csv")
    task = rows(out / "final_release_evaluation" / "task_utility.csv")
    require(main, MAIN_ORDER, "main statistical table")
    require(task, TASK_ORDER, "task utility table")
    write_text_all("tables_kdd_revised_main_statistics.tex", main_table(main))
    write_text_all("tables_kdd_revised_task_utility.tex", task_table(task))
    figure_dir = out / "figures"; figure_dir.mkdir(parents=True, exist_ok=True)
    calibration_figure(main, figure_dir / "real_vs_real_calibration")
    current = PUBLIC_RELEASE / "outputs" / "synthetic_releases" / "current_best"
    plot(str(out / "split" / "real_full_frozen.pkl"), [current / "sprt_native.pkl", current / "privtrace_native.pkl", current / "dptrajpm_native.pkl", current / "mtr_dp_gsrt.pkl"], "beijing_published_vs_ara_map", 17123, figure_dir / "beijing_published_vs_ara_map", "Full-size Beijing release-object comparison")
    stems = ["beijing_published_vs_ara_map", "real_vs_real_calibration"]
    if args.dpmm:
        dpmm = Path(args.dpmm).resolve()
        if not dpmm.exists() or not dpmm.with_suffix(".json").exists():
            raise RuntimeError("DPMM diagnostic requires a complete release and manifest; partial checkpoints are rejected")
        if "DPMM (official)" not in main:
            raise RuntimeError("DPMM diagnostic requires a completed DPMM row in the source statistics CSV")
        write_text_all("tables_appendix_dpmm_official.tex", dpmm_table(main))
        plot("geolife", [dpmm, current / "mtr_dp_gsrt.pkl"], "dpmm_official_vs_mtr_beijing", None, figure_dir / "dpmm_official_vs_mtr_beijing", "DPMM official per-record release versus MTR")
        stems.append("dpmm_official_vs_mtr_beijing")
    for stem in stems:
        for suffix in [".png", ".pdf"]:
            copy_asset(figure_dir / f"{stem}{suffix}", f"{stem}{suffix}")
    print(f"[render] wrote completed central-DP tables and figures to {out}", flush=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import PUBLIC_ROOT, write_json


PATH_METRICS = ["MM-accept", "Strict-MM", "Sim-ready", "Route-ready"]
PATH_TABLE_COLUMNS = ["Method", *PATH_METRICS, "Usable trips", "Jump", "Road"]
METHOD_ORDER = [
    "Real full",
    "SPRT-native",
    "SPRT-OSM",
    "PrivTrace-native",
    "PrivTrace-OSM",
    "DPTraj-PM-native",
    "DPTraj-PM-OSM",
    "DPStd-native",
    "DPStd-OSM",
    "MTR / DP-GSRT",
]
METHOD_COLORS = {
    "Real full": "#164EB0",
    "MTR / DP-GSRT": "#0A8E4E",
    "SPRT-native": "#C43C39",
    "SPRT-OSM": "#F18F01",
    "PrivTrace-native": "#7B3294",
    "PrivTrace-OSM": "#B358B2",
    "DPTraj-PM-native": "#8C510A",
    "DPTraj-PM-OSM": "#BF812D",
    "DPStd-native": "#4D4D4D",
    "DPStd-OSM": "#878787",
}
BACKGROUND = "#FCFCFA"


def log(message: str) -> None:
    print(f"[downstream-plot] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Create paper-ready downstream-task tables and figures from already "
            "computed downstream CSV files. If the CSV directory is partial, the "
            "script can fall back to the bundled paper table snapshot."
        )
    )
    p.add_argument("--downstream-dir", default=str(PUBLIC_ROOT / "outputs" / "downstream_tasks_full"))
    p.add_argument("--fallback-path-table", default=str(PUBLIC_ROOT / "paper_latex" / "tables_kdd_path_facing_downstream.tex"))
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "downstream_figures"))
    p.add_argument("--paper-fig-dir", default=str(PUBLIC_ROOT / "paper_latex" / "figures"))
    p.add_argument("--paper-table-dir", default=str(PUBLIC_ROOT / "paper_latex"))
    p.add_argument("--name-prefix", default="downstream_path")
    p.add_argument("--min-methods", type=int, default=3)
    p.add_argument("--copy-to-paper", action="store_true")
    return p


def clean_method(name: str) -> str:
    stem = Path(str(name)).stem
    s = stem
    for prefix in ["geolife_", "beijing_", "porto_", "oldenburg_"]:
        if s.startswith(prefix):
            s = s[len(prefix) :]
    s = re.sub(r"_s\d+$", "", s)
    s = s.replace("_full", "")
    s = re.sub(r"_20k$", "", s)
    mapping = {
        "sprt_native": "SPRT-native",
        "sprt_osm": "SPRT-OSM",
        "privtrace_native": "PrivTrace-native",
        "privtrace_osm": "PrivTrace-OSM",
        "dptrajpm_native": "DPTraj-PM-native",
        "dptrajpm_osm": "DPTraj-PM-OSM",
        "dpstd_native": "DPStd-native",
        "dpstd_osm": "DPStd-OSM",
        "dp_gsrt": "MTR / DP-GSRT",
        "ara_dp_gsrt": "MTR / DP-GSRT",
        "mtr_dp_gsrt": "MTR / DP-GSRT",
    }
    return mapping.get(s.lower().replace("-", "_"), name)


def method_sort_key(row: dict) -> tuple[int, str]:
    name = str(row["Method"])
    try:
        return (METHOD_ORDER.index(name), name)
    except ValueError:
        return (len(METHOD_ORDER), name.lower())


def load_path_rows_from_csv(downstream_dir: Path) -> list[dict]:
    mm = downstream_dir / "map_matching.csv"
    rr = downstream_dir / "route_recovery.csv"
    sim = downstream_dir / "simulation.csv"
    if not (mm.exists() and rr.exists() and sim.exists()):
        return []

    def read_by_method(path: Path) -> dict[str, dict]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        out = {}
        for row in rows:
            out[clean_method(row["method"])] = row
        return out

    mm_rows = read_by_method(mm)
    rr_rows = read_by_method(rr)
    sim_rows = read_by_method(sim)
    methods = sorted(set(mm_rows) | set(rr_rows) | set(sim_rows))
    out = []
    manifest = downstream_dir / "downstream_manifest.json"
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            real = payload.get("real_summary", {})
            if real:
                out.append(
                    {
                        "Method": "Real full",
                        "MM-accept": float(real.get("map_matching", {}).get("accept_rate", 0.0)),
                        "Strict-MM": float(real.get("strict_map_matching", {}).get("accept_rate", 0.0)),
                        "Sim-ready": float(real.get("simulation", {}).get("accept_rate", 0.0)),
                        "Route-ready": float(real.get("route_recovery", {}).get("accept_rate", 0.0)),
                        "Usable trips": int(real.get("route_recovery", {}).get("n_accepted", 0)),
                        "Jump": float(real.get("map_matching", {}).get("jump2_mean", 0.0)),
                        "Road": float(real.get("map_matching", {}).get("road200_mean", 0.0)),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            log(f"warning: could not read real summary from {manifest}: {exc!r}")
    for method in methods:
        a = mm_rows.get(method, {})
        b = rr_rows.get(method, {})
        c = sim_rows.get(method, {})
        row = {
            "Method": method,
            "MM-accept": float(a.get("accept_rate", 0.0) or 0.0),
            "Strict-MM": float(a.get("strict_accept_rate", 0.0) or 0.0),
            "Sim-ready": float(c.get("accept_rate", 0.0) or 0.0),
            "Route-ready": float(b.get("accept_rate", 0.0) or 0.0),
            "Usable trips": int(float(b.get("n_accepted", 0.0) or 0.0)),
            "Jump": float(a.get("jump2_mean", b.get("jump2_mean", 0.0)) or 0.0),
            "Road": float(a.get("road200_mean", b.get("road200_mean", 0.0)) or 0.0),
        }
        out.append(row)
    return sorted(out, key=method_sort_key)


def parse_latex_path_table(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if "&" not in line or line.startswith(("Method", "\\", "%")):
            continue
        line = line.rstrip("\\").strip()
        parts = [p.strip() for p in line.split("&")]
        if len(parts) != len(PATH_TABLE_COLUMNS):
            continue
        row = {"Method": parts[0]}
        for key, val in zip(PATH_TABLE_COLUMNS[1:], parts[1:]):
            val = val.replace(",", "")
            row[key] = int(val) if key == "Usable trips" else float(val)
        rows.append(row)
    return sorted(rows, key=method_sort_key)


def write_path_latex_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"Method & MM-accept & Strict-MM & Sim-ready & Route-ready & Usable trips & Jump & Road \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            (
                f"{row['Method']} & {row['MM-accept']:.3f} & {row['Strict-MM']:.3f} & "
                f"{row['Sim-ready']:.3f} & {row['Route-ready']:.3f} & "
                f"{int(row['Usable trips']):,} & {row['Jump']:.3f} & {row['Road']:.3f} \\\\"
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def savefig(fig, out_dir: Path, stem: str, copy_to: Path | None = None) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    pdf = out_dir / f"{stem}.pdf"
    log(f"saving {png}")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    log(f"saving {pdf}")
    fig.savefig(pdf, bbox_inches="tight")
    copied = {}
    if copy_to is not None:
        copy_to.mkdir(parents=True, exist_ok=True)
        c_png = copy_to / png.name
        c_pdf = copy_to / pdf.name
        c_png.write_bytes(png.read_bytes())
        c_pdf.write_bytes(pdf.read_bytes())
        copied = {"paper_png": str(c_png.resolve()), "paper_pdf": str(c_pdf.resolve())}
    return {"png": str(png.resolve()), "pdf": str(pdf.resolve()), **copied}


def plot_admission(rows: list[dict], out_dir: Path, prefix: str, paper_dir: Path | None) -> dict[str, str]:
    methods = [row["Method"] for row in rows]
    y = np.arange(len(methods))
    offsets = np.linspace(-0.27, 0.27, len(PATH_METRICS))
    height = 0.15
    fig, ax = plt.subplots(figsize=(8.8, max(4.8, 0.43 * len(methods) + 1.4)))
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    palette = ["#2C7BB6", "#00A6A6", "#7FC97F", "#0A8E4E"]
    for metric, off, color in zip(PATH_METRICS, offsets, palette):
        vals = [float(row[metric]) for row in rows]
        ax.barh(y + off, vals, height=height, label=metric, color=color, alpha=0.92)
    ax.set_yticks(y)
    ax.set_yticklabels(methods, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.05)
    ax.set_xlabel("Admission rate")
    ax.set_title("Path-facing downstream admission", fontweight="bold", fontsize=12, pad=10)
    ax.grid(axis="x", color="#DADDE2", lw=0.7, alpha=0.8)
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.20), frameon=False, fontsize=8.2)
    for i, method in enumerate(methods):
        if method == "MTR / DP-GSRT":
            ax.axhspan(i - 0.43, i + 0.43, color="#0A8E4E", alpha=0.075, zorder=0)
        elif method == "Real full":
            ax.axhspan(i - 0.43, i + 0.43, color="#164EB0", alpha=0.06, zorder=0)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    fig.text(0.5, 0.025, "Full Beijing releases; all rates are higher-is-better.", ha="center", fontsize=8.5)
    fig.tight_layout(rect=(0.0, 0.08, 1.0, 1.0))
    outputs = savefig(fig, out_dir, f"{prefix}_admission_rates", paper_dir)
    plt.close(fig)
    return outputs


def plot_jump_road(rows: list[dict], out_dir: Path, prefix: str, paper_dir: Path | None) -> dict[str, str]:
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    label_offsets = {
        "Real full": (6, 8),
        "MTR / DP-GSRT": (8, -18),
        "SPRT-native": (8, -10),
        "SPRT-OSM": (-8, 10),
        "PrivTrace-native": (8, -12),
        "PrivTrace-OSM": (8, 8),
        "DPTraj-PM-native": (8, 8),
        "DPTraj-PM-OSM": (8, 10),
        "DPStd-native": (8, -13),
        "DPStd-OSM": (8, 9),
    }
    label_alias = {
        "Real full": "Real",
        "MTR / DP-GSRT": "MTR/DP-GSRT",
        "DPTraj-PM-native": "DPTrajPM-native",
        "DPTraj-PM-OSM": "DPTrajPM-OSM",
    }
    for row in rows:
        method = row["Method"]
        color = METHOD_COLORS.get(method, "#777777")
        size = 92 if method in {"Real full", "MTR / DP-GSRT"} else 56
        marker = "*" if method == "MTR / DP-GSRT" else ("D" if method == "Real full" else "o")
        ax.scatter(row["Jump"], row["Road"], s=size, color=color, marker=marker, edgecolor="white", linewidth=0.8, zorder=3)
        ax.annotate(
            label_alias.get(method, method),
            (row["Jump"], row["Road"]),
            xytext=label_offsets.get(method, (5, 2)),
            textcoords="offset points",
            fontsize=7.2,
        )
    ax.set_xlabel("Jump rate (>2km), lower is better")
    ax.set_ylabel("Road proximity within 200m, higher is better")
    ax.set_title("Road proximity alone does not imply usable paths", fontweight="bold", fontsize=12, pad=10)
    ax.grid(color="#DADDE2", lw=0.7, alpha=0.8)
    ax.set_xlim(-0.02, 1.05)
    ax.set_ylim(0.93, 1.015)
    ax.axvspan(0.0, 0.03, color="#0A8E4E", alpha=0.07, zorder=0)
    ax.axhspan(0.95, 1.015, color="#164EB0", alpha=0.045, zorder=0)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    outputs = savefig(fig, out_dir, f"{prefix}_jump_vs_road", paper_dir)
    plt.close(fig)
    return outputs


def main() -> None:
    args = build_parser().parse_args()
    downstream_dir = Path(args.downstream_dir)
    if not downstream_dir.is_absolute():
        downstream_dir = Path.cwd() / downstream_dir
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    paper_fig_dir = Path(args.paper_fig_dir)
    if not paper_fig_dir.is_absolute():
        paper_fig_dir = Path.cwd() / paper_fig_dir
    paper_table_dir = Path(args.paper_table_dir)
    if not paper_table_dir.is_absolute():
        paper_table_dir = Path.cwd() / paper_table_dir

    log(f"loading downstream CSVs from {downstream_dir}")
    rows = load_path_rows_from_csv(downstream_dir)
    source = "downstream_csv"
    if len(rows) < args.min_methods:
        fallback = Path(args.fallback_path_table)
        if not fallback.is_absolute():
            fallback = Path.cwd() / fallback
        log(f"CSV result has only {len(rows)} method(s); falling back to {fallback}")
        rows = parse_latex_path_table(fallback)
        source = "fallback_latex_snapshot"
    if not rows:
        raise RuntimeError("no downstream rows available for plotting")
    log(f"plotting {len(rows)} method row(s) from {source}")

    table_out = out_dir / f"{args.name_prefix}_summary.tex"
    write_path_latex_table(table_out, rows)
    paper_table_out = None
    if args.copy_to_paper:
        paper_table_out = paper_table_dir / f"tables_{args.name_prefix}_summary.tex"
        write_path_latex_table(paper_table_out, rows)

    paper_dir = paper_fig_dir if args.copy_to_paper else None
    outputs = {
        "admission": plot_admission(rows, out_dir, args.name_prefix, paper_dir),
        "jump_vs_road": plot_jump_road(rows, out_dir, args.name_prefix, paper_dir),
        "table": str(table_out.resolve()),
    }
    if paper_table_out is not None:
        outputs["paper_table"] = str(paper_table_out.resolve())
    manifest = {
        "command_role": "plot_downstream_results",
        "source": source,
        "downstream_dir": str(downstream_dir.resolve()),
        "method_count": len(rows),
        "methods": [row["Method"] for row in rows],
        "outputs": outputs,
    }
    write_json(out_dir / f"{args.name_prefix}_manifest.json", manifest)
    log(f"wrote manifest {out_dir / f'{args.name_prefix}_manifest.json'}")


if __name__ == "__main__":
    main()

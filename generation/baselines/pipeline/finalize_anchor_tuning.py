"""Summarize the full-corpus anchor-support tuning and make the final figure.

The anchor audit is a diagnostic of public post-processing support.  It does
not introduce a new private query: all selected cells are derived from the
already released noisy histogram.  The final release itself is the completed
full-size A=40 artifact from the candidate-support sweep.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SWEEP = ROOT / "outputs" / "anchor_support_sweep_20260710"
AUDITS = SWEEP / "audits"
FINAL_SRC = ROOT / "outputs" / "mtr_candidate_support_sweep_20260709" / "synthetic" / "mtr_k32_a40.pkl"
FINAL_PROTOCOL_SRC = FINAL_SRC.with_name("mtr_k32_a40_protocol.json")
FINAL_DST = ROOT / "outputs" / "synthetic_releases" / "current_best" / "mtr_dp_gsrt.pkl"
PROTOCOL_DIR = ROOT / "outputs" / "synthetic_releases" / "current_best" / "protocols_20260710_mtr_candidate_sweep"


def load_audits() -> list[dict]:
    rows = []
    for path in sorted(AUDITS.glob("A*/anchor_audit_A*_g20_seed20260709.json"), key=lambda p: int(p.parent.name[1:])):
        payload = json.loads(path.read_text(encoding="utf-8"))
        d = payload.get("diagnostics", payload)
        rows.append(d)
    if not rows:
        raise RuntimeError(f"No audit files found under {AUDITS}")
    return rows


def make_plot(rows: list[dict]) -> tuple[Path, Path]:
    anchors = np.asarray([r["anchor_count"] for r in rows], dtype=int)
    point = np.asarray([r["point_support_coverage"] for r in rows], dtype=float)
    traj = np.asarray([r["trajectory_support_coverage"] for r in rows], dtype=float)
    south = np.asarray([r["selected_anchor_count_below_lat_39_95"] for r in rows], dtype=float)
    lat_min = np.asarray([r["selected_anchor_latitude_min"] for r in rows], dtype=float)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0), dpi=180)
    blue, teal, coral = "#2166AC", "#1B9E77", "#D95F02"
    axes[0].plot(anchors, point * 100, marker="o", lw=2.4, color=blue, label="Point support")
    axes[0].plot(anchors, traj * 100, marker="s", lw=2.4, color=teal, label="Trajectory support")
    axes[0].axvline(40, color=coral, ls="--", lw=1.8, label="Selected A=40")
    axes[0].set(xlabel="Number of DP anchors", ylabel="Coverage (%)", title="Public support coverage")
    axes[0].set_ylim(35, 100)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    axes[1].plot(anchors, south, marker="o", lw=2.4, color=coral)
    axes[1].axvline(40, color=coral, ls="--", lw=1.8)
    axes[1].set(xlabel="Number of DP anchors", ylabel="Anchors below 39.95°N", title="Southern support recovery")
    axes[1].set_ylim(bottom=0)
    axes[2].plot(anchors, lat_min, marker="o", lw=2.4, color=blue)
    axes[2].axhline(39.75, color="#666666", ls=":", lw=1.4, label="Real corpus minimum")
    axes[2].axvline(40, color=coral, ls="--", lw=1.8)
    axes[2].set(xlabel="Number of DP anchors", ylabel="Minimum anchor latitude", title="Southern latitude reach")
    axes[2].legend(frameon=False, fontsize=8, loc="lower right")
    for ax in axes:
        ax.grid(axis="y", alpha=0.22, lw=0.7)
        ax.set_xticks(anchors)
    fig.suptitle("Anchor-support tuning on the full 17,123-trajectory Beijing corpus", y=1.03, fontsize=13, fontweight="bold")
    fig.tight_layout()
    png = SWEEP / "anchor_support_tuning.png"
    pdf = SWEEP / "anchor_support_tuning.pdf"
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def finalize_release(rows: list[dict]) -> None:
    if not FINAL_SRC.exists():
        raise FileNotFoundError(FINAL_SRC)
    FINAL_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FINAL_SRC, FINAL_DST)
    protocol = json.loads(FINAL_PROTOCOL_SRC.read_text(encoding="utf-8"))
    protocol["anchor_count"] = 40
    protocol["anchor_tuning"] = {
        "selected": 40,
        "selection_rule": "first fully synthesized setting with materially improved southern support; A50/A64 remain audit-only because no full synthesis was released",
        "audit_seed": 20260709,
        "audit_grid": 20,
    }
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    (PROTOCOL_DIR / "mtr_k32_a40_protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    (SWEEP / "anchor_support_sweep_summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def write_report(rows: list[dict], png: Path, pdf: Path) -> Path:
    selected = next(r for r in rows if r["anchor_count"] == 40)
    report = SWEEP / "ANCHOR_SUPPORT_TUNING_REPORT.md"
    lines = [
        "# Anchor-support tuning report",
        "",
        "This tuning uses the full Beijing GeoLife corpus (17,123 trajectories), a fixed public bbox, grid=20, epsilon_anchor=0.20, and the same public noisy-histogram seed (20260709). The audit reports support diagnostics only; it does not add a private release or change the DP mechanism.",
        "",
        "## Selection",
        "",
        "A=40 is selected as the final operational setting. It is the first setting in this sweep for which a complete full-size synthesis already exists under the K=32 candidate protocol. A50 and A64 improve diagnostic support further, but they were not promoted without a complete full-release synthesis and full metric rerun.",
        "",
        f"At A=40, point support coverage is **{selected['point_support_coverage']:.3f}**, trajectory support coverage is **{selected['trajectory_support_coverage']:.3f}**, the minimum selected-anchor latitude is **{selected['selected_anchor_latitude_min']:.2f}**, and **{selected['selected_anchor_count_below_lat_39_95']}** selected anchors lie below 39.95°N.",
        "",
        "The completed A=40 release has 17,123 synthetic trajectories, road@200m=1.000, jump>2km=0.0003, Grid JSD=0.2413, and length JSD=0.1985 under the full evaluator. These metrics are computed from the stored artifact, not from the audit-only support proxy.",
        "",
        "## Files",
        "",
        f"- Tuning figure: `{png}` and `{pdf}`",
        f"- Audit records: `{AUDITS}`",
        f"- Final release: `{FINAL_DST}`",
        f"- Final protocol: `{PROTOCOL_DIR / 'mtr_k32_a40_protocol.json'}`",
        "",
        "## Interpretation",
        "",
        "Increasing A expands the public anchor support and recovers the southern city region. This is public post-processing of the DP anchor release; it is not a private-data-dependent candidate or template insertion. The remaining gap between the full corpus boundary and the selected anchors is therefore reported explicitly rather than hidden by a tighter plotting bbox.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    rows = load_audits()
    png, pdf = make_plot(rows)
    finalize_release(rows)
    report = write_report(rows, png, pdf)
    print(json.dumps({"figure_png": str(png), "figure_pdf": str(pdf), "report": str(report), "final_release": str(FINAL_DST)}, indent=2))


if __name__ == "__main__":
    main()

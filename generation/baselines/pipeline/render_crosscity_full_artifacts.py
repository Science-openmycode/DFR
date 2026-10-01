"""Render the independently regenerated Porto/SF full-corpus evidence.

The script consumes only completed per-city evaluator CSV files.  It never
uses historical internal numbers or mixes city-specific OSM graphs.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
ARA = PUBLIC_RELEASE.parent
PAPERS = [
    ARA / "paper_latex" / "mod_paper",
    ARA / "paper_latex" / "mod_paper_zh",
    ARA / "paper_latex" / "mod_paper_change",
]
ORDER = ["SPRT", "PrivTrace", "DPTraj-PM", "MTR-public-only", "MTR/DP-GSRT"]


def read(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def render(city_rows: list[tuple[str, dict[str, dict[str, str]]]]) -> str:
    lines = [
        r"\begin{tabular}{llrrrrr}", r"\toprule",
        r"City & Method & Grid JSD$\downarrow$ & Trip error$\downarrow$ & Path JSD$\downarrow$ & Road-seg. JSD$\downarrow$ & Directed validity$\uparrow$\\",
        r"\midrule",
    ]
    for city, rows in city_rows:
        for method in ORDER:
            row = rows[method]
            lines.append(
                f"{city} & {method} & {float(row['grid_density_jsd']):.3f} & "
                f"{float(row['trip_error']):.3f} & {float(row['path_length_jsd']):.3f} & "
                f"{float(row['road_segment_jsd']):.3f} & {float(row['directed_road_validity']):.3f}\\\\"
            )
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(PUBLIC_RELEASE / "outputs" / "kdd_revised" / "crosscity_full"))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    city_rows = []
    for tag, label in [("porto", "Porto"), ("sf", "San Francisco")]:
        path = root / tag / "statistics" / "main_statistics.csv"
        rows = read(path)
        missing = [method for method in ORDER if method not in rows]
        if missing:
            raise RuntimeError(f"{tag} evaluator is incomplete: {missing}")
        city_rows.append((label, rows))
    text = render(city_rows)
    for paper in PAPERS:
        (paper / "tables_crosscity_full.tex").write_text(text, encoding="utf-8")
        figures = paper / "figures"; figures.mkdir(exist_ok=True)
        for tag in ["porto", "sf"]:
            source = root / tag / "figures" / f"{tag}_full_release_comparison.png"
            if not source.exists():
                raise FileNotFoundError(source)
            shutil.copy2(source, figures / source.name)
    print(f"[crosscity-render] wrote complete Porto/SF evidence from {root}", flush=True)


if __name__ == "__main__":
    main()

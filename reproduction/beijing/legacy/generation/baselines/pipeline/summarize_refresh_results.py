from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DISPLAY = {
    "geolife_sprt_native_full": "SPRT-native",
    "geolife_sprt_osm_full": "SPRT-OSM",
    "geolife_privtrace_native_full": "PrivTrace-native",
    "geolife_privtrace_osm_full": "PrivTrace-OSM",
    "geolife_dptrajpm_native_full": "DPTraj-PM-native",
    "geolife_dptrajpm_osm_full": "DPTraj-PM-OSM",
    "geolife_dpstd_native_full": "DPStd-native",
    "geolife_dpstd_osm_full": "DPStd-OSM",
    "geolife_dp_gsrt_full": "MTR / DP-GSRT",
    "porto_sprt_native_20k": "SPRT-native",
    "porto_sprt_osm_20k": "SPRT-OSM",
    "porto_privtrace_native_20k": "PrivTrace-native",
    "porto_privtrace_osm_20k": "PrivTrace-OSM",
    "porto_dptrajpm_native_20k": "DPTraj-PM-native",
    "porto_dptrajpm_osm_20k": "DPTraj-PM-OSM",
    "porto_dpstd_native_20k": "DPStd-native",
    "porto_dpstd_osm_20k": "DPStd-OSM",
    "porto_dp_gsrt_20k": "MTR / DP-GSRT",
}

ORDER = [
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


def sort_key(row: dict) -> tuple[int, str]:
    name = row["display"]
    return (ORDER.index(name) if name in ORDER else len(ORDER), name)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        method = row["method"]
        row["display"] = DISPLAY.get(method, method)
        for key, value in list(row.items()):
            if key in {"method", "display", "synthetic_file", "real"}:
                continue
            try:
                row[key] = float(value)
            except ValueError:
                pass
        out.append(row)
    return sorted(out, key=sort_key)


def write_metrics_table(rows: list[dict], path: Path) -> None:
    lines = [
        r"\begin{tabular}{lrrrrrrrrr}",
        r"\toprule",
        r"Method & JS & OD & Len & J1 & J2 & R100 & R200 & Dist & Step \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            (
                f"{r['display']} & {r['grid_occupancy_jsd']:.3f} & {r['od_jsd']:.3f} & "
                f"{r['length_jsd']:.3f} & {r['jump_gt1km']:.3f} & {r['jump_gt2km']:.3f} & "
                f"{r['road_100m']:.3f} & {r['road_200m']:.3f} & {r['road_mean_dist_km']:.3f} & "
                f"{r['step_mean_km']:.3f} \\\\"
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_compact_claims(rows: list[dict], path: Path) -> None:
    by_name = {r["display"]: r for r in rows}
    mtr = by_name.get("MTR / DP-GSRT")
    best_baseline_jump = min((r for r in rows if r["display"] != "MTR / DP-GSRT"), key=lambda r: r["jump_gt2km"])
    best_baseline_road = max((r for r in rows if r["display"] != "MTR / DP-GSRT"), key=lambda r: r["road_200m"])
    payload = {
        "mtr_jump_gt2km": mtr["jump_gt2km"] if mtr else None,
        "mtr_road_200m": mtr["road_200m"] if mtr else None,
        "mtr_grid_jsd": mtr["grid_occupancy_jsd"] if mtr else None,
        "best_baseline_jump": {"method": best_baseline_jump["display"], "value": best_baseline_jump["jump_gt2km"]},
        "best_baseline_road": {"method": best_baseline_road["display"], "value": best_baseline_road["road_200m"]},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics-csv", required=True)
    p.add_argument("--paper-dir", default="paper_latex")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--table-name", default="tables_kdd_full_release_road_metrics.tex")
    args = p.parse_args()
    metrics_csv = Path(args.metrics_csv)
    paper_dir = Path(args.paper_dir)
    out_dir = Path(args.out_dir) if args.out_dir else metrics_csv.parent
    rows = read_csv(metrics_csv)
    table_path = paper_dir / args.table_name
    write_metrics_table(rows, table_path)
    write_compact_claims(rows, out_dir / "refresh_claims.json")
    print(table_path)
    print(out_dir / "refresh_claims.json")


if __name__ == "__main__":
    main()

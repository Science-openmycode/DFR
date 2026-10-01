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
    "sf_sprt_native_full": "SPRT-native",
    "sf_sprt_osm_full": "SPRT-OSM",
    "sf_privtrace_native_full": "PrivTrace-native",
    "sf_privtrace_osm_full": "PrivTrace-OSM",
    "sf_dptrajpm_native_full": "DPTraj-PM-native",
    "sf_dptrajpm_osm_full": "DPTraj-PM-OSM",
    "sf_dpstd_native_full": "DPStd-native",
    "sf_dpstd_osm_full": "DPStd-OSM",
    "sf_dp_gsrt_full": "MTR / DP-GSRT",
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


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict, key: str) -> float:
    return float(row[key])


def i(row: dict, key: str) -> int:
    return int(float(row[key]))


def add_dataset(rows: list[dict], dataset: str, metrics_csv: Path, downstream_csv: Path) -> None:
    metrics = read_csv(metrics_csv)
    downstream = {r["method"]: r for r in read_csv(downstream_csv)}
    for m in metrics:
        method = m["method"]
        d = downstream.get(method, {})
        display = DISPLAY.get(method, method)
        rows.append(
            {
                "dataset": dataset,
                "method": display,
                "source_method": method,
                "n": i(m, "n_traj"),
                "js": f(m, "grid_occupancy_jsd"),
                "od": f(m, "od_jsd"),
                "len": f(m, "length_jsd"),
                "j2": f(m, "jump_gt2km"),
                "r200": f(m, "road_200m"),
                "step": f(m, "step_mean_km"),
                "route_ready": float(d.get("accept_rate", 0.0)),
                "usable": int(float(d.get("n_accepted", 0))),
            }
        )


def sort_key(row: dict) -> tuple[str, int, str]:
    method = row["method"]
    return (row["dataset"], ORDER.index(method) if method in ORDER else 99, method)


def write_tex(rows: list[dict], path: Path) -> None:
    lines = [
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Dataset & Method & $n$ & J2 & R200 & Len & Route-ready & Usable \\",
        r"\midrule",
    ]
    for r in sorted(rows, key=sort_key):
        lines.append(
            f"{r['dataset']} & {r['method']} & {int(r['n']):,} & {r['j2']:.3f} & "
            f"{r['r200']:.3f} & {r['len']:.3f} & {r['route_ready']:.3f} & {int(r['usable']):,} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--beijing-metrics", required=True)
    p.add_argument("--beijing-downstream", required=True)
    p.add_argument("--porto-metrics", required=True)
    p.add_argument("--porto-downstream", required=True)
    p.add_argument("--sf-metrics")
    p.add_argument("--sf-downstream")
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-tex", required=True)
    args = p.parse_args()

    rows: list[dict] = []
    add_dataset(rows, "Beijing full", Path(args.beijing_metrics), Path(args.beijing_downstream))
    add_dataset(rows, "Porto 20k", Path(args.porto_metrics), Path(args.porto_downstream))
    if args.sf_metrics and args.sf_downstream:
        add_dataset(rows, "SF CabSpotting", Path(args.sf_metrics), Path(args.sf_downstream))
    rows = sorted(rows, key=sort_key)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_tex(rows, Path(args.out_tex))
    print(out_json)
    print(args.out_tex)


if __name__ == "__main__":
    main()

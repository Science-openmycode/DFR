from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
PIPELINE_DIR = Path(__file__).resolve().parent
for path in [PUBLIC_RELEASE, PIPELINE_DIR]:
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

from public_utils import filter_osm_ways_by_bbox, jsonable, load_osm_ways, load_trajectories, write_json

_DS_SPEC = importlib.util.spec_from_file_location("pipeline_evaluate_downstream", PIPELINE_DIR / "evaluate_downstream.py")
if _DS_SPEC is None or _DS_SPEC.loader is None:
    raise RuntimeError("cannot load pipeline/evaluate_downstream.py")
ds = importlib.util.module_from_spec(_DS_SPEC)
_DS_SPEC.loader.exec_module(ds)


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


def log(message: str) -> None:
    print(f"[robustness] {time.strftime('%H:%M:%S')} {message}", flush=True)


def discover_synthetic(paths: list[str], synthetic_dir: str | None) -> list[Path]:
    found = [Path(p) for p in paths]
    if synthetic_dir:
        root = Path(synthetic_dir)
        if not root.is_absolute():
            root = Path.cwd() / root
        for suffix in ["*.npz", "*.pkl", "*.pickle", "*.npy"]:
            found.extend(sorted(root.glob(suffix)))
    by_stem: dict[str, Path] = {}
    priority = {".npz": 0, ".pkl": 1, ".pickle": 1, ".npy": 2}
    for path in found:
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            continue
        key = str(path.with_suffix(""))
        prev = by_stem.get(key)
        if prev is None or priority.get(path.suffix.lower(), 9) < priority.get(prev.suffix.lower(), 9):
            by_stem[key] = path
    out = sorted(by_stem.values())
    if not out:
        raise RuntimeError("provide existing --synthetic and/or --synthetic-dir")
    return out


def bootstrap_rate(mask: np.ndarray, rng: np.random.Generator, draws: int) -> dict:
    n = int(mask.size)
    if n == 0:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    vals = np.empty(draws, dtype=float)
    for i in range(draws):
        idx = rng.integers(0, n, size=n)
        vals[i] = float(np.mean(mask[idx]))
    return {
        "mean": float(np.mean(mask)),
        "ci_low": float(np.percentile(vals, 2.5)),
        "ci_high": float(np.percentile(vals, 97.5)),
        "n": n,
    }


def threshold_accept(rows: list[dict], road_km: float, jump_km: float, max_jump_share: float) -> np.ndarray:
    return np.asarray(
        [
            r["road_mean_dist_km"] <= road_km
            or (r["road200_share"] >= 0.95 and r["jump2_share"] <= max_jump_share and r["max_step_km"] <= jump_km)
            for r in rows
        ],
        dtype=bool,
    )


def route_ready_mask(rows: list[dict], road_min: float = 0.95, jump2_max: float = 0.02) -> np.ndarray:
    return np.asarray(
        [
            r["road200_share"] >= road_min
            and r["jump2_share"] <= jump2_max
            and r["n_points"] >= 8
            and 1.05 <= r["stretch"] <= 25.0
            for r in rows
        ],
        dtype=bool,
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({k for row in rows for k in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: jsonable(v) for k, v in row.items()} for row in rows])


def write_ci_table(rows: list[dict], path: Path) -> None:
    rows = sorted(rows, key=lambda r: (ORDER.index(r["display"]) if r["display"] in ORDER else 99, r["display"]))
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Method & Route-ready & 95\% CI low & 95\% CI high & $n$ \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            f"{r['display']} & {r['route_ready_mean']:.3f} & {r['ci_low']:.3f} & {r['ci_high']:.3f} & {int(r['n']):,} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_threshold_table(rows: list[dict], path: Path) -> None:
    focus = [r for r in rows if r["road_min"] in {0.90, 0.95, 0.98} and r["jump2_max"] in {0.01, 0.02, 0.05}]
    focus = sorted(
        focus,
        key=lambda r: (
            ORDER.index(r["display"]) if r["display"] in ORDER else 99,
            r["road_min"],
            r["jump2_max"],
        ),
    )
    lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Method & Road-min & Jump2-max & Route-ready \\",
        r"\midrule",
    ]
    for r in focus:
        lines.append(f"{r['display']} & {r['road_min']:.2f} & {r['jump2_max']:.2f} & {r['accept_rate']:.3f} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--real", default="geolife")
    p.add_argument("--real-limit", type=int, default=None)
    p.add_argument("--synthetic", action="append", default=[])
    p.add_argument("--synthetic-dir", default=None)
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--paper-dir", default=None)
    p.add_argument("--table-prefix", default="tables_kdd_robustness")
    p.add_argument("--bootstrap-draws", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20260705)
    p.add_argument("--road-sample-step-km", type=float, default=0.08)
    args = p.parse_args()

    t0 = time.time()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    log(f"loading real trajectories from {args.real}")
    real = load_trajectories(args.real, limit=args.real_limit)
    lat0 = float(np.mean(np.vstack([t[[0, -1]] for t in real if len(t) >= 2])[:, 0]))
    log(f"loading OSM cache from {args.osm_cache}")
    bbox = ds.full_bbox(real)
    osm_ways_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
    log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")
    road_samples = ds.sample_osm_points(osm_ways, lat0, args.road_sample_step_km)
    road_tree = cKDTree(ds.latlon_to_xy(road_samples, lat0))
    syn_files = discover_synthetic(args.synthetic, args.synthetic_dir)

    ci_rows: list[dict] = []
    threshold_rows: list[dict] = []
    for i, syn_path in enumerate(syn_files, start=1):
        log(f"[{i}/{len(syn_files)}] loading {syn_path.name}")
        syn = load_trajectories(str(syn_path), limit=None)
        log(f"[{i}/{len(syn_files)}] computing per-trajectory quality")
        rows = ds.traj_quality(syn, road_tree, lat0)
        display = DISPLAY.get(syn_path.stem, syn_path.stem)
        mask = route_ready_mask(rows)
        ci = bootstrap_rate(mask, rng, args.bootstrap_draws)
        ci_rows.append(
            {
                "method": syn_path.stem,
                "display": display,
                "route_ready_mean": ci["mean"],
                "ci_low": ci["ci_low"],
                "ci_high": ci["ci_high"],
                "n": ci["n"],
            }
        )
        for road_min in [0.90, 0.95, 0.98]:
            for jump2_max in [0.01, 0.02, 0.05]:
                m = route_ready_mask(rows, road_min=road_min, jump2_max=jump2_max)
                threshold_rows.append(
                    {
                        "method": syn_path.stem,
                        "display": display,
                        "road_min": road_min,
                        "jump2_max": jump2_max,
                        "accept_rate": float(np.mean(m)) if len(m) else 0.0,
                        "n_accepted": int(np.sum(m)),
                        "n_total": int(len(m)),
                    }
                )
        log(f"[{i}/{len(syn_files)}] {display}: route-ready={ci['mean']:.3f} CI=({ci['ci_low']:.3f},{ci['ci_high']:.3f})")

    write_csv(out_dir / "route_ready_bootstrap_ci.csv", ci_rows)
    write_csv(out_dir / "threshold_sensitivity.csv", threshold_rows)
    manifest = {
        "command_role": "evaluate_robustness",
        "real": args.real,
        "real_limit": args.real_limit,
        "osm_cache": args.osm_cache,
        "bootstrap_draws": args.bootstrap_draws,
        "seed": args.seed,
        "runtime_sec": float(time.time() - t0),
        "outputs": {
            "ci_csv": str((out_dir / "route_ready_bootstrap_ci.csv").resolve()),
            "threshold_csv": str((out_dir / "threshold_sensitivity.csv").resolve()),
        },
    }
    write_json(out_dir / "robustness_manifest.json", manifest)

    if args.paper_dir:
        paper_dir = Path(args.paper_dir)
        if not paper_dir.is_absolute():
            paper_dir = Path.cwd() / paper_dir
        write_ci_table(ci_rows, paper_dir / f"{args.table_prefix}_route_ready_ci.tex")
        write_threshold_table(threshold_rows, paper_dir / f"{args.table_prefix}_threshold_sensitivity.tex")
    log(f"completed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

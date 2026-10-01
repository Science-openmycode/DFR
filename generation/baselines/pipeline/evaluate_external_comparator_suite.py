"""Evaluate DPMM/PUTS diagnostics with the complete public metric suite.

The script deliberately writes two strata instead of manufacturing a common
leaderboard: (i) a frozen 3,000-record parent for MTR versus official DPMM;
and (ii) the FMM-eligible 86-record branch for independently trained MTR
versus released PUTS.  It never trains, reroutes, pads, or discards a release.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.distance import jensenshannon

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
for location in (ROOT, PIPELINE, ROOT / "src" / "mtr" / "shared_graph", ROOT.parent / "scripts"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from public_utils import filter_osm_ways_by_bbox, load_osm_ways, write_json


def load_pipeline_module(name: str):
    """Avoid importing similarly named legacy scripts from the wider workspace."""
    spec = importlib.util.spec_from_file_location(name, PIPELINE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {name} from the public pipeline")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revised = load_pipeline_module("evaluate_kdd_revised_statistics")
legacy = load_pipeline_module("evaluate_metrics")
downstream = load_pipeline_module("evaluate_downstream")
from route_structure_potential_experiment import prepare_graph

_external_spec = importlib.util.spec_from_file_location("external_road_metrics", PIPELINE / "evaluate_external_road_comparators.py")
if _external_spec is None or _external_spec.loader is None:
    raise RuntimeError("cannot import external road metric suite")
external = importlib.util.module_from_spec(_external_spec)
_external_spec.loader.exec_module(external)


def log(message: str) -> None:
    print(f"[external-suite] {time.strftime('%H:%M:%S')} {message}", flush=True)


def load_pickle(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if isinstance(payload, dict):
        raise ValueError(f"{path} is not a trajectory-list release")
    return [np.asarray(row, dtype=float)[:, :2] for row in payload if len(row) >= 2]


def hist_jsd(left: np.ndarray, right: np.ndarray, bins: np.ndarray) -> float:
    a = np.histogram(left, bins=bins)[0].astype(float) + 1e-12
    b = np.histogram(right, bins=bins)[0].astype(float) + 1e-12
    return float(jensenshannon(a / a.sum(), b / b.sum(), base=2.0) ** 2)


def turn_summary(real: list[np.ndarray], synthetic: list[np.ndarray]) -> dict[str, float]:
    real_turns = np.concatenate([downstream.turn_angles(t) for t in real if len(t) >= 3])
    syn_turns = np.concatenate([downstream.turn_angles(t) for t in synthetic if len(t) >= 3])
    bins = np.linspace(0.0, 180.0, 37)
    return {
        "turn_jsd": hist_jsd(real_turns, syn_turns, bins),
        "turn_mean_deg": float(np.mean(syn_turns)) if len(syn_turns) else 0.0,
        "turn_p90_deg": float(np.percentile(syn_turns, 90)) if len(syn_turns) else 0.0,
    }


def admission_summary(rows: list[dict]) -> dict[str, float]:
    flags = downstream.flags(rows)
    return {
        "mm_accept": float(np.mean(flags["map_matching"])),
        "strict_mm_accept": float(np.mean(flags["strict_map_matching"])),
        "route_ready": float(np.mean(flags["route_recovery"])),
        "eta_ready": float(np.mean(flags["eta_readiness"])),
        "simulation_ready": float(np.mean(flags["simulation"])),
    }


def runtime(path: Path) -> tuple[float | None, float | None, int | None]:
    manifests = [
        path.with_suffix(".json"),
        path.with_name(path.stem + "_protocol.json"),
        path.with_name(path.stem + "_ledger.json"),
    ]
    manifest = next((candidate for candidate in manifests if candidate.exists()), None)
    if manifest is None:
        return None, None, None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, None
    input_count = data.get("input_count", data.get("loaded_real_trajectories", data.get("n_train")))
    output_yield = data.get("output_yield")
    if output_yield is None and input_count:
        output_count = data.get("output_count", data.get("generated_trajectories", data.get("n_release")))
        if output_count is not None:
            output_yield = float(output_count) / float(input_count)
    return data.get("elapsed_seconds", data.get("runtime_sec")), output_yield, input_count


def evaluate_stratum(
    label: str,
    real: list[np.ndarray],
    methods: list[tuple[str, Path]],
    bbox: tuple[float, float, float, float],
    osm: list[dict],
    seed: int,
) -> list[dict]:
    lat0 = float(np.mean(np.vstack([t[[0, -1]] for t in real])[:, 0]))
    road_samples = legacy.sample_osm_points(osm, lat0, .08)
    road_tree = cKDTree(legacy.latlon_to_xy(road_samples, lat0))
    revised_ctx = revised.graph_context(osm, bbox)
    road_coords, graph = prepare_graph(real, bbox=bbox, osm_ways=osm, raw_graph=False)
    quality_real = downstream.traj_quality(real, road_tree, lat0)
    rows: list[dict] = []
    for method, path in methods:
        log(f"{label}: evaluating {method} ({path.name})")
        syn = load_pickle(path)
        elapsed, output_yield, input_count = runtime(path)
        start = time.time()
        broad = revised.evaluate(real, syn, bbox, lat0, revised_ctx, seed)
        road = legacy.road_metrics(syn, road_tree, lat0)
        distribution = legacy.distribution_metrics(real, syn, bbox, 64)
        quality = downstream.traj_quality(syn, road_tree, lat0)
        similarity = downstream.route_similarity_summary(real, syn, quality_real, quality, bbox, 32)
        edge = external.fast_edge_metric_suite(real, syn, real, road_coords, graph)
        row = {
            "stratum": label,
            "method": method,
            "n_real": len(real),
            "n_release": len(syn),
            "output_yield": float(output_yield) if output_yield is not None else len(syn) / len(real),
            "input_count_manifest": int(input_count) if input_count is not None else len(real),
            "runtime_sec_manifest": elapsed,
            **broad,
            **road,
            **distribution,
            **turn_summary(real, syn),
            **admission_summary(quality),
            "route_similarity_coverage": similarity["query_coverage"],
            "route_similarity_jaccard": similarity["mean_best_jaccard"],
            **edge,
            "evaluation_runtime_sec": time.time() - start,
        }
        rows.append(row)
        log(f"{label}: completed {method} in {row['evaluation_runtime_sec']:.1f}s")
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def tex_table(path: Path, rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    aligns = "l" * 2 + "r" * len(columns)
    header = " & ".join(["Stratum", "Method", *[label for label, _, _ in columns]]) + r" \\"
    lines = [r"\begin{tabular}{" + aligns + "}", r"\toprule", header, r"\midrule"]
    for row in rows:
        values = []
        for _, key, digits in columns:
            value = row.get(key)
            values.append("--" if value is None else f"{float(value):.{digits}f}")
        lines.append(" & ".join([str(row["stratum"]), str(row["method"]), *values]) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-real", type=Path, required=True)
    parser.add_argument("--parent-mtr", type=Path, required=True)
    parser.add_argument("--parent-dpmm", type=Path, required=True)
    parser.add_argument("--puts-real", type=Path, required=True)
    parser.add_argument("--puts-mtr", type=Path, required=True)
    parser.add_argument("--puts", type=Path, required=True)
    parser.add_argument("--osm-cache", type=Path, required=True)
    parser.add_argument("--bbox", nargs=4, type=float, required=True)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(); bbox = tuple(args.bbox)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log("loading public OSM once for both frozen strata")
    osm = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox)
    parent_rows = evaluate_stratum("central parent (N=3000)", load_pickle(args.parent_real),
        [("MTR / DP-GSRT", args.parent_mtr), ("DPMM official", args.parent_dpmm)], bbox, osm, args.seed)
    puts_rows = evaluate_stratum("FMM-eligible branch (m=86)", load_pickle(args.puts_real),
        [("MTR / DP-GSRT", args.puts_mtr), ("PUTS upstream", args.puts)], bbox, osm, args.seed)
    rows = [*parent_rows, *puts_rows]
    write_csv(args.out_dir / "external_comparator_big_table.csv", rows)
    (args.out_dir / "external_comparator_big_table.json").write_text(json.dumps({
        "protocol": "Two-stratum external comparison; no cross-stratum numerical ranking.",
        "bbox": bbox, "rows": rows,
        "runtime_note": "Runtime fields are native-run manifests, not evaluator runtime.",
    }, indent=2), encoding="utf-8")
    fidelity = [("Grid", "grid_density_jsd", 3), ("OD", "od_jsd", 3), ("Trip", "trip_error", 3), ("Len", "path_length_jsd", 3), ("Step", "step_jsd", 3), ("DTW", "conditional_nn_dtw_km", 3), ("Turn", "turn_jsd", 3), ("Seg", "road_segment_jsd", 3)]
    structure = [("Dir-valid", "directed_road_validity", 3), ("Road@200", "road_200m", 3), ("Jump>2", "jump_gt2km", 3), ("Route-ready", "route_ready", 3), ("Sim-ready", "simulation_ready", 3), ("Edge-flow", "edge_flow_jsd", 3), ("Edge-F1", "edge_coverage_f1", 3), ("Corridor", "od_corridor_jsd", 3), ("Yield", "output_yield", 3), ("Runtime s", "runtime_sec_manifest", 1)]
    tex_table(args.out_dir / "tables_external_big_fidelity.tex", rows, fidelity)
    tex_table(args.out_dir / "tables_external_big_structure.tex", rows, structure)
    (args.out_dir / "README.md").write_text(
        "# External Comparator Metric Suite\n\n"
        "`external_comparator_big_table.csv` is the complete metric record. The two TeX files are readable projections of the same rows. Rows are separated into a 3,000-record MTR--DPMM stratum and an 86-record MTR--PUTS stratum; values must not be ranked across strata.\n",
        encoding="utf-8")
    log(f"wrote complete suite to {args.out_dir}")


if __name__ == "__main__":
    main()

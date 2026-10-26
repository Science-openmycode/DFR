from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "multicity_current"
OUT = ROOT / "results" / "figures" / "multicity_current"
ROAD_RESULTS = ROOT / "results" / "road_route_metrics" / "current"
ACTIVE_ROAD_RESULTS = (
    ROOT / "results" / "active_hierarchy_release_v1_20260726" / "road_route"
)

CITIES = {
    "Beijing": ("beijing", {
        "MTR-GSRT": "mtr_gsrt_current_eval_v3",
        "SPRT": "sprt_current_eval_v3",
        "PrivTrace": "privtrace_current_eval_v3",
        "DPTraj-PM": "dptraj_pm_current_eval_v3",
        "DPStd": "dpstd_current_eval_v3",
    }),
    "Porto": ("porto", {
        "MTR-GSRT": "mtr_gsrt_current_eval_v3",
        "SPRT": "sprt_current_eval_v3",
        "PrivTrace": "privtrace_current_eval_v3",
        "DPTraj-PM": "dptraj_pm_current_eval_v3",
        "DPStd": "dpstd_current_eval_v3",
    }),
    "San Francisco": ("sf_trip20k", {
        "MTR-GSRT": "mtr_gsrt_current_eval_v3",
        "SPRT": "sprt_current_eval_v3",
        "PrivTrace": "privtrace_current_eval_v3",
        "DPTraj-PM": "dptraj_pm_current_eval_v3",
        "DPStd": "dpstd_current_eval_v3",
    }),
}
METHODS = ("MTR-GSRT", "SPRT", "PrivTrace", "DPTraj-PM", "DPStd")
METRICS = (
    ("grid_density_jsd", "Grid JSD", False),
    ("trip_error", "Trip error", False),
    ("path_length_jsd", "Length JSD", False),
    ("road_route_top1", "Route@1", True),
    ("road_route_top5", "Route@5", True),
    ("road_route_mrr", "MRR", True),
    ("road_route_best5_edge_f1", "Best-5 edge F1", True),
)
LOWER_IS_BETTER = {
    "A1_count_jsd_mean", "A1_range_are_nonzero", "A1_range_smape",
    "OD_jsd", "conditional_nn_dtw_km", "conditional_nn_frechet_km",
    "grid_density_jsd", "path_length_jsd", "road_segment_jsd", "trip_error",
    "od_conditioned_road_transition_jsd", "B2_next_region_nll",
}


def validate_method_set(reported: list[str], path: Path) -> None:
    if set(reported) != set(METHODS) or len(reported) != len(METHODS):
        raise RuntimeError(f"actual-road method set mismatch: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows() -> tuple[list[dict], dict[str, str]]:
    rows, inputs = [], {}
    evaluator_hashes = set()
    for city, (slug, runs) in CITIES.items():
        for method in METHODS:
            path = RESULTS / slug / runs[method] / "metrics.json"
            manifest = path.with_name("manifest.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            protocol, metrics = payload["protocol"], payload["metrics"]
            if protocol["real_count"] != protocol["synthetic_count"]:
                raise RuntimeError(f"unmatched counts: {path}")
            if protocol.get("public_slot_count") != protocol["real_count"]:
                raise RuntimeError(f"public-slot mismatch: {path}")
            evaluator_hashes.add(protocol["evaluator"]["entrypoint_sha256"])
            inputs[str(path.relative_to(ROOT))] = sha256(path)
            inputs[str(manifest.relative_to(ROOT))] = sha256(manifest)
            for legacy, current in (
                ("B2_route_od_coverage", "B2_grid_route_od_coverage"),
                ("B2_route_top1_hit", "B2_grid_route_top1_hit"),
                ("B2_route_top3_hit", "B2_grid_route_top3_hit"),
                ("B2_route_top5_hit", "B2_grid_route_top5_hit"),
                ("B2_route_mrr", "B2_grid_route_mrr"),
                ("B2_route_top1_edge_f1", "B2_grid_route_top1_transition_f1"),
                ("B2_route_best5_edge_f1", "B2_grid_route_best5_transition_f1"),
            ):
                if legacy in metrics:
                    metrics[current] = metrics.pop(legacy)
            rows.append({"city": city, "method": method, **metrics})
    if len(evaluator_hashes) != 1:
        raise RuntimeError(f"evaluator hashes differ: {sorted(evaluator_hashes)}")
    lookup = {(row["city"], row["method"]): row for row in rows}
    for city, slug in (
        ("Beijing", "beijing"),
        ("Porto", "porto"),
        ("San Francisco", "sf"),
    ):
        path = ROAD_RESULTS / slug / "metrics.json"
        manifest = path.with_name("manifest.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_method_set(payload["methods"], path)
        for method in METHODS:
            lookup[(city, method)].update(payload["results"][method])
        inputs[str(path.relative_to(ROOT))] = sha256(path)
        inputs[str(manifest.relative_to(ROOT))] = sha256(manifest)
    for city, run in (
        ("Beijing", "beijing_v2"),
        ("Porto", "porto_v3"),
        ("San Francisco", "sf_v2"),
    ):
        path = ACTIVE_ROAD_RESULTS / run / "metrics.json"
        manifest = path.with_name("manifest.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        active = payload["results"]["MTR-GSRT"]
        lookup[(city, "MTR-GSRT")].update(active)
        inputs[str(path.relative_to(ROOT))] = sha256(path)
        inputs[str(manifest.relative_to(ROOT))] = sha256(manifest)
    return rows, inputs


def write_csv(rows: list[dict]) -> Path:
    path = OUT / "multicity_metrics.csv"
    fields = ["city", "method", *(key for key, _, _ in METRICS), "witness_valid"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_full_metric_audit(rows: list[dict]) -> tuple[Path, Path]:
    """Record every comparable metric, including exceptions to MTR's first rank."""
    lookup = {(row["city"], row["method"]): row for row in rows}
    metric_names = sorted(set.intersection(*(
        {key for key, value in row.items() if isinstance(value, (int, float)) and value is not None}
        for row in rows
    )))
    audit_rows, summary = [], {}
    for city in CITIES:
        rank_counts = {str(rank): 0 for rank in range(1, 6)}
        for metric in metric_names:
            values = {method: float(lookup[(city, method)][metric]) for method in METHODS}
            lower = metric in LOWER_IS_BETTER
            mtr = values["MTR-GSRT"]
            baseline_values = [values[method] for method in METHODS[1:]]
            rank = 1 + sum(value < mtr if lower else value > mtr for value in baseline_values)
            rank_counts[str(rank)] += 1
            audit_rows.append({
                "city": city,
                "metric": metric,
                "direction": "lower" if lower else "higher",
                "mtr_gsrt": mtr,
                "best_baseline": min(baseline_values) if lower else max(baseline_values),
                "mtr_rank": rank,
            })
        summary[city] = {"comparable_metric_count": len(metric_names), "mtr_rank_counts": rank_counts}
    csv_path = OUT / "multicity_full_metric_audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    json_path = OUT / "multicity_full_metric_audit.json"
    json_path.write_text(json.dumps({"summary": summary, "rows": audit_rows}, indent=2), encoding="utf-8")
    return csv_path, json_path


def write_table(rows: list[dict], destination: Path, *, chinese: bool) -> None:
    lookup = {(row["city"], row["method"]): row for row in rows}
    lines = [
        r"\begin{tabular}{llrrrrrrr}",
        r"\toprule",
        (
            r"城市 & 方法 & Grid$\downarrow$ & Trip$\downarrow$ & Len$\downarrow$ & "
            r"Route@1$\uparrow$ & Route@5$\uparrow$ & MRR$\uparrow$ & Best-$\kroute$ F1$\uparrow$ \\"
            if chinese
            else r"City & Method & Grid$\downarrow$ & Trip$\downarrow$ & Len$\downarrow$ & "
            r"Route@1$\uparrow$ & Route@5$\uparrow$ & MRR$\uparrow$ & Best-$\kroute$ F1$\uparrow$ \\"
        ),
        r"\midrule",
    ]
    for city in CITIES:
        best = {}
        for key, _, higher in METRICS:
            candidates = [float(lookup[(city, method)][key]) for method in METHODS]
            best[key] = max(candidates) if higher else min(candidates)
        for index, method in enumerate(METHODS):
            row = lookup[(city, method)]
            translated_city = {"Beijing": "北京", "Porto": "波尔图", "San Francisco": "旧金山"}.get(city, city)
            city_cell = (translated_city if chinese else city) if index == 0 else ""
            values = []
            for key, _, _ in METRICS:
                value = float(row[key])
                rendered = f"{value:.3f}"
                if value == best[key]:
                    rendered = r"\textbf{" + rendered + "}"
                values.append(rendered)
            lines.append(
                f"{city_cell} & {method} & " + " & ".join(values) + r" \\"
            )
        lines.append(r"\midrule" if city != "San Francisco" else r"\bottomrule")
    lines.append(r"\end{tabular}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot(rows: list[dict]) -> tuple[Path, Path]:
    lookup = {(row["city"], row["method"]): row for row in rows}
    colors = ["#C44E52", "#4C72B0", "#55A868", "#8172B3", "#CCB974"]
    fig, axes = plt.subplots(3, len(METRICS), figsize=(17.5, 7.8), constrained_layout=True)
    for i, city in enumerate(CITIES):
        for j, (key, label, higher) in enumerate(METRICS):
            ax = axes[i, j]
            values = [lookup[(city, method)][key] for method in METHODS]
            ax.bar(np.arange(len(METHODS)), values, color=colors, width=.78)
            if i == 0:
                ax.set_title(label + (" ↑" if higher else " ↓"), fontsize=9)
            if j == 0:
                ax.set_ylabel(city, fontsize=9)
            ax.set_xticks(np.arange(len(METHODS)))
            ax.set_xticklabels(METHODS if i == 2 else [], rotation=55, ha="right", fontsize=7)
            ax.grid(axis="y", alpha=.25, linewidth=.5)
            ax.tick_params(axis="y", labelsize=7)
    pdf, png = OUT / "multicity_main_metrics.pdf", OUT / "multicity_main_metrics.png"
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(png, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return pdf, png


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, inputs = load_rows()
    csv_path = write_csv(rows)
    audit_csv, audit_json = write_full_metric_audit(rows)
    table_paths = [OUT / "tables" / lang / "tables_multicity_current.tex" for lang in ("en", "zh")]
    for path in table_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_table(rows, path, chinese=path.parent.name == "zh")
    pdf, png = plot(rows)
    outputs = [csv_path, audit_csv, audit_json, pdf, png, *table_paths]
    manifest = {
        "schema_version": 1,
        "classification": "CURRENT_MATCHED_MULTICITY_EVALUATION",
        "methods": list(METHODS),
        "cities": list(CITIES),
        "public_only_included": False,
        "inputs": inputs,
        "outputs": {str(path.relative_to(ROOT)): sha256(path) for path in outputs},
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

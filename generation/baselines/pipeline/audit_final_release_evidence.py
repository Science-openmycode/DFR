"""Fail-closed cross-check of public production, experiment, and figure evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMAL = (
    ROOT
    / "outputs"
    / "synthetic_releases"
    / "current_best"
    / "edge_witness_release_v1_20260720"
)
ACTIVE = (
    ROOT
    / "outputs"
    / "synthetic_releases"
    / "current_best"
    / "active_hierarchy_release_v1_20260726"
)
MATCHED = ROOT / "results" / "matched_active_hierarchy" / "current"
PRIVACY_FIGURE = (
    ROOT / "results" / "active_hierarchy_release_v1_20260726"
    / "figures" / "privacy_budget_paper"
)
MAIN_FIGURE = (
    ROOT
    / "results"
    / "figures"
    / "paper_beijing"
    / "active_hierarchy_release_v1_20260726_all_methods_compact_v3"
)
MULTICITY = ROOT / "results" / "figures" / "multicity_current"
STATISTICAL_TABLES = (
    ROOT / "outputs" / "kdd_revised" / "current_statistical_comparison_20260720" / "tables"
)
ROAD_BEIJING = (
    ROOT / "results" / "road_route_metrics" / "current" / "beijing" / "metrics.json"
)
ACTIVE_ROAD_BEIJING = (
    ROOT / "results" / "active_hierarchy_release_v1_20260726"
    / "road_route" / "beijing_v2" / "metrics.json"
)
BASELINE_EVALUATIONS = {
    "SPRT-native": ROOT / "results" / "multicity_current" / "beijing" / "sprt_current_eval_v3" / "metrics.json",
    "PrivTrace-native": ROOT / "results" / "multicity_current" / "beijing" / "privtrace_current_eval_v3" / "metrics.json",
    "DPTrajPM-native": ROOT / "results" / "multicity_current" / "beijing" / "dptraj_pm_current_eval_v3" / "metrics.json",
    "DPStd-native": ROOT / "results" / "multicity_current" / "beijing" / "dpstd_current_eval_v3" / "metrics.json",
}
MTR_BEIJING_EVALUATION = (
    ROOT / "results" / "multicity_current" / "beijing"
    / "mtr_gsrt_current_eval_v3" / "metrics.json"
)
EXPECTED_METHODS = ("MTR-GSRT", "SPRT", "PrivTrace", "DPTraj-PM", "DPStd")
ACTUAL_ROAD_METRICS = (
    "od_conditioned_road_transition_jsd",
    "road_route_top1",
    "road_route_top5",
    "road_route_mrr",
    "road_route_best5_edge_f1",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def public_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def decimal(value: float, digits: int) -> str:
    rendered = f"{float(value):.{digits}f}"
    return rendered[1:] if rendered.startswith("0.") else rendered


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise RuntimeError(message)
    checks.append(message)


def validate_actual_road_payload(
    payload: dict, relative: str, checks: list[str]
) -> None:
    """Validate the aggregate produced by the actual-road metric CLI."""
    methods = payload.get("methods")
    results = payload.get("results")
    require(
        isinstance(methods, list)
        and len(methods) == len(EXPECTED_METHODS)
        and set(methods) == set(EXPECTED_METHODS),
        f"actual-road method set is complete: {relative}",
        checks,
    )
    require(
        payload.get("classification")
        == "RESEARCH_EVALUATION_LEDGER_NOT_A_DP_RELEASE",
        f"actual-road aggregate has the evaluation-ledger classification: {relative}",
        checks,
    )
    require(
        isinstance(payload.get("record_count"), int)
        and payload["record_count"] > 0,
        f"actual-road aggregate records a positive evaluation count: {relative}",
        checks,
    )
    require(
        isinstance(results, dict) and set(results) == set(EXPECTED_METHODS),
        f"actual-road results cover every method exactly once: {relative}",
        checks,
    )
    for method in EXPECTED_METHODS:
        row = results[method]
        for metric in ACTUAL_ROAD_METRICS:
            value = row.get(metric)
            require(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value)),
                f"actual-road metric is finite ({method}, {metric}): {relative}",
                checks,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "check" / "final_release_audit_20260720" / "report.json",
    )
    args = parser.parse_args()
    checks: list[str] = []

    active_manifest = read_json(
        ROOT / "outputs" / "synthetic_releases" / "current_best" / "MANIFEST.json"
    )
    status = read_json(ROOT / "src" / "mtr" / "DP_GSRT" / "CURRENT_METHOD_STATUS.json")
    formal_protocol = read_json(FORMAL / "protocol.json")
    protocol = read_json(ACTIVE / "protocol.json")
    lineage = read_json(FORMAL / "source_lineage_compatibility.json")
    package = read_json(FORMAL / "road_witness_release_v1.json")
    metrics = read_json(MTR_BEIJING_EVALUATION)["metrics"]
    control = read_json(FORMAL / "evaluation_public_control" / "metrics.json")["metrics"]
    dp = active_manifest["dp_gsrt_status"]

    require(
        active_manifest["status"] == "ACTIVE_MTR_GSRT_HIERARCHICAL_POSTPROCESSING_V1",
        "active manifest selects the reviewed active-hierarchy release",
        checks,
    )
    require(
        status["promotion_status"] == "APPROVED_ACTIVE_HIERARCHY_V1"
        and status["active_algorithm_id"] == "mtr-gsrt-active-hierarchy-v1",
        "method status records the reviewed active-hierarchy promotion",
        checks,
    )
    require(
        formal_protocol["classification"] == "PRODUCTION_DP_POSTPROCESS"
        and formal_protocol["certified_release"] is True,
        "superseded edge-witness protocol remains a certified historical release",
        checks,
    )
    require(
        protocol["classification"] == "PROMOTED_REVIEWED_DP_TRANSCRIPT_POSTPROCESSING"
        and protocol["privacy"]["epsilon"] == "7/5"
        and float(protocol["privacy"]["delta"]) == 0.0
        and protocol["privacy"]["new_private_access"] is False
        and float(protocol["privacy"]["additional_privacy_cost"]) == 0.0,
        "active protocol records pure (7/5,0)-DP transcript post-processing",
        checks,
    )
    require(
        len(protocol["active_hierarchy"]["active_blocks"]) == 8
        and protocol["active_hierarchy"]["fallback_count"] == 0
        and protocol["active_hierarchy"]["row_sum_max_abs_error"] <= 1e-12
        and protocol["active_hierarchy"]["minimum_positive_probability"] > 0.0,
        "all eight released hierarchy blocks enter a positive stochastic route law",
        checks,
    )
    coordinates = ACTIVE / "trajectories.pkl"
    witness = ACTIVE / "road_witnesses.pkl"
    require(sha256(coordinates) == dp["artifact_sha256"], "active coordinate hash matches", checks)
    require(sha256(witness) == dp["witness_sha256"], "active witness hash matches", checks)
    require(
        package["record_count"] == protocol["public_slot_count"]
        == protocol["output_count"] == 17123,
        "active coordinate/witness release contains 17,123 fixed slots",
        checks,
    )
    require(
        lineage["passed"] is True
        and lineage["transcript_manifest_sha256"]
        == formal_protocol["inputs"]["portal_manifest_sha256"],
        "historical certified query-source lineage remains transcript-bound",
        checks,
    )
    require(
        sha256(ROOT / protocol["source_binding"]["source_manifest"])
        == protocol["source_binding"]["source_manifest_sha256"]
        and sha256(ROOT / "src" / "mtr" / "DP_GSRT" / "final"
                   / "quotient_rsp_bridge_development.py")
        == protocol["source_binding"]["decoder_sha256"]
        and sha256(ROOT / "generation" / "mtr" / "generate.py")
        == protocol["source_binding"]["generation_cli_sha256"],
        "active protocol is bound to the promoted source manifest, decoder, and CLI",
        checks,
    )
    require(metrics["witness_valid"] == 1.0, "current evaluator measured WitnessValid=1.0", checks)
    require(control["witness_valid"] is None, "public control claims no edge witness", checks)

    baseline_metrics = {
        name: read_json(path)["metrics"] for name, path in BASELINE_EVALUATIONS.items()
    }
    road_metrics = read_json(ROAD_BEIJING)["results"]
    road_metrics["MTR-GSRT"].update(
        read_json(ACTIVE_ROAD_BEIJING)["results"]["MTR-GSRT"]
    )
    road_names = {
        "SPRT-native": "SPRT",
        "PrivTrace-native": "PrivTrace",
        "DPTrajPM-native": "DPTraj-PM",
        "DPStd-native": "DPStd",
        "MTR-GSRT": "MTR-GSRT",
    }
    expected_main = {
        name: [
            *[values[key] for key in (
                "grid_density_jsd", "trip_error", "path_length_jsd",
            )],
            values["B2_next_region_accuracy"],
            values["B2_next_region_nll"],
        ]
        for name, values in baseline_metrics.items()
    }
    expected_main["MTR-GSRT"] = [
        *[metrics[key] for key in (
            "grid_density_jsd", "trip_error", "path_length_jsd",
        )],
        metrics["witness_valid"],
        metrics["B2_next_region_accuracy"],
        metrics["B2_next_region_nll"],
    ]
    expected_task = {
        name: [
            values["B2_next_region_accuracy"],
            values["B2_next_region_nll"],
        ]
        for name, values in baseline_metrics.items()
    }
    expected_task["MTR-GSRT"] = [
        metrics["B2_next_region_accuracy"],
        metrics["B2_next_region_nll"],
    ]
    for language in ("en", "zh"):
        table = (STATISTICAL_TABLES / language / "tables_kdd_revised_main_statistics.tex").read_text(encoding="utf-8")
        task = (STATISTICAL_TABLES / language / "tables_kdd_revised_task_utility.tex").read_text(encoding="utf-8")
        for label, values in expected_main.items():
            row = next((line for line in table.splitlines() if label in line), "")
            require(
                bool(row) and all(decimal(value, 3) in row for value in values),
                f"{language} main table contains current rounded {label} metrics",
                checks,
            )
        for label, values in expected_task.items():
            row = next((line for line in task.splitlines() if label in line), "")
            require(
                bool(row) and all(decimal(value, 3) in row for value in values),
                f"{language} task table contains current rounded {label} metrics",
                checks,
            )

    main_figure = read_json(MAIN_FIGURE / "beijing_all_methods_compact.json")
    expected_panels = [
        "Real", "SPRT-native", "PrivTrace-native", "DPTrajPM-native",
        "DPStd-native", "MTR-GSRT",
    ]
    require(
        [panel["label"] for panel in main_figure["panels"]] == expected_panels,
        "main figure contains Real, four statistical synthesizers, and MTR only",
        checks,
    )
    require(
        all(panel["loaded_count"] == 17123 for panel in main_figure["panels"]),
        "main figure is count-matched at 17,123 records per panel",
        checks,
    )
    require(
        sha256(public_path(main_figure["outputs"]["pdf"])) == main_figure["output_sha256"]["pdf"],
        "public main-figure PDF matches its manifest hash",
        checks,
    )

    multicity = read_json(MULTICITY / "manifest.json")
    require(
        multicity["classification"] == "CURRENT_MATCHED_MULTICITY_EVALUATION",
        "cross-city manifest is the current matched evaluation",
        checks,
    )
    require(
        multicity["methods"] == ["MTR-GSRT", "SPRT", "PrivTrace", "DPTraj-PM", "DPStd"]
        and multicity["cities"] == ["Beijing", "Porto", "San Francisco"]
        and multicity["public_only_included"] is False,
        "cross-city comparison contains exactly MTR-GSRT and four statistical methods in three cities",
        checks,
    )
    for relative, expected in multicity["inputs"].items():
        require(
            sha256(ROOT / relative) == expected,
            f"cross-city input hash matches: {relative}",
            checks,
        )
    for relative, expected in multicity["outputs"].items():
        require(
            sha256(ROOT / relative) == expected,
            f"cross-city output hash matches: {relative}",
            checks,
        )
    evaluator_hashes = set()
    osm_selection_rows = []
    sf_osm_contracts = []
    sf_real_hashes = []
    unified_metric_rows = 0
    actual_road_rows = 0
    active_road_override_rows = 0
    for relative in multicity["inputs"]:
        if relative.endswith("metrics.json"):
            item = read_json(ROOT / relative)
            if "protocol" not in item:
                if set(item.get("methods", [])) == set(EXPECTED_METHODS):
                    validate_actual_road_payload(item, relative, checks)
                    actual_road_rows += 1
                else:
                    active_row = item.get("results", {}).get("MTR-GSRT", {})
                    require(
                        set(ACTUAL_ROAD_METRICS) <= set(active_row)
                        and all(
                            isinstance(active_row[key], (int, float))
                            and math.isfinite(float(active_row[key]))
                            for key in ACTUAL_ROAD_METRICS
                        ),
                        f"active-hierarchy actual-road override is complete: {relative}",
                        checks,
                    )
                    active_road_override_rows += 1
                continue
            item_protocol = item["protocol"]
            unified_metric_rows += 1
            require(
                item_protocol["real_count"] == item_protocol["synthetic_count"]
                == item_protocol["public_slot_count"],
                f"cross-city metric row is count matched: {relative}",
                checks,
            )
            evaluator_hashes.add(item_protocol["evaluator"]["entrypoint_sha256"])
            osm_selection_rows.append(item_protocol.get("osm_selection"))
            if "sf_trip20k" in Path(relative).parts:
                sf_osm_contracts.append(
                    (
                        item_protocol.get("osm_bbox_way_count"),
                        item_protocol.get("osm_selected_way_count"),
                        item_protocol.get("osm_max_ways"),
                        tuple(item_protocol.get("osm_highway_classes", [])),
                    )
                )
                sf_manifest = read_json((ROOT / relative).with_name("manifest.json"))
                sf_real_hashes.append(sf_manifest["inputs"]["real"].get("sha256"))
    require(
        unified_metric_rows == 15,
        "cross-city manifest contains exactly 15 unified-evaluator rows",
        checks,
    )
    require(
        actual_road_rows == 3,
        "cross-city manifest contains exactly three actual-road aggregates",
        checks,
    )
    require(
        active_road_override_rows == 3,
        "cross-city manifest contains exactly three active-hierarchy MTR road overrides",
        checks,
    )
    require(len(evaluator_hashes) == 1, "all cross-city rows share one evaluator hash", checks)
    require(
        evaluator_hashes == {sha256(ROOT / "evaluation" / "evaluate_all.py")},
        "cross-city evaluator hash matches the current unified evaluator",
        checks,
    )
    require(
        set(osm_selection_rows) == {"bbox_filter_then_highway_class_filter_then_optional_deterministic_spatial_thinning"},
        "all cross-city rows record the same public OSM selection rule",
        checks,
    )
    sf_classes = (
        "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
        "secondary", "secondary_link", "tertiary", "tertiary_link",
    )
    require(
        len(sf_osm_contracts) == 5
        and set(sf_osm_contracts) == {(14114, 14114, 0, sf_classes)},
        "all San Francisco rows share the declared 14,114-way vehicle-road contract",
        checks,
    )
    require(
        set(sf_real_hashes) == {"544cc51b459554d52bebe0f881c58f4aa6896ae2a319f5b23c048d7ec415511e"},
        "all San Francisco rows bind the frozen 20,000-trip real input hash",
        checks,
    )
    full_metric_audit = read_json(MULTICITY / "multicity_full_metric_audit.json")
    primary_rank_metrics = {
        "grid_density_jsd",
        "B2_next_region_accuracy",
        "B2_next_region_nll",
        "road_route_best5_edge_f1",
    }
    expected_primary_ranks = {
        city: {metric: 1 for metric in primary_rank_metrics}
        for city in ("Beijing", "Porto", "San Francisco")
    }
    for city, summary in full_metric_audit["summary"].items():
        require(
            sum(summary["mtr_rank_counts"].values())
            == summary["comparable_metric_count"],
            f"{city} non-selective metric ledger accounts for every comparable metric",
            checks,
        )
        rows = {
            row["metric"]: row
            for row in full_metric_audit["rows"]
            if row["city"] == city
        }
        require(
            primary_rank_metrics.issubset(rows)
            and {
                metric: rows[metric]["mtr_rank"] for metric in primary_rank_metrics
            }
            == expected_primary_ranks[city],
            (
                f"{city} primary ranks match the manuscript claim"
            ),
            checks,
        )
    for language in ("en", "zh"):
        table = MULTICITY / "tables" / language / "tables_multicity_current.tex"
        table_text = table.read_text(encoding="utf-8")
        require(
            "MTR-GSRT" in table_text and "Public-only" not in table_text,
            f"{language} exported cross-city table contains MTR-GSRT and excludes Public-only",
            checks,
        )

    matched = read_json(MATCHED / "matched_summary.json")
    require(matched["acceptance"]["passed"] is False, "strict matched q5 acceptance rule failed", checks)
    require(len(matched["per_seed"]) == 2, "strict matched active-hierarchy audit uses two transcript seeds", checks)
    require(
        all(set(row["arms"]) == {"public_only", "shuffled_dp", "correct_dp"} for row in matched["per_seed"]),
        "each matched seed executes all three route-alignment arms",
        checks,
    )
    require(
        all(
            len({
                tuple(sorted(arm["source_dp_hashes"].items()))
                for arm in row["arms"].values()
            }) == 1
            for row in matched["per_seed"]
        ),
        "all arms share one released DP transcript within each seed",
        checks,
    )
    require(
        all("transition_jsd" in row["arms"]["correct_dp"] for row in matched["per_seed"]),
        "matched active-hierarchy summary exposes the current Correct-DP transition statistic",
        checks,
    )

    figure_manifest = read_json(PRIVACY_FIGURE / "figure_manifest.json")
    require(figure_manifest["run_count"] == 35, "privacy-budget figure uses all 35 runs", checks)
    require(
        figure_manifest["expected_output_count"] == 17123,
        "privacy-budget figure is bound to 17,123 output slots",
        checks,
    )
    for name, expected in figure_manifest["outputs"].items():
        require(sha256(PRIVACY_FIGURE / name) == expected, f"privacy figure output hash matches: {name}", checks)

    with (PRIVACY_FIGURE / "metrics_summary.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        summary_rows = list(csv.DictReader(handle))
    summary = {
        (row["epsilon"], row["metric"]): float(row["mean"])
        for row in summary_rows
    }
    reported_sweep = {
        ("1/5", "grid_density_jsd"), ("3", "grid_density_jsd"),
        ("1/5", "trip_error"), ("3", "trip_error"),
        ("1/5", "road_segment_jsd"), ("3", "road_segment_jsd"),
        ("1/5", "A1_range_smape"), ("3", "A1_range_smape"),
        ("1/5", "path_length_jsd"), ("3", "path_length_jsd"),
        ("1/5", "directed_road_validity"), ("3", "directed_road_validity"),
        ("7/5", "witness_valid"),
        ("7/5", "B1_dest8_top5"), ("7/10", "B1_dest8_top5"),
        ("2", "B2_grid_route_best5_transition_f1"),
        ("3", "B2_grid_route_best5_transition_f1"),
    }
    require(
        reported_sweep <= set(summary),
        "privacy-budget summary contains every manuscript-reported endpoint",
        checks,
    )
    rendered_sweep = {decimal(summary[key], 3) for key in reported_sweep}
    require(
        all(value and value.lower() not in {"nan", "inf", "-inf"} for value in rendered_sweep),
        "privacy-budget reported endpoints are finite and renderable",
        checks,
    )

    report = {
        "schema_version": 1,
        "passed": True,
        "checks": checks,
        "formal_artifact_sha256": sha256(coordinates),
        "formal_witness_sha256": sha256(witness),
        "matched_summary_sha256": sha256(MATCHED / "matched_summary.json"),
        "privacy_figure_manifest_sha256": sha256(PRIVACY_FIGURE / "figure_manifest.json"),
        "privacy_metrics_summary_sha256": sha256(PRIVACY_FIGURE / "metrics_summary.csv"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "check_count": len(checks), "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()

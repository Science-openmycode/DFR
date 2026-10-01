"""Fail-closed inventory check for every experiment used by the current paper.

This command is read-only.  It verifies that the command-line entry points and
the paper-active artifacts are present, and writes a machine-readable report
when requested.  It intentionally does not treat archived/withdrawn runs as
current evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ENTRYPOINTS = (
    "generation/mtr/generate.py",
    "generation/baselines/generate.py",
    "evaluation/evaluate_all.py",
    "evaluation/evaluate_road_choice.py",
    "evaluation/aggregate_privacy_budget_road_choice.py",
    "evaluation/metric_suites/road_choice.py",
    "evaluation/evaluate_road_route.py",
    "evaluation/aggregate_road_route_chunks.py",
    "evaluation/prepare_road_evaluation_network.py",
    "evaluation/verify_road_route_chunk.py",
    "plotting/plot_privacy_budget.py",
    "plotting/plot_privacy_budget_road_choice.py",
    "plotting/plot_privacy_budget_paper.py",
    "pipeline/render_multicity_current.py",
    "pipeline/prepare_privacy_attack_splits.py",
    "pipeline/run_mtr_portal_fiber_audit_instance.py",
    "pipeline/evaluate_domias_official.py",
    "pipeline/evaluate_population_linkage.py",
    "pipeline/evaluate_gda_mia.py",
    "pipeline/evaluate_ordered_interface_linkage.py",
    "pipeline/redecode_active_hierarchy_transcript.py",
    "pipeline/run_matched_active_hierarchy.py",
    "pipeline/audit_final_release_evidence.py",
    "commands/run_formal_edge_witness_release.ps1",
    "commands/run_current_privacy_attacks.ps1",
    "commands/run_external_all_metrics.ps1",
    "commands/render_current_paper_figures.ps1",
    "commands/run_mtr_epsilon_sweep.ps1",
    "commands/run_privacy_budget_road_choice.ps1",
    "commands/run_road_choice_metrics.ps1",
    "commands/run_portal_unit_ablation_metrics.ps1",
    "commands/run_multicity_evaluation.ps1",
    "commands/run_road_route_chunks.ps1",
    "commands/run_all_paper_experiments.ps1",
)

MULTICITY = {
    "beijing": (
        "mtr_gsrt_current_eval_v3",
        "sprt_current_eval_v3",
        "privtrace_current_eval_v3",
        "dptraj_pm_current_eval_v3",
        "dpstd_current_eval_v3",
    ),
    "porto": (
        "mtr_gsrt_current_eval_v3",
        "sprt_current_eval_v3",
        "privtrace_current_eval_v3",
        "dptraj_pm_current_eval_v3",
        "dpstd_current_eval_v3",
    ),
    "sf_trip20k": (
        "mtr_gsrt_current_eval_v3",
        "sprt_current_eval_v3",
        "privtrace_current_eval_v3",
        "dptraj_pm_current_eval_v3",
        "dpstd_current_eval_v3",
    ),
}

CURRENT_RESULTS = (
    "outputs/synthetic_releases/current_best/active_hierarchy_release_v1_20260726/protocol.json",
    "outputs/synthetic_releases/current_best/active_hierarchy_release_v1_20260726/MANIFEST.json",
    "outputs/synthetic_releases/current_best/active_hierarchy_release_v1_20260726/evaluation/metrics.json",
    "outputs/synthetic_releases/current_best/edge_witness_release_v1_20260720/protocol.json",
    "outputs/synthetic_releases/current_best/edge_witness_release_v1_20260720/road_witness_release_v1.json",
    "results/figures/multicity_current/manifest.json",
    "results/figures/multicity_current/multicity_full_metric_audit.json",
    "results/active_hierarchy_release_v1_20260726/figures/privacy_budget_paper/figure_manifest.json",
    "results/active_hierarchy_release_v1_20260726/road_route/beijing_v2/manifest.json",
    "results/active_hierarchy_release_v1_20260726/road_route/porto_v3/manifest.json",
    "results/active_hierarchy_release_v1_20260726/road_route/sf_v2/manifest.json",
    "results/road_route_metrics/current/beijing/manifest.json",
    "results/road_route_metrics/current/porto/manifest.json",
    "results/road_route_metrics/current/sf/manifest.json",
    "results/road_route_metrics/network/geolife/manifest.json",
    "results/road_route_metrics/network/porto/manifest.json",
    "results/road_route_metrics/network/sf/manifest.json",
    "results/matched_active_hierarchy/current/matched_summary.json",
    "results/matched_active_hierarchy/current/manifest.json",
    "results/active_hierarchy_release_v1_20260726/privacy_attacks/domias_v3/results.json",
    "results/active_hierarchy_release_v1_20260726/privacy_attacks/gda_v3/results.json",
    "results/active_hierarchy_release_v1_20260726/privacy_attacks/ordered_v3/results.json",
    "results/active_hierarchy_release_v1_20260726/privacy_attacks/population_linkage_v3/results.json",
    "results/active_hierarchy_release_v1_20260726/privacy_attacks/attack_manifest.json",
    "results/figures/paper_unified/figure_manifest_en.json",
    "results/figures/paper_unified/figure_manifest_zh.json",
    "results/figures/external_all_metrics/en/external_all_metrics_en.manifest.json",
    "results/figures/external_all_metrics/zh/external_all_metrics_zh.manifest.json",
    "check/active_hierarchy_promotion_20260726/final_release_audit.json",
    "results/road_choice_metrics/beijing_public_crossing_v4_20260727/manifest.json",
    "results/road_choice_metrics/sf_public_crossing_v4_20260727/manifest.json",
    "results/road_choice_metrics/privacy_budget_geolife_carrier_v2/aggregate/manifest.json",
    "results/road_choice_metrics/privacy_budget_geolife_carrier_v2/figures/figure_manifest.json",
    "results/portal_unit_ablation/seed_20260719/road_choice_matched_carrier_v1/manifest.json",
    "results/figures/privacy_budget/privacy_budget_paper_carrier_v2.manifest.json",
    "results/figures/privacy_budget/privacy_budget_paper_carrier_v2_zh.manifest.json",
    "results/figures/external_all_metrics/en_carrier_v2/external_all_metrics_en.manifest.json",
    "results/figures/external_all_metrics/zh_carrier_v2/external_all_metrics_zh.manifest.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_json(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # fail closed, with a useful path-specific error
        return f"invalid JSON: {exc}"
    if path.name in {"report_reorganized.json", "final_release_audit.json"} and payload.get("passed") is not True:
        return "final evidence audit does not report passed=true"
    return None


def check_file(relative: str, *, parse_json: bool = False) -> dict[str, object]:
    path = ROOT / relative
    row: dict[str, object] = {"path": relative, "exists": path.is_file()}
    if path.is_file():
        row["bytes"] = path.stat().st_size
        row["sha256"] = sha256(path)
        if parse_json:
            row["error"] = inspect_json(path)
    else:
        row["error"] = "missing"
    row["passed"] = row.get("error") is None
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("commands", "results", "all"), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    checks: list[dict[str, object]] = []
    if args.scope in {"commands", "all"}:
        checks.extend(check_file(path) for path in ENTRYPOINTS)
    if args.scope in {"results", "all"}:
        for city, runs in MULTICITY.items():
            for run in runs:
                base = f"results/multicity_current/{city}/{run}"
                checks.append(check_file(f"{base}/metrics.json", parse_json=True))
                checks.append(check_file(f"{base}/manifest.json", parse_json=True))
        checks.extend(
            check_file(path, parse_json=path.endswith(".json")) for path in CURRENT_RESULTS
        )

    failures = [row for row in checks if not row["passed"]]
    report = {
        "schema_version": 1,
        "classification": "READ_ONLY_CURRENT_PAPER_EXPERIMENT_INVENTORY",
        "public_release_root": str(ROOT),
        "scope": args.scope,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failures),
        "failed_count": len(failures),
        "multicity_evaluation_count": sum(len(runs) for runs in MULTICITY.values()),
        "checks": checks,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        destination = args.out if args.out.is_absolute() else ROOT / args.out
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

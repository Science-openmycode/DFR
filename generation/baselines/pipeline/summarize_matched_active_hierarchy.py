from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
ARMS = ("portal_prior", "permuted_portal_dp", "aligned_portal_dp")
LABELS = {
    "portal_prior": "Portal-prior",
    "permuted_portal_dp": "Permuted-Portal-DP",
    "aligned_portal_dp": "Aligned-Portal-DP",
}
METRICS = (
    ("grid_density_jsd", "Grid JSD", False),
    ("trip_error", "Trip error", False),
    ("path_length_jsd", "Length JSD", False),
    ("witness_valid", "WitnessValid", True),
    ("B2_next_region_accuracy", "NextAcc", True),
    ("B2_next_region_nll", "NextNLL", False),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        default=PUBLIC_RELEASE
        / "results"
        / "matched_active_hierarchy"
        / "current"
        / "matched_main_metrics_summary.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PUBLIC_RELEASE / "results" / "matched_active_hierarchy" / "current_summary",
    )
    args = parser.parse_args()
    payload = json.loads(args.summary.read_text(encoding="utf-8"))
    rows = payload["runs"]
    expected = {(seed, arm) for seed in ("seed_v4", "seed_v5") for arm in ARMS}
    actual = {(row["seed"], row["arm"]) for row in rows}
    if actual != expected or len(rows) != 6:
        raise ValueError(f"matched run matrix mismatch: {sorted(expected - actual)}")
    for row in rows:
        if set(row["metrics"]) != {item[0] for item in METRICS}:
            raise ValueError(f"metric schema mismatch: {row['seed']}/{row['arm']}")
        if not all(math.isfinite(float(value)) for value in row["metrics"].values()):
            raise ValueError(f"non-finite metric: {row['seed']}/{row['arm']}")

    args.out_dir.mkdir(parents=True, exist_ok=False)
    long_path = args.out_dir / "matched_main_metrics.csv"
    with long_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("seed", "arm", "metric", "value"))
        writer.writeheader()
        for row in rows:
            for metric, _, _ in METRICS:
                writer.writerow(
                    {
                        "seed": row["seed"],
                        "arm": LABELS[row["arm"]],
                        "metric": metric,
                        "value": row["metrics"][metric],
                    }
                )

    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_seed = {}
    for row in rows:
        by_seed[(row["seed"], row["arm"])] = row["metrics"]
        for metric, _, _ in METRICS:
            values[(row["arm"], metric)].append(float(row["metrics"][metric]))

    navigation_checks = []
    for seed in ("seed_v4", "seed_v5"):
        aligned = by_seed[(seed, "aligned_portal_dp")]
        controls = [
            by_seed[(seed, "portal_prior")],
            by_seed[(seed, "permuted_portal_dp")],
        ]
        acc = aligned["B2_next_region_accuracy"] > max(
            row["B2_next_region_accuracy"] for row in controls
        )
        nll = aligned["B2_next_region_nll"] < min(
            row["B2_next_region_nll"] for row in controls
        )
        navigation_checks.append(
            {"seed": seed, "NextAcc": acc, "NextNLL": nll, "both": acc and nll}
        )

    lines = [
        "# Matched paper-metric result",
        "",
        "Only the six metrics printed in the current main paper are evaluated.",
        "Values below are means across the two sealed DP transcripts.",
        "",
        "| Metric | Portal-prior | Permuted-Portal-DP | Aligned-Portal-DP | Direction |",
        "|---|---:|---:|---:|:---:|",
    ]
    for metric, label, higher in METRICS:
        means = {
            arm: sum(values[(arm, metric)]) / len(values[(arm, metric)])
            for arm in ARMS
        }
        best = max(means, key=means.get) if higher else min(means, key=means.get)
        rendered = []
        for arm in ARMS:
            text = f"{means[arm]:.6f}"
            rendered.append(f"**{text}**" if arm == best else text)
        lines.append(
            f"| {label} | {rendered[0]} | {rendered[1]} | {rendered[2]} | "
            f"{'higher' if higher else 'lower'} |"
        )
    strict = all(row["both"] for row in navigation_checks)
    lines.extend(
        [
            "",
            "The matched navigation rule requires Aligned-Portal-DP to achieve "
            "higher NextAcc and lower NextNLL than both controls in each seed.",
            "",
            f"- seed_v4: {navigation_checks[0]}",
            f"- seed_v5: {navigation_checks[1]}",
            f"- strict navigation rule passed: `{strict}`",
            "",
            "Grid, Trip, Length, and WitnessValid are reported as paper controls; "
            "they are not used to select the portal arm.",
        ]
    )
    md_path = args.out_dir / "MATCHED_MAIN_METRICS_RESULT.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    decision_path = args.out_dir / "decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": [item[0] for item in METRICS],
                "navigation_checks": navigation_checks,
                "strict_navigation_passed": strict,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "markdown": str(md_path),
                "csv": str(long_path),
                "decision": str(decision_path),
                "strict_navigation_passed": strict,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

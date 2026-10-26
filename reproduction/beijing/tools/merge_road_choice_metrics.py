"""Merge independently scored road-choice metrics into a batch long table.

This is evaluation-only: it never synthesizes or routes.  It adds only metrics
that the pinned road-choice evaluator actually produced; BTF/EdgeCPC/TurnCPC/
FamilyCPC are deliberately not inferred here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--metrics", nargs="+", required=True,
                        help="ROUTER=road-choice-evaluation-directory")
    args = parser.parse_args()
    root = args.batch.resolve()
    table_path = root / "data_results" / "beijing" / "batch_001" / "metrics_long.csv"
    rows = list(csv.DictReader(table_path.open(encoding="utf-8", newline="")))
    # Older tables have seven columns; native rows and newer evaluators add
    # provenance.  Normalize before appending so a merge cannot truncate the
    # file and then fail on an unexpected ``source`` field.
    for row in rows:
        row.setdefault("source", "cell_evaluation")
    seen = {(r["M"], r["R"], r["metric"]) for r in rows}
    added = []
    source_records = {}
    for spec in args.metrics:
        if "=" not in spec:
            raise SystemExit(f"expected ROUTER=DIR, got {spec!r}")
        router, raw_dir = spec.split("=", 1)
        metrics_dir = Path(raw_dir).resolve()
        payload = json.loads((metrics_dir / "metrics.json").read_text(encoding="utf-8"))
        source_records[router] = str((metrics_dir / "metrics.json").resolve())
        for method, values in payload["results"].items():
            route_manifest = json.loads(
                (root / "data_results" / "beijing" / "batch_001" /
                 method / router / "route_manifest.json").read_text(encoding="utf-8")
            )
            reasons = route_manifest.get("reasons", {})
            valid = sum(int(value) for key, value in reasons.items()
                        if key in {"accepted", "connected"})
            slots = int(route_manifest.get("records", 0))
            road_yield = valid / slots if slots else 0.0
            values_to_add = {
                "RoadYield": road_yield,
                "RC-CPC": float(values["road_choice_cpc"] * road_yield),
                "RC-NDCG": float(values["road_choice_ndcg"] * road_yield),
                "NextRoadAcc": float(values["next_road_accuracy"] * road_yield),
                "NextRoadNLL": (float(values["next_road_nll"] - math.log(road_yield))
                                if road_yield else math.inf),
            }
            for metric, value in values_to_add.items():
                key = (method, router, metric)
                if key in seen:
                    continue
                added.append({"dataset": "beijing", "batch": "batch_001",
                              "M": method, "R": router, "metric": metric,
                              "value": value, "status": "VALID",
                              "source": f"road_choice_metrics:{metrics_dir / 'metrics.json'}"})
                seen.add(key)
    rows.extend(added)
    fields = ["dataset", "batch", "M", "R", "metric", "value", "status", "source"]
    extras = sorted({key for row in rows for key in row if key not in fields})
    fields.extend(extras)
    temporary = table_path.with_suffix(table_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(table_path)
    (table_path.parent / "metrics_long.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "classification": "ROAD_CHOICE_EVALUATION_NO_SYNTHESIS",
        "sources": source_records,
        "added_rows": len(added),
        "metrics": ["RoadYield", "RC-CPC", "RC-NDCG", "NextRoadAcc", "NextRoadNLL"],
        "not_inferred": ["BTF", "EdgeCPC", "TurnCPC", "FamilyCPC"],
    }
    (table_path.parent / "road_choice_metrics_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"added_rows": len(added), "total_rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()

"""Merge edge-ID route metrics into the reproducibility long table.

The edge-ID evaluator is authoritative for road-object metrics of statistical
M x R cells.  This tool replaces only an existing lower-priority
``cell_evaluation`` value for the same (M, R, metric), or appends a missing
metric.  It never touches native MTR-DFR/MTNet rows and never changes metrics
that are not present in the edge-ID file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROAD_METRICS = {
    "RoadYield", "BTF", "RC-CPC", "EdgeCPC", "TurnCPC", "FamilyCPC",
    "EdgeRecall", "EdgePrecision", "EdgeF1", "TurnRecall", "TurnPrecision",
    "TurnF1", "EdgeIoU", "TurnIoU", "BranchCPC", "ExitAcc", "ODPF96",
    "ODPF384",
}
NATIVE_METHODS = {"MTR-DFR", "MTNet", "DPMM", "PUTS"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--edge-metrics", type=Path, required=True)
    args = parser.parse_args()

    table_path = args.table.resolve()
    edge_path = args.edge_metrics.resolve()
    rows = list(csv.DictReader(table_path.open(encoding="utf-8", newline="")))
    for row in rows:
        row.setdefault("source", "cell_evaluation")
    edge_rows = list(csv.DictReader(edge_path.open(encoding="utf-8", newline="")))

    index = {(row["M"], row["R"], row["metric"]): i for i, row in enumerate(rows)}
    replaced = 0
    appended = 0
    skipped_native = 0
    skipped_nonroad = 0
    for incoming in edge_rows:
        metric = incoming["metric"]
        method = incoming["M"]
        if metric not in ROAD_METRICS:
            skipped_nonroad += 1
            continue
        if method in NATIVE_METHODS:
            skipped_native += 1
            continue
        key = (method, incoming["R"], metric)
        incoming = {
            "dataset": incoming.get("dataset", "beijing"),
            "batch": incoming.get("batch", "batch_001"),
            "M": method,
            "R": incoming["R"],
            "metric": metric,
            "value": incoming["value"],
            "status": incoming.get("status", "VALID"),
            "source": "edge_id_route_metrics",
        }
        if key in index:
            old = rows[index[key]]
            if old.get("source", "cell_evaluation") == "edge_id_route_metrics":
                continue
            old_source = old.get("source", "cell_evaluation")
            # Native results are protected even if a malformed edge file uses
            # a native method name (the guard above is intentionally explicit).
            if old_source.startswith("native_scores:"):
                skipped_native += 1
                continue
            rows[index[key]] = incoming
            replaced += 1
        else:
            index[key] = len(rows)
            rows.append(incoming)
            appended += 1

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
        "classification": "EDGE_ID_ROUTE_METRICS_NO_SYNTHESIS",
        "edge_metrics": str(edge_path),
        "edge_metrics_sha256": sha256(edge_path),
        "replacement_policy": "edge_id_route_metrics replaces cell_evaluation only for listed road metrics",
        "protected_native_methods": sorted(NATIVE_METHODS),
        "replaced_rows": replaced,
        "appended_rows": appended,
        "skipped_native_rows": skipped_native,
        "skipped_nonroad_rows": skipped_nonroad,
    }
    (table_path.parent / "edge_route_metrics_merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"replaced": replaced, "appended": appended,
                      "skipped_native": skipped_native,
                      "skipped_nonroad": skipped_nonroad,
                      "total_rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()

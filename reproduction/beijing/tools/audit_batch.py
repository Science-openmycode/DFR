"""Create a truthful, manifest-based audit for one reproducibility batch."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    root = args.batch.resolve()
    prepared = root.parent.parent / "prepared_data"  # usually overridden below
    measurements = list((root / "synthetic_data" / "measurements").glob("*/beijing/batch_001/measurement_manifest.json"))
    route_manifests = list((root / "data_results").rglob("route_manifest.json"))
    valid_routes = []
    for path in route_manifests:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") in {"VALID", "registered_existing_route"}:
            valid_routes.append({"path": str(path), "M": record.get("M", path.parent.parent.name),
                                 "R": record.get("R", path.parent.name), "status": record.get("status"),
                                 "records": record.get("records")})
    table = root / "data_results" / "beijing" / "batch_001" / "metrics_long.csv"
    metric_rows = list(csv.DictReader(table.open(encoding="utf-8", newline=""))) if table.is_file() else []
    missing = json.loads((table.parent / "missing_cells.json").read_text(encoding="utf-8")) if (table.parent / "missing_cells.json").is_file() else []
    audit = {
        "schema_version": 1,
        "classification": "LOCAL_REPRO_BATCH_AUDIT",
        "batch": str(root),
        "measurement_methods": [p.parent.parent.parent.name for p in measurements],
        "measurement_manifest_count": len(measurements),
        "route_manifest_count": len(route_manifests),
        "valid_or_registered_route_cells": len(valid_routes),
        "route_cells": valid_routes,
        "metric_row_count": len(metric_rows),
        "metric_status_counts": {status: sum(1 for row in metric_rows if row.get("status") == status)
                                  for status in sorted({row.get("status") for row in metric_rows})},
        "missing_cells": missing,
        "plots": sorted(str(p) for p in (root / "plotting").rglob("*.png")),
        "no_fabricated_values": True,
        "note": "This audit counts only manifests and tables on disk; it does not infer missing MM2, DPMM, MTNet, or MTR-DFR cells.",
    }
    out = root / "full_batch_audit.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "route_cells": len(valid_routes), "metric_rows": len(metric_rows), "missing": len(missing)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

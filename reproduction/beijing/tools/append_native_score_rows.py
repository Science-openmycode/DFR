"""Append audited native-release scores to a batch long table.

Native road generators do not have an MxR coordinate transcript.  Their road
scores therefore come from the method's frozen native scorer, not from a
second FMM/STMatch pass.  This small idempotent utility records only numeric
fields that are actually present in ``scores.json``; all other 48-column cells
remain absent and are rendered as MISSING by the plotter.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DIRECT_FIELDS = {
    "Grid", "Trip", "Len", "DemandFid", "RoadYield", "DirValid",
    "WitnessValid", "BTF", "RC-CPC", "RC-NDCG", "NextRoadAcc",
    "NextRoadNLL", "NativeWitnessValid", "CompletionRate",
}


def read_score(path: Path) -> tuple[str, dict[str, float], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    method = str(payload.get("M") or payload.get("method") or "")
    if not method:
        raise ValueError(f"native score has no M/method: {path}")
    values: dict[str, float] = {}
    for key, value in payload.items():
        if key in DIRECT_FIELDS and isinstance(value, (int, float)):
            values[key] = float(value)
    # The frozen native scores call this quantity RoadYield.  It is the
    # completion fraction of accepted complete routes, not a guessed road
    # coverage score.  Preserve the distinction in the manifest/source field.
    if "RoadYield" in values and "CompletionRate" not in values:
        values["CompletionRate"] = values["RoadYield"]
    return method, values, payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--score", type=Path, action="append", required=True)
    p.add_argument("--dataset", default="beijing")
    p.add_argument("--batch", default="batch_001")
    args = p.parse_args()

    results = args.results.resolve()
    rows: list[dict[str, str]] = []
    if results.exists():
        with results.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    fieldnames = ["dataset", "batch", "M", "R", "metric", "value", "status", "source"]
    # Accept older tables without a source column and normalize them.
    for row in rows:
        row.setdefault("source", "cell_evaluation")
    methods = set()
    appended = []
    for raw in args.score:
        method, values, payload = read_score(raw.resolve())
        methods.add(method)
        # Make the operation idempotent when a batch is regenerated.
        rows = [r for r in rows if not (r.get("M") == method and r.get("R") == "Native")]
        for metric, value in values.items():
            appended.append({
                "dataset": args.dataset,
                "batch": args.batch,
                "M": method,
                "R": "Native",
                "metric": metric,
                "value": repr(value),
                "status": "VALID",
                "source": f"native_scores:{raw}",
            })
    rows.extend(appended)
    results.parent.mkdir(parents=True, exist_ok=True)
    with results.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path = results.with_suffix(".json")
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(results), "native_methods": sorted(methods), "appended_rows": len(appended), "total_rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

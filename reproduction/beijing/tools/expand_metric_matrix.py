"""Rectangularize the frozen 27x48 experiment ledger.

This utility deliberately does not infer unavailable metrics.  It expands the
observed long table to every frozen row/column pair and leaves an unavailable
cell as ``MISSING``.  The only aliases are labels whose evaluator definition
is identical (for example ``Grid`` and ``grid_density_jsd``).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


EXACT_ALIASES = {
    "Grid": "grid_density_jsd",
    "Trip": "trip_error",
    "Len": "path_length_jsd",
    "DirValid": "directed_road_validity",
}


def _row_label(item: dict, native_rows: set[str]) -> str:
    measurement = str(item.get("M", ""))
    router = str(item.get("R", ""))
    return measurement if measurement in native_rows else f"{measurement} + {router}"


def _load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def expand_table(spec_path: Path, source_path: Path) -> list[dict]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    rows = _load_rows(source_path)
    frozen_rows = list(spec.get("rows", []))
    columns = list(spec.get("columns", []))
    if not frozen_rows or not columns:
        raise ValueError("spec must define non-empty rows and columns")
    native = set(spec.get("native_rows", []))

    observed: dict[tuple[str, str], dict] = {}
    for item in rows:
        row = item.get("row") or _row_label(item, native)
        metric = str(item.get("metric", ""))
        if not row or not metric:
            continue
        key = (row, metric)
        if key in observed:
            raise ValueError(f"duplicate observed cell: {row}/{metric}")
        observed[key] = item

    expanded: list[dict] = []
    for row in frozen_rows:
        for column in columns:
            item = observed.get((row, column))
            source_metric = column
            if item is None:
                source_metric = EXACT_ALIASES.get(column, column)
                item = observed.get((row, source_metric))
            if item is not None:
                expanded.append({
                    "row": row,
                    "column": column,
                    "metric": column,
                    "value": item.get("value", ""),
                    "status": item.get("status", "VALID"),
                    "source": item.get("source", "unknown"),
                    "source_metric": source_metric,
                })
            else:
                expanded.append({
                    "row": row,
                    "column": column,
                    "metric": column,
                    "value": "",
                    "status": "MISSING",
                    "source": "not_computed",
                    "source_metric": "",
                })
    return expanded


def write_rows(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["row", "column", "metric", "value", "status", "source", "source_metric"]
    tmp = output.with_name(output.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand an observed ledger to the frozen 27x48 grid.")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = expand_table(args.spec.resolve(), args.source.resolve())
    write_rows(rows, args.output.resolve())
    missing = sum(row["status"] == "MISSING" for row in rows)
    print(f"wrote {len(rows)} cells ({missing} MISSING) to {args.output.resolve()}")


if __name__ == "__main__":
    main()


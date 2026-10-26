from __future__ import annotations

VALID_STATES = {"VALID", "ZERO", "NA", "MISSING", "INVALID"}


def validate_row(row: dict) -> None:
    required = {"dataset", "batch", "M", "R", "metric", "value", "status"}
    missing = required.difference(row)
    if missing:
        raise ValueError(f"missing result fields: {sorted(missing)}")
    if row["status"] not in VALID_STATES:
        raise ValueError(f"unknown result status: {row['status']}")

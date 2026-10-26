"""Compute the road-choice metrics from edge-ID route objects.

This evaluator intentionally consumes route objects whose ``cpath`` contains
public edge IDs.  It uses the public metric cache keyed by those edge IDs and
never merges its node IDs with the prepared network node namespace.  This is
the safe path for FMM/STMatch/MM2 outputs; coordinate-only/native node routes
must use their own native scorer instead.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import pickle
import os
import time
from pathlib import Path


def _load(path: Path):
    with gzip.open(path, "rb") as handle:
        return pickle.load(handle)


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def score_pair(real_path: Path, synthetic_path: Path, cache_path: Path) -> dict[str, float]:
    # The legacy evaluator already implements the frozen metric definitions.
    # Import it only after loading paths so this tool remains usable as a CLI.
    import sys
    legacy_eval = Path(os.environ.get('DFR_LEGACY_ROOT', str(Path(__file__).resolve().parents[1] / 'legacy'))) / 'evaluation'
    if str(legacy_eval) not in sys.path:
        sys.path.insert(0, str(legacy_eval))
    from route_metric_core import evaluate_routes, load_pickle, normalize_routes, route_counters

    cache = load_pickle(cache_path)
    real = normalize_routes(load_pickle(real_path), cache)
    synthetic = normalize_routes(load_pickle(synthetic_path), cache)
    reference = route_counters(real, cache)
    return evaluate_routes(synthetic, real, cache, reference)


def _status(value: object) -> tuple[str, str]:
    if value is None:
        return "NA", ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA", ""
    if number != number or number in (float("inf"), float("-inf")):
        return "NA", ""
    return ("ZERO" if number == 0 else "VALID"), repr(number)


def _cell_files(batch_root: Path):
    root = batch_root / "data_results"
    for path in sorted(root.glob("*/batch_001/*/*/synthetic_routes.pkl.gz")):
        # The direct glob excludes nested/incomplete MM2 chunk directories.
        parts = path.parts
        yield parts[-3], parts[-2], path


def compute(batch_root: Path, real_path: Path, cache_path: Path, output: Path) -> dict:
    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    dataset = "beijing"
    batch = "batch_001"
    for measurement, router, path in _cell_files(batch_root):
        values = score_pair(real_path, path, cache_path)
        for metric, value in sorted(values.items()):
            status, serialized = _status(value)
            rows.append({
                "dataset": dataset,
                "batch": batch,
                "M": measurement,
                "R": router,
                "metric": metric,
                "value": serialized,
                "status": status,
                "source": "edge_id_route_metrics",
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    fields = ["dataset", "batch", "M", "R", "metric", "value", "status", "source"]
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(output)
    manifest = {
        "schema_version": 1,
        "classification": "EDGE_ID_ROUTE_METRICS_NOT_A_DP_RELEASE",
        "batch_root": str(batch_root.resolve()),
        "real_routes": {"path": str(real_path.resolve()), "sha256": _hash(real_path)},
        "metric_cache": {"path": str(cache_path.resolve()), "sha256": _hash(cache_path)},
        "route_cells": len({(row["M"], row["R"]) for row in rows}),
        "rows": len(rows),
        "elapsed_sec": round(time.perf_counter() - started, 6),
        "output": {"path": str(output.resolve()), "sha256": _hash(output)},
        "node_namespace_policy": "edge_ids_only; legacy metric-cache node IDs are never merged with prepared network node IDs",
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Score saved cpath edge-ID route objects.")
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--real-routes", type=Path, required=True)
    parser.add_argument("--metric-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compute(args.batch_root.resolve(), args.real_routes.resolve(), args.metric_cache.resolve(), args.output.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


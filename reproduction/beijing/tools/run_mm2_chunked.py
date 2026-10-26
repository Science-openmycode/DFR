"""Run the public MM2-MDP router in resumable complete-M chunks.

The normal MM2 adapter deliberately runs one measurement file as one cell.  On
Windows, a very large coordinate transcript can make the upstream executable
consume excessive memory or run for hours.  This helper keeps the *cell*
semantics (all M slots are required and merged before the cell is published)
while splitting only the external MM2 invocation into fixed, auditable chunks.
It never reads the private/reference trajectory and never fills a failed route.
"""
from __future__ import annotations

import argparse
import gzip
import json
import pickle
import shutil
import sys
from collections import Counter
from pathlib import Path

# Allow direct ``python tools/run_mm2_chunked.py`` from the isolated root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from algorithms.routers.mm2_mdp_adapter import (
    _edge_cache,
    _read_mm2_rows,
    convert_rows,
    load_pickle,
    run_mm2,
    sha256,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--edge-cache", type=Path, required=True)
    parser.add_argument("--input-srs", default="EPSG:4326")
    parser.add_argument("--tracks-srs", default="EPSG:32650")
    parser.add_argument("--network-srs", default="EPSG:32650")
    parser.add_argument("--max-points", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--resume", action="store_true", help="reuse completed MM2 chunks and finalize existing matches.csv")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.out_dir.exists() and not args.resume:
        raise SystemExit(f"refusing to overwrite output: {args.out_dir}")
    raw = load_pickle(args.measurement)
    if not isinstance(raw, (list, tuple)):
        raise SystemExit("measurement must be a list/tuple of trajectories")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    chunks_root = args.out_dir / "mm2_batches"
    chunks_root.mkdir(exist_ok=True)
    merged: list[dict] = []
    batch_manifests: list[dict] = []
    reasons: Counter[str] = Counter()

    for start in range(0, len(raw), args.batch_size):
        stop = min(len(raw), start + args.batch_size)
        batch_name = f"{start:06d}_{stop:06d}"
        batch_dir = chunks_root / batch_name
        batch_dir.mkdir(exist_ok=True)
        batch_measurement = batch_dir / "measurement.pkl"
        if not batch_measurement.exists():
            with batch_measurement.open("wb") as handle:
                pickle.dump(list(raw[start:stop]), handle, protocol=pickle.HIGHEST_PROTOCOL)
        route_output = batch_dir / "run" / "synthetic_routes.pkl.gz"
        if route_output.exists():
            with gzip.open(route_output, "rb") as handle:
                routes = pickle.load(handle)
            manifest_path = batch_dir / "run" / "route_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"reasons": {}}
        elif args.resume and (batch_dir / "run" / "mm2_run" / "matches.csv").exists():
            # The external binary may have finished before the Python process
            # was interrupted while parsing/serializing.  Finalize that raw
            # CSV without running the expensive binary again.
            rows = _read_mm2_rows(batch_dir / "run" / "mm2_run" / "matches.csv")
            routes, reasons_local = convert_rows(rows, _edge_cache(args.edge_cache), stop - start)
            route_output.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(route_output, "wb") as handle:
                pickle.dump(routes, handle, protocol=pickle.HIGHEST_PROTOCOL)
            manifest = {
                "schema_version": 1,
                "kind": "route_cell_chunk",
                "router": "MM2-MDP",
                "status": "VALID",
                "route_generation": "executed_public_mm2_value_iteration_chunked",
                "raw_source_used": False,
                "measurement": str(batch_measurement.resolve()),
                "measurement_sha256": sha256(batch_measurement),
                "public_mm2_executable": str(args.executable.resolve()),
                "public_mm2_executable_sha256": sha256(args.executable),
                "public_mm2_network": str(args.network.resolve()),
                "public_edge_cache": str(args.edge_cache.resolve()),
                "public_edge_cache_sha256": sha256(args.edge_cache),
                "records": len(routes),
                "reasons": reasons_local,
                "output": str(route_output.resolve()),
                "output_sha256": sha256(route_output),
                "resumed_from_matches_csv": True,
            }
            (batch_dir / "run" / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            manifest = run_mm2(
                batch_measurement,
                batch_dir / "run",
                executable=args.executable,
                network=args.network,
                edge_cache=args.edge_cache,
                input_srs=args.input_srs,
                tracks_srs=args.tracks_srs,
                network_srs=args.network_srs,
                max_points=args.max_points,
                seed=args.seed,
            )
            with gzip.open(route_output, "rb") as handle:
                routes = pickle.load(handle)
        if len(routes) != stop - start:
            raise RuntimeError(f"MM2 chunk {batch_name} returned {len(routes)} routes, expected {stop-start}")
        for route in routes:
            route["source_index"] = int(route["source_index"]) + start
            merged.append(route)
        for key, value in manifest.get("reasons", {}).items():
            reasons[key] += int(value)
        batch_manifests.append({"start": start, "stop": stop, "manifest": str((batch_dir / "run" / "route_manifest.json").resolve())})

    merged.sort(key=lambda route: int(route["source_index"]))
    if [int(route["source_index"]) for route in merged] != list(range(len(raw))):
        raise RuntimeError("merged MM2 chunks do not cover every M slot exactly once")
    output = args.out_dir / "synthetic_routes.pkl.gz"
    with gzip.open(output, "wb") as handle:
        pickle.dump(merged, handle, protocol=pickle.HIGHEST_PROTOCOL)
    final = {
        "schema_version": 1,
        "kind": "route_cell",
        "router": "MM2-MDP",
        "status": "VALID",
        "route_generation": "executed_public_mm2_value_iteration_chunked",
        "raw_source_used": False,
        "measurement": str(args.measurement.resolve()),
        "measurement_sha256": sha256(args.measurement),
        "public_mm2_executable": str(args.executable.resolve()),
        "public_mm2_executable_sha256": sha256(args.executable),
        "public_mm2_network": str(args.network.resolve()),
        "public_edge_cache": str(args.edge_cache.resolve()),
        "public_edge_cache_sha256": sha256(args.edge_cache),
        "input_srs": args.input_srs,
        "tracks_srs": args.tracks_srs,
        "network_srs": args.network_srs,
        "max_points": args.max_points,
        "batch_size": args.batch_size,
        "seed": args.seed,
        "records": len(merged),
        "reasons": dict(reasons),
        "batches": batch_manifests,
        "output": str(output.resolve()),
        "output_sha256": sha256(output),
    }
    (args.out_dir / "route_manifest.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "route_generation.log").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

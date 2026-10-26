"""Adapters for the existing public FMM/STMatch implementation.

The legacy matcher is imported only as an implementation dependency.  The
adapter passes it coordinates from one M output and public road files; it
never passes the reference/raw trajectories.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib
import json
import os
import pickle
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pickle(path: Path):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as handle:
        return pickle.load(handle)


def _load_legacy_run_fmm(legacy_root: Path):
    evaluation = legacy_root / "evaluation" / "evaluation"
    if not evaluation.is_dir():
        raise FileNotFoundError(f"legacy evaluation package missing: {evaluation}")
    sys.path.insert(0, str(evaluation))
    try:
        module = importlib.import_module("metric_suites.road_route")
    finally:
        # Keep this adapter's import path deterministic for repeated cells.
        try:
            sys.path.remove(str(evaluation))
        except ValueError:
            pass
    return module.run_fmm


def run_public_match(
    measurement: Path,
    out_dir: Path,
    *,
    matcher: str,
    network: Path,
    executable: Path,
    edge_cache: Path,
    legacy_root: Path,
    ubodt: Path | None = None,
    runtime_dir: Path | None = None,
    ubodt_executable: Path | None = None,
    max_points: int = 32,
    radius_m: float = 200.0,
    gps_error_m: float = 50.0,
    candidates: int = 8,
    min_observation_share: float = 0.95,
) -> dict:
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite route output: {out_dir}")
    out_dir.mkdir(parents=True)
    # Keep a machine-readable failure record even when the external matcher
    # is unavailable or exits non-zero.  This is important for a matrix run:
    # an external-resource failure is INVALID, never an implicit zero or a
    # missing cell with another method's value copied into it.
    def write_invalid(error: BaseException, invocation: object | None = None) -> None:
        manifest = {
            "schema_version": 1,
            "kind": "route_cell",
            "router": matcher,
            "route_generation": f"executed_public_{matcher.lower()}",
            "status": "INVALID",
            "raw_source_used": False,
            "measurement": str(measurement.resolve()),
            "measurement_sha256": sha256(measurement) if measurement.is_file() else None,
            "public_network": str(network.resolve()),
            "public_network_sha256": sha256(network) if network.is_file() else None,
            "public_executable": str(executable.resolve()),
            "public_executable_sha256": sha256(executable) if executable.is_file() else None,
            "edge_cache": str(edge_cache.resolve()),
            "edge_cache_sha256": sha256(edge_cache) if edge_cache.is_file() else None,
            "ubodt": str(ubodt.resolve()) if ubodt else None,
            "ubodt_sha256": sha256(ubodt) if ubodt and ubodt.is_file() else None,
            "runtime_dir": str(runtime_dir.resolve()) if runtime_dir else None,
            "error_type": type(error).__name__,
            "error": str(error),
            "invocation": invocation,
        }
        (out_dir / "route_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    try:
        if matcher not in {"FMM", "STMatch"}:
            raise ValueError(f"unsupported public matcher: {matcher}")
        for path, label in ((measurement, "measurement"), (network, "public network"), (executable, f"{matcher} executable"), (edge_cache, "edge cache")):
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")
        if matcher == "FMM" and ubodt is None:
            raise ValueError("FMM requires --ubodt generated for the exact public network")
        if ubodt is not None and not ubodt.exists():
            raise FileNotFoundError(f"UBODT not found: {ubodt}")
    except Exception as error:
        write_invalid(error)
        raise
    try:
        trajectories = load_pickle(measurement)
        if not isinstance(trajectories, (list, tuple)) or not trajectories:
            raise ValueError("measurement must contain a non-empty list of trajectories")
    except Exception as error:
        write_invalid(error)
        raise
    try:
        run_fmm = _load_legacy_run_fmm(legacy_root)
        # The legacy matcher still accepts a ``runtime_dir`` positional
        # argument, but its Windows branch expects gdal204.dll and
        # boost_serialization.dll.  The Linux build links against the public
        # libFMMLIB.so beside the executable; passing the Windows runtime
        # directory on POSIX makes the legacy helper reject an otherwise
        # valid Linux invocation.  Keep the manifest's runtime_dir unchanged,
        # but pass it to the legacy implementation only on Windows.
        legacy_runtime_dir = runtime_dir if os.name == "nt" else None
        records, invocation = run_fmm(
            list(trajectories), network, ubodt if matcher == "FMM" else None,
            executable, ubodt_executable if matcher == "FMM" else None,
            legacy_runtime_dir, max_points, radius_m, gps_error_m, candidates,
            min_observation_share, None, True,
        )
    except Exception as error:
        write_invalid(error)
        raise
    if len(records) != len(trajectories):
        error = RuntimeError(f"{matcher} returned {len(records)} records for {len(trajectories)} M slots")
        write_invalid(error, invocation)
        raise error
    routes = []
    reasons: dict[str, int] = {}
    for index, record in enumerate(records):
        accepted = bool(record.accepted)
        if not accepted:
            reason = "rejected"
        elif not record.connected:
            reason = "disconnected"
        elif not record.cpath:
            reason = "empty"
        else:
            reason = "accepted"
        reasons[reason] = reasons.get(reason, 0) + 1
        routes.append({
            "source_index": index,
            "accepted": accepted,
            "cpath": tuple(int(value) for value in record.cpath) if accepted else [],
            "opath": tuple(int(value) for value in record.opath) if accepted else [],
            "residual_m": tuple(float(value) for value in record.residual_m) if accepted else [],
            "connected": bool(record.connected),
            "observation_share": float(record.observation_share),
            "reason": reason,
        })
    output = out_dir / "synthetic_routes.pkl.gz"
    with gzip.open(output, "wb", compresslevel=6) as handle:
        pickle.dump(routes, handle, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {
        "schema_version": 1,
        "kind": "route_cell",
        "router": matcher,
        "route_generation": f"executed_public_{matcher.lower()}",
        "status": "VALID",
        "raw_source_used": False,
        "measurement": str(measurement.resolve()),
        "measurement_sha256": sha256(measurement),
        "public_network": str(network.resolve()),
        "public_network_sha256": sha256(network),
        "public_executable": str(executable.resolve()),
        "public_executable_sha256": sha256(executable),
        "edge_cache": str(edge_cache.resolve()),
        "edge_cache_sha256": sha256(edge_cache),
        "ubodt": str(ubodt.resolve()) if ubodt else None,
        "ubodt_sha256": sha256(ubodt) if ubodt else None,
        "runtime_dir": str(runtime_dir.resolve()) if runtime_dir else None,
        "parameters": {"max_points": max_points, "radius_m": radius_m, "gps_error_m": gps_error_m, "candidates": candidates, "min_observation_share": min_observation_share, "route_only": True},
        "protocol": "historical_public_route_completion_v1",
        "records": len(routes),
        "reasons": reasons,
        "invocation": invocation,
        "output": str(output),
        "output_sha256": sha256(output),
    }
    (out_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest

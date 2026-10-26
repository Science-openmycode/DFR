"""Evaluation-only public edge-ID geometry expansion; never match or repair roads.

The network geometry is directed source -> target, following the public network
builder. A bad edge or join invalidates its entire route slot. Empty and invalid
slots remain explicit (0, 2) arrays. Output coordinates use (latitude, longitude).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import time
from collections import Counter
from datetime import datetime, timezone
from numbers import Integral
from pathlib import Path

import numpy as np


def _binding(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1 << 20), b""):
            digest.update(data)
    return {"path": path.as_posix(), "sha256": digest.hexdigest()}


def _integer(value):
    return isinstance(value, Integral) and not isinstance(value, bool)


def stage(*, routes, network, out_dir, edge_cache=None):
    """Expand an explicit list of edge-ID routes into a new staging directory."""
    import geopandas as gpd

    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    routes, network, out_dir = Path(routes).resolve(), Path(network).resolve(), Path(out_dir).resolve()
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite native coordinate staging: {out_dir}")
    opener = gzip.open if routes.suffix.lower() == ".gz" else open
    with opener(routes, "rb") as handle:
        raw = pickle.load(handle)
    if not isinstance(raw, (list, tuple)):
        raise ValueError("native edge-ID routes must be a list/tuple of slots")
    route_binding = _binding(routes)
    network_files = [_binding(p) for p in sorted(network.parent.glob(network.stem + ".*")) if p.is_file()]
    cache_binding = _binding(edge_cache) if edge_cache is not None else None
    frame = gpd.read_file(network)
    required = {"id", "source", "target", "geometry"}
    if not required.issubset(frame.columns):
        raise ValueError(f"public network missing columns {sorted(required - set(frame.columns))}")
    if frame.crs is None:
        raise ValueError("public network CRS is required")
    if frame["id"].duplicated().any():
        raise ValueError("duplicate public network edge IDs are ambiguous")
    frame = frame.to_crs("EPSG:4326")
    by_id = {}
    for row in frame[["id", "source", "target", "geometry"]].itertuples(index=False):
        if not all(_integer(v) for v in (row.id, row.source, row.target)):
            raise ValueError("network id/source/target must be integer IDs")
        problem = None
        coords = None
        if row.geometry is None or row.geometry.is_empty:
            problem = "empty_geometry"
        elif row.geometry.geom_type != "LineString":
            problem = "unsupported_geometry"
        else:
            xy = np.asarray(row.geometry.coords, dtype=float)
            if len(xy) < 2 or not np.isfinite(xy[:, :2]).all():
                problem = "invalid_geometry"
            else:
                coords = np.column_stack((xy[:, 1], xy[:, 0]))
        by_id[int(row.id)] = (int(row.source), int(row.target), coords, problem)
    coordinates = []
    reasons = Counter()
    invalid_slots = []
    edge_occurrences = 0
    for slot, route in enumerate(raw):
        error = None
        if not isinstance(route, (list, tuple)) or any(not _integer(e) for e in route):
            error = {"slot": slot, "reason": "invalid_route_schema"}
        elif not route:
            reasons["empty_native_slot"] += 1
            coordinates.append(np.empty((0, 2), dtype=float))
            continue
        points = []
        previous_target = None
        if error is None:
            edge_occurrences += len(route)
            for position, value in enumerate(route):
                edge_id = int(value)
                edge = by_id.get(edge_id)
                reason = None
                if edge is None:
                    reason = "missing_edge_id"
                else:
                    source, target, coords, problem = edge
                    if problem:
                        reason = problem
                    elif previous_target is not None and previous_target != source:
                        reason = "network_disconnected"
                    elif points and not np.array_equal(points[-1], coords[0]):
                        reason = "geometry_disconnected"
                if reason:
                    error = {"slot": slot, "reason": reason, "edge_position": position, "edge_id": edge_id}
                    break
                # Preserve internal/repeated coordinates. Remove exactly the
                # single common endpoint between consecutive directed edges.
                points.extend(coords if not points else coords[1:])
                previous_target = target
        if error is not None:
            invalid_slots.append(error)
            reasons[error["reason"]] += 1
            coordinates.append(np.empty((0, 2), dtype=float))
        else:
            reasons["valid"] += 1
            coordinates.append(np.asarray(points, dtype=float).reshape((-1, 2)))
    out_dir.mkdir(parents=True, exist_ok=False)
    output = out_dir / "coordinates.pkl"
    with output.open("wb") as handle:
        pickle.dump(coordinates, handle, protocol=pickle.HIGHEST_PROTOCOL)
    record = {
        "schema": "road-route-coordinate-derivation-v1",
        "classification": "EVALUATION_ONLY", "formal_output": False,
        "derivation_mode": "native-public-edge-ID-directed-geometry",
        "representation": "edge-ids", "record_count": len(coordinates),
        "nonempty_slot_count": reasons["valid"], "empty_native_slot_count": reasons["empty_native_slot"],
        "invalid_slot_count": len(invalid_slots), "reason_counts": dict(reasons), "invalid_slots": invalid_slots,
        "edge_occurrences": edge_occurrences,
        "coordinates": _binding(output), "route_source": route_binding,
        "public_network": _binding(network), "network_files": network_files,
        "stager": _binding(Path(__file__)),
        "raw_source_used": False, "rematched": False, "fills_gaps": False,
        "direction": "public network geometry in declared source->target direction; no reversal",
        "join_policy": "exact directed-node and endpoint continuity; drop one shared endpoint only",
        "invalid_slot_policy": "empty the entire slot, never concatenate partial valid pieces",
        "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - timer,
    }
    if cache_binding is not None:
        record["edge_cache"] = cache_binding
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    (out_dir / "coordinates.pkl.manifest.json").write_text(text, encoding="utf-8")
    (out_dir / "manifest.json").write_text(text, encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--edge-cache", type=Path, help="optional hash binding required when scoring --road-routes")
    result = stage(**vars(parser.parse_args()))
    print(json.dumps({key: result[key] for key in ("record_count", "nonempty_slot_count", "invalid_slot_count", "reason_counts", "coordinates", "elapsed_seconds")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

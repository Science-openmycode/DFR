"""Evaluate saved roads only; never synthesize, route, fill gaps, or map-match.

The real reference must be explicit accepted/cpath edge records. Synthetic
representation is explicit, never inferred from coordinates or node values.
Real metrics are conditioned on valid real roads (as in the historical native
scorer), while every synthetic slot remains in the denominator, including a
self-reference run. Pickles must be trusted local experiment artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from numbers import Integral
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_BUNDLED = _ROOT/'legacy'
_LEGACY = Path(os.environ.get('DFR_LEGACY_ROOT', str(_BUNDLED)))
CORE_PATH = _LEGACY/'evaluation'/'route_metric_core.py'
REPRESENTATIONS = ("edge-ids", "edge-records", "node-pairs")


def _binding(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"path": path.as_posix(), "sha256": digest.hexdigest(),
            "bytes": path.stat().st_size}


def _integer(value, context):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{context}: expected integer ID, got {value!r}")
    return int(value)


def _sequence(value, context):
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{context}: expected list/tuple sequence")
    return value


def _edge_nodes(cache, context):
    if not isinstance(cache, dict) or not isinstance(cache.get("edge_nodes"), dict):
        raise ValueError(f"{context}: required edge_nodes mapping is missing")
    result = {}
    for key, value in cache["edge_nodes"].items():
        key = _integer(key, context)
        pair = _sequence(value, context)
        if len(pair) != 2:
            raise ValueError(f"{context}: expected directed node pair")
        result[key] = tuple(_integer(v, context) for v in pair)
    if not result:
        raise ValueError(f"{context}: empty edge_nodes mapping")
    return result


def _network_data(path, metric_edges):
    import geopandas as gpd

    frame = gpd.read_file(path)
    required = {"id", "source", "target", "length_m"}
    if not required.issubset(frame.columns):
        raise ValueError(f"network: missing columns {sorted(required - set(frame.columns))}")
    nodes, lengths = {}, {}
    for row in frame[["id", "source", "target", "length_m"]].itertuples(index=False):
        edge_id = _integer(row.id, "network edge")
        if edge_id not in metric_edges:
            continue
        if edge_id in nodes:
            raise ValueError(f"network: ambiguous duplicate edge ID {edge_id}")
        nodes[edge_id] = (_integer(row.source, "network source"),
                          _integer(row.target, "network target"))
        length = float(row.length_m)
        if not math.isfinite(length) or length < 0:
            raise ValueError(f"network: invalid length for edge {edge_id}")
        # Same public-edge length reduction as historical run_mr_experiment:
        # clamp to 1 mm and take shortest length if cache merges node pairs.
        pair = metric_edges[edge_id]
        length = max(length, 1e-3)
        if pair not in lengths or length < lengths[pair]:
            lengths[pair] = length
    missing = set(metric_edges).difference(nodes)
    if missing:
        raise ValueError(f"network: missing edge lengths/endpoints for IDs {sorted(missing)[:5]}")
    return nodes, lengths


def _connected(pairs):
    return all(left[1] == right[0] for left, right in zip(pairs, pairs[1:]))


def _convert(raw, representation, metric_edges, source_edges, physical_edges, label,
             canonical_pairs=None):
    raw = _sequence(raw, label)
    pair_ids = defaultdict(list)
    if source_edges is not None:
        for edge_id, pair in source_edges.items():
            pair_ids[pair].append(edge_id)
    routes = []
    counts = {"slots": len(raw), "valid_routes": 0, "empty_routes": 0,
              "rejected_routes": 0, "disconnected_routes": 0,
              "source_disconnected_routes": 0, "physical_disconnected_routes": 0,
              "metric_disconnected_routes": 0}
    for index, row in enumerate(raw):
        context = f"{label} slot {index}"
        accepted = True
        source_pairs = None
        if representation == "edge-records":
            if not isinstance(row, dict):
                raise ValueError(f"{context}: expected edge record")
            if "accepted" not in row or not isinstance(row["accepted"], bool):
                raise ValueError(f"{context}: accepted must be an explicit boolean")
            if "cpath" not in row:
                raise ValueError(f"{context}: cpath is required; node_sequence is not an edge-ID route")
            accepted = row["accepted"]
            ids = tuple(_integer(v, context) for v in _sequence(row["cpath"], context))
        elif representation == "edge-ids":
            ids = tuple(_integer(v, context) for v in _sequence(row, context))
        else:
            source_pairs = []
            ids = []
            for pair in _sequence(row, context):
                pair = _sequence(pair, context)
                if len(pair) != 2:
                    raise ValueError(f"{context}: expected directed node pair")
                pair = tuple(_integer(v, context) for v in pair)
                source_pairs.append(pair)
                candidates = pair_ids.get(pair, [])
                if not candidates:
                    raise ValueError(f"{context}: unknown source node pair {pair}")
                if len(candidates) != 1 and (canonical_pairs is None or pair not in canonical_pairs):
                    raise ValueError(f"{context}: ambiguous source node pair {pair}: {candidates[:5]}")
                edge_id = canonical_pairs[pair] if canonical_pairs is not None else candidates[0]
                if edge_id not in metric_edges:
                    raise ValueError(f"{context}: no common edge ID for source pair {pair}")
                ids.append(edge_id)
        missing = set(ids).difference(metric_edges)
        if missing:
            raise ValueError(f"{context}: unknown metric-cache edge IDs {sorted(missing)[:5]}")
        if not accepted:
            counts["rejected_routes"] += 1
            routes.append(())
            continue
        if not ids:
            counts["empty_routes"] += 1
            routes.append(())
            continue
        reason = None
        if source_pairs is not None and not _connected(source_pairs):
            reason = "source_disconnected_routes"
        elif physical_edges is not None and not _connected([physical_edges[e] for e in ids]):
            reason = "physical_disconnected_routes"
        pairs = tuple(metric_edges[e] for e in ids)
        if reason is None and not _connected(pairs):
            reason = "metric_disconnected_routes"
        if reason:
            counts[reason] += 1
            counts["disconnected_routes"] += 1
            routes.append(())
        else:
            counts["valid_routes"] += 1
            routes.append(pairs)
    return routes, counts


def evaluate_saved(*, real_routes, synthetic_routes, metric_cache, representation,
                   method, router, out, source_cache=None, network=None):
    """Score one saved cell, writing a new output directory without overwriting."""
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"refusing to overwrite evaluation directory: {out}")
    if representation not in REPRESENTATIONS:
        raise ValueError(f"unknown representation {representation!r}")
    if representation == "node-pairs" and source_cache is None:
        raise ValueError("node-pairs requires --source-cache")
    if representation != "node-pairs" and source_cache is not None:
        raise ValueError("--source-cache is only valid for node-pairs")
    spec = importlib.util.spec_from_file_location("saved_roads_metric_core", CORE_PATH)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    paths = {"real_routes": Path(real_routes), "synthetic_routes": Path(synthetic_routes),
             "metric_cache": Path(metric_cache)}
    if source_cache is not None:
        paths["source_cache"] = Path(source_cache)
    if network is not None:
        paths["network"] = Path(network)
    inputs = {name: _binding(path) for name, path in paths.items()}
    if network is not None and Path(network).suffix.lower() == ".shp":
        inputs["network_sidecars"] = [
            _binding(Path(network).with_suffix(suffix))
            for suffix in (".dbf", ".shx", ".prj", ".cpg")
            if Path(network).with_suffix(suffix).is_file()
        ]
    cache = core.load_pickle(paths["metric_cache"])
    edges = _edge_nodes(cache, "metric cache")
    for name in ("outdegree", "labels24", "labels96", "labels384"):
        if not isinstance(cache.get(name), dict):
            raise ValueError(f"metric cache: missing {name} mapping")
        if name.startswith("labels"):
            missing_nodes = {node for pair in edges.values() for node in pair}.difference(cache[name])
            if missing_nodes:
                raise ValueError(f"metric cache: {name} missing node labels {sorted(missing_nodes)[:5]}")
        else:
            missing_nodes = {pair[0] for pair in edges.values()}.difference(cache[name])
            if missing_nodes:
                raise ValueError(f"metric cache: outdegree missing source nodes {sorted(missing_nodes)[:5]}")
    source_edges = (_edge_nodes(core.load_pickle(paths["source_cache"]), "source cache")
                    if source_cache is not None else None)
    physical_edges, lengths = (_network_data(Path(network), edges)
                               if network is not None else (None, None))
    real, real_audit = _convert(core.load_pickle(paths["real_routes"]), "edge-records",
                                edges, None, physical_edges, "real")
    synthetic_raw = core.load_pickle(paths["synthetic_routes"])
    canonical = None
    if representation == 'node-pairs':
        import sys
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))
        from tools.convert_native_node_pairs import resolve_pairs
        used = {tuple(_integer(v, 'synthetic node pair') for v in _sequence(pair, 'synthetic node pair'))
                for row in _sequence(synthetic_raw, 'synthetic') for pair in _sequence(row, 'synthetic route')}
        canonical = resolve_pairs(source_edges, edges, network=network, required_pairs=used)
    synthetic, synthetic_audit = _convert(synthetic_raw,
                                          representation, edges, source_edges,
                                          physical_edges, "synthetic", canonical)
    # Historical native scores condition the reference, not the release slots.
    reference_roads = core.valid_routes(real, cache)
    if not reference_roads:
        raise ValueError("no valid real reference roads; refusing placeholder metrics")
    real_audit["reference_slots"] = len(reference_roads)
    real_audit["conditioning"] = "valid nonempty connected real roads only"
    reference = core.route_counters(reference_roads, cache)
    scoring_started = time.perf_counter()
    values = core.evaluate_routes(synthetic, reference_roads, cache, reference, lengths)
    scoring_seconds = time.perf_counter() - scoring_started
    statuses = {key: ("NA" if not math.isfinite(value) else "ZERO" if value == 0 else "VALID")
                for key, value in values.items()}
    serializable = {key: value if math.isfinite(value) else None for key, value in values.items()}
    out.mkdir(parents=True, exist_ok=False)
    json_path, csv_path = out / "metrics.json", out / "metrics.csv"
    json_path.write_text(json.dumps(serializable, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["M", "R", "metric", "value", "status", "source"])
        writer.writeheader()
        for key in sorted(values):
            writer.writerow({"M": method, "R": router, "metric": key,
                             "value": "" if serializable[key] is None else repr(values[key]),
                             "status": statuses[key], "source": "saved_road_evaluation"})
    manifest = {
        "schema_version": "saved-road-evaluation-v1", "classification": "EVALUATION_ONLY_NOT_A_DP_RELEASE",
        "method": method, "router": router, "representation": representation,
        "real_representation": "edge-records", "rematched": False, "gap_filling": False,
        "self_reference": inputs["real_routes"]["sha256"] == inputs["synthetic_routes"]["sha256"],
        "inputs": inputs, "metric_core": _binding(CORE_PATH), "evaluator": _binding(Path(__file__)),
        "representation_resolver": _binding(_ROOT/'tools/convert_native_node_pairs.py') if canonical is not None else None,
        "real": real_audit, "synthetic": synthetic_audit,
        "physical_connectivity_check": "public network source,target" if network is not None else "not supplied; cache connectivity only",
        "node_namespace_policy": "source node pairs -> common edge ID; parallel aliases require identical directed geometry, physical and metric endpoints; minimum alias ID -> metric-cache node pairs",
        "synthetic_denominator_policy": "all saved slots; empty/rejected/disconnected slots contribute zero road mass",
        "metric_count": len(values), "metric_status": statuses,
        "shape_length_policy": "historical run_mr_experiment: max(length_m,0.001), minimum per metric node pair" if network is not None else None,
        "outputs": {"metrics_json": _binding(json_path), "metrics_csv": _binding(csv_path)},
        "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "scoring_seconds": scoring_seconds, "elapsed_seconds": time.perf_counter() - timer,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("real-routes", "synthetic-routes", "metric-cache", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--representation", choices=REPRESENTATIONS, required=True)
    parser.add_argument("--source-cache", type=Path, help="required for node-pairs; explicit source namespace")
    parser.add_argument("--network", type=Path, help="public id/source/target/length_m network; enables five shape metrics")
    parser.add_argument("--method", required=True)
    parser.add_argument("--router", required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate_saved(**vars(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

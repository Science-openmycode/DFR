from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import geopandas as gpd

from route_metric_core import evaluate_routes, load_pickle, normalize_routes, route_counters, valid_routes
from experiment_contract import (validate_native_mr_cell, validate_real_reference,
                                validate_routing_source, validate_generation_source, POPULATIONS)


ROOT = Path(__file__).resolve().parents[1]

def rooted(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()

def binding(path, network):
    output_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    side = path.with_name(path.name.replace(".pkl.gz", ".manifest.json"))
    record = {"path": str(path), "sha256": output_hash}
    if side != path and side.is_file():
        metadata = json.loads(side.read_text(encoding="utf-8"))
        if metadata.get("output_sha256") != output_hash:
            raise ValueError(f"Route cache output hash mismatch: {path}")
        if metadata.get("network_sha256") != hashlib.sha256(network.read_bytes()).hexdigest():
            raise ValueError(f"Route cache network mismatch: {path}")
        record.update(cache_manifest=str(side), source_sha256=metadata.get("input_sha256"),
                      parameters=metadata.get("parameters"), record_count=metadata.get("record_count"))
    return record


def parse_item(text: str) -> tuple[str, str, Path]:
    try:
        label, value = text.split("=", 1)
        measurement, router = label.split("::", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected M::R=PATH") from exc
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return measurement, router, path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute an M-by-R matrix from saved synthetic route objects."
    )
    parser.add_argument("--real-routes", required=True)
    parser.add_argument("--real-source", required=True)
    parser.add_argument("--population", choices=POPULATIONS, default="full-corpus")
    parser.add_argument("--measurement", action="append", default=[], help="NAME=original coordinate release")
    parser.add_argument("--synthesis-lineage", action="append", default=[], help="Native NAME=executed generation record")
    parser.add_argument("--edge-cache", default=str(ROOT / "public_assets" / "ordered_portal_route_cache.pkl.gz"))
    parser.add_argument("--network", default=str(ROOT / "public_assets" / "beijing_network" / "network.shp"),
                        help="public directed road shapefile with id and length_m")
    parser.add_argument("--route", action="append", type=parse_item, default=[], help="M::R=PATH; repeat")
    parser.add_argument("--route-dir", help="Load this route directory; defaults to packaged routes only when no --route is supplied")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    cache_path, network_path, real_path = rooted(args.edge_cache), rooted(args.network), rooted(args.real_routes)
    cache = load_pickle(cache_path)
    input_audit = validate_real_reference(real_path, rooted(args.real_source), cache,
                                          args.population, network_path)
    pairs = [item.split("=", 1) for item in args.measurement]
    if any(len(item) != 2 for item in pairs) or len(dict(pairs)) != len(pairs):
        parser.error("--measurement expects unique NAME=PATH entries")
    measurements = {name: rooted(path) for name, path in pairs}
    lineage_pairs = [item.split("=", 1) for item in args.synthesis_lineage]
    if any(len(item) != 2 for item in lineage_pairs) or len(dict(lineage_pairs)) != len(lineage_pairs):
        parser.error("--synthesis-lineage expects unique NAME=PATH entries")
    lineages = {name: rooted(path) for name, path in lineage_pairs}
    real_binding = binding(real_path, network_path)
    frame = gpd.read_file(network_path)[["id", "length_m"]]
    edge_nodes = {int(key): tuple(value) for key, value in cache["edge_nodes"].items()}
    lengths = {}
    for row in frame.itertuples(index=False):
        edge = edge_nodes.get(int(row.id))
        if edge is None:
            continue
        length = max(float(row.length_m), 1e-3)
        if edge not in lengths or length < lengths[edge]:
            lengths[edge] = length
    real = valid_routes(normalize_routes(load_pickle(real_path), cache))
    reference = route_counters(real, cache)
    items = list(args.route)
    if args.route_dir or not items:
        route_dir = Path(args.route_dir or "datasets/synthetic/route_experiments")
        if not route_dir.is_absolute():
            route_dir = ROOT / route_dir
        for path in sorted(route_dir.glob("*/*")):
            if path.is_file() and (path.suffix == ".pkl" or path.name.endswith(".pkl.gz")):
                items.append((path.parent.name, path.name.replace(".pkl.gz", "").replace(".pkl", ""), path))
    if not items:
        parser.error("no --route entries and no packaged route datasets")

    rows = []
    inputs = []
    seen = set()
    for measurement, router, path in items:
        key = (measurement, router)
        if key in seen:
            raise ValueError(f"Duplicate M×R entry: {key}")
        seen.add(key)
        bound = binding(path, network_path)
        validate_native_mr_cell(measurement, router, bound)
        if measurement == "MTR-DFR":
            if measurement not in lineages:
                raise ValueError("DFR Original requires --synthesis-lineage MTR-DFR=PATH")
            bound.update(generation=validate_generation_source(lineages[measurement],
                         rooted(args.real_source), path, args.population))
        if measurement not in {"MTR-DFR", "DPMM", "MTNet"}:
            if measurement not in measurements:
                raise ValueError(f"Missing --measurement {measurement}=PATH source binding")
            bound.update(validate_routing_source(path, measurements[measurement]))
        inputs.append({"M": measurement, "R": router, **bound})
        routes = normalize_routes(load_pickle(path), cache)
        rows.append({"M": measurement, "R": router,
                     **evaluate_routes(routes, real, cache, reference, lengths)})

    output = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    output.mkdir(parents=True, exist_ok=False)
    result = output / "results.csv"
    with result.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output / "manifest.json").write_text(json.dumps({
        "protocol": "executed_route_object_m_by_r_v1",
        "real_routes": str(real_path),
        "real_input": real_binding,
        "private_input_audit": input_audit,
        "metric_definition": "physical_branch_unit_mass_v2_public_edges_required",
        "route_inputs": inputs,
        "edge_cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
        "network_sha256": hashlib.sha256(network_path.read_bytes()).hexdigest(),
        "results_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
        "rows": len(rows),
        "result": str(result.resolve()),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} executed M×R cells to {result}")


if __name__ == "__main__":
    main()

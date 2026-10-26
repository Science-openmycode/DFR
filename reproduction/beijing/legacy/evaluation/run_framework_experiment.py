from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from route_metric_core import evaluate_routes, load_pickle, normalize_routes, route_counters, valid_routes
from experiment_contract import validate_real_reference, validate_routing_source, POPULATIONS


ROOT = Path(__file__).resolve().parents[1]


def named_path(text: str) -> tuple[str, Path]:
    name, value = text.split("=", 1)
    path = Path(value)
    return name, (path if path.is_absolute() else ROOT / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute the road-object lift from native releases and their public routed outputs."
    )
    parser.add_argument("--real-routes", required=True)
    parser.add_argument("--real-source", type=Path, required=True)
    parser.add_argument("--population", choices=POPULATIONS, default="full-corpus")
    parser.add_argument("--measurement", action="append", type=named_path, required=True,
                        help="NAME=original coordinate release matching each routed output")
    parser.add_argument("--edge-cache", default=str(ROOT / "public_assets" / "ordered_portal_route_cache.pkl.gz"))
    parser.add_argument("--routed", action="append", type=named_path, required=True, help="NAME=ROUTE_PICKLE; repeat")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    cache = load_pickle(Path(args.edge_cache).resolve())
    input_audit = validate_real_reference(Path(args.real_routes), args.real_source, cache, args.population)
    measurements = dict(args.measurement)
    if len(measurements) != len(args.measurement) or set(measurements) != {name for name, _ in args.routed}:
        parser.error("Each routed result needs exactly one corresponding --measurement")
    routing_bindings = {name: validate_routing_source(path, measurements[name]) for name, path in args.routed}
    real = valid_routes(normalize_routes(load_pickle(Path(args.real_routes).resolve()), cache))
    reference = route_counters(real, cache)
    rows = []
    for name, path in args.routed:
        # A coordinate-only statistical release contains no consumer-visible road object.
        rows.append({"Measurement": name, "Stage": "native coordinate release", "StageKey": "native",
                     "RoadYield": 0.0, "BTF": 0.0, "FamilyCPC": 0.0})
        routes = normalize_routes(load_pickle(path), cache)
        metrics = evaluate_routes(routes, real, cache, reference)
        rows.append({"Measurement": name, "Stage": "MTR public routing", "StageKey": "routed",
                     "RoadYield": metrics["RoadYield"], "BTF": metrics["BTF"],
                     "FamilyCPC": metrics["FamilyCPC"]})
    output = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    output.mkdir(parents=True, exist_ok=False)
    result = output / "results.csv"
    with result.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output / "manifest.json").write_text(json.dumps({
        "protocol": "executed_native_vs_public_routing_v1", "rows": len(rows),
        "private_input_audit": input_audit, "routing_bindings": routing_bindings,
        "metric_definition": "physical_branch_unit_mass_v2_public_edges_required",
        "result": str(result.resolve())
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote executed framework comparison to {result}")


if __name__ == "__main__":
    main()

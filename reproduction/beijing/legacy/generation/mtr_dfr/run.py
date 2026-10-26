from __future__ import annotations

import argparse
import importlib
import hashlib
import json
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "dependencies"))
sys.path.insert(0, str(HERE / "algorithm"))
sys.path.insert(0, str(ROOT / "evaluation"))
from experiment_contract import validate_real_reference, POPULATIONS
from route_metric_core import load_pickle


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone MTR-DFR release wrapper.")
    parser.add_argument("--real-matched", type=Path, required=True,
                        help="Private matched trajectory records; never bundled.")
    parser.add_argument("--edge-cache", type=Path, required=True,
                        help="Public frozen edge/region cache.")
    parser.add_argument("--network", type=Path, required=True,
                        help="Public road-network vector file (for example network.shp).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--seed", type=int)
    mode.add_argument("--formal", action="store_true")
    mode.add_argument("--check-only", action="store_true",
                      help="Import the frozen dependency closure and validate paths without reading private records.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--length-aware", action="store_true")
    parser.add_argument("--real-source", type=Path, help="Raw source bound by the road-reference manifest")
    parser.add_argument("--population", choices=POPULATIONS, default="full-corpus",
                        help="full-corpus rejects missing measurement records; accepted-road-subset is conditional")
    parser.add_argument("--epsilon-total", type=float, default=1.4)
    parser.add_argument("--endpoint-top-k", "--resolution-k", dest="endpoint_top_k", type=int, default=8,
                        help="Number of selected endpoint cells within the FIXED 384 partition, not a new grid")
    parser.add_argument("--audit-dir", type=Path, help="Private provenance directory outside the release")
    parser.add_argument("--public-slot-count", type=int, default=17123,
                        help="Predeclared fixed number of synthetic road trajectories.")
    args = parser.parse_args()
    for name in ("real_matched", "edge_cache", "network", "out_dir"):
        path = getattr(args, name)
        setattr(args, name, path.resolve() if path.is_absolute() else (ROOT / path).resolve())
    if args.out_dir.exists() and not args.check_only:
        parser.error(f"Output directory already exists: {args.out_dir}; choose a new run directory")
    for path, label in ((args.real_matched, "real matched input"),
                        (args.edge_cache, "public edge cache"),
                        (args.network, "public network")):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    for path in (args.real_matched, args.edge_cache):
        side = path.with_name(path.name.replace(".pkl.gz", ".manifest.json"))
        if side != path and side.is_file():
            metadata = json.loads(side.read_text(encoding="utf-8"))
            if metadata.get("network_sha256") and metadata["network_sha256"].lower() != hashlib.sha256(args.network.read_bytes()).hexdigest():
                parser.error(f"Input network binding mismatch: {path}")
            if metadata.get("output_sha256") and metadata["output_sha256"].lower() != hashlib.sha256(path.read_bytes()).hexdigest():
                parser.error(f"Input output hash mismatch: {path}")
    module = importlib.import_module("run_minimal_strong_family")
    module.EDGE_CACHE = args.edge_cache.resolve()
    module.REAL_MATCHED = args.real_matched.resolve()
    module.NETWORK = args.network.resolve()
    module.POPULATION_SCOPE = args.population
    if not math.isfinite(args.epsilon_total) or args.epsilon_total <= 0:
        parser.error("--epsilon-total must be positive and finite")
    if not 1 <= args.endpoint_top_k <= 384:
        parser.error("--endpoint-top-k must be in [1,384]; it is not spatial partition resolution")
    module.SELECTED_CELLS_PER_ROLE = args.endpoint_top_k
    if args.public_slot_count <= 0:
        parser.error("--public-slot-count must be positive")
    if args.check_only:
        print("MTR-DFR dependency closure and explicit input paths: OK")
        return
    if args.real_source is None:
        parser.error("--real-source is required to verify actual real-data provenance")
    args.real_source = (args.real_source if args.real_source.is_absolute() else ROOT / args.real_source).resolve()
    input_audit = validate_real_reference(args.real_matched, args.real_source,
        load_pickle(args.edge_cache), args.population, args.network)
    audit_dir = (args.audit_dir or args.out_dir.with_name(args.out_dir.name + ".private_audit")).resolve()
    if audit_dir.is_relative_to(args.out_dir) or args.out_dir.is_relative_to(audit_dir) or audit_dir.exists():
        parser.error("Choose a new private --audit-dir outside the release directory")
    forwarded = [module.__file__, "--out-dir", str(args.out_dir.resolve())]
    forwarded += ["--formal"] if args.formal else ["--seed", str(args.seed)]
    if args.length_aware:
        forwarded.append("--length-aware")
    forwarded += ["--public-slot-count", str(args.public_slot_count)]
    forwarded += ["--epsilon-total", str(args.epsilon_total)]
    sys.argv = forwarded
    module.main()
    binding = {
        "classification": "LOCAL_SYNTHESIS_INPUT_LINEAGE_NOT_AN_ADDITIONAL_DP_RELEASE",
        "inputs": {name: {"path": str(getattr(args, name)),
                         "sha256": hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()}
                   for name in ("real_matched", "edge_cache", "network")},
        "public_slot_count": args.public_slot_count,
        "length_aware": args.length_aware,
        "randomness": "formal" if args.formal else "seeded_research",
        "input_audit": input_audit,
        "endpoint_top_k": args.endpoint_top_k,
        "epsilon_total": args.epsilon_total,
        "outputs": {p.relative_to(args.out_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(args.out_dir.rglob("*")) if p.is_file()},
    }
    audit_dir.mkdir(parents=True, exist_ok=False)
    (audit_dir / "input_lineage.json").write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

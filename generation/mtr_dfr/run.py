from __future__ import annotations

import argparse
import importlib
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "dependencies"))
sys.path.insert(0, str(HERE / "algorithm"))


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
    if args.public_slot_count <= 0:
        parser.error("--public-slot-count must be positive")
    module.SLOTS = int(args.public_slot_count)
    if args.check_only:
        print("MTR-DFR dependency closure and explicit input paths: OK")
        return
    forwarded = [module.__file__, "--out-dir", str(args.out_dir.resolve())]
    forwarded += ["--formal"] if args.formal else ["--seed", str(args.seed)]
    if args.length_aware:
        forwarded.append("--length-aware")
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
    }
    (args.out_dir / "input_lineage.json").write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

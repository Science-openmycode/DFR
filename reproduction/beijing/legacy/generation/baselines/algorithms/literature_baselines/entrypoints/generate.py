from __future__ import annotations

import argparse
import importlib.util
import math
import subprocess
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    for _candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if ((_candidate / "configs" / "datasets.json").is_file()
                and (_candidate / "generation" / "common" / "runtime.py").is_file()):
            sys.path.insert(0, str(_candidate))
            break
    else:
        raise RuntimeError("cannot locate public_release root")

from generation.common.runtime import (  # noqa: E402
    PUBLIC_RELEASE, dataset_config, public_path, require_new_directory, sha256_file, write_json
)


BASELINE_METHODS = (
    "dpstd-native", "dpstd-osm", "dpstd-pra",
    "dptrajpm-native", "dptrajpm-official", "dptrajpm-osm", "dptrajpm-pra",
    "privtrace-native", "privtrace-official", "privtrace-osm", "privtrace-pra",
    "sprt-native", "sprt-osm", "sprt-paper-structured", "sprt-pra",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified wrapper for reproduced trajectory baselines.")
    parser.add_argument("--method", required=True, choices=BASELINE_METHODS)
    parser.add_argument("--data", required=True)
    parser.add_argument("--epsilon", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--tag")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--format", choices=("pkl", "npz", "both"), default="pkl")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    parser.add_argument("--osm-cache")
    parser.add_argument("--public-slot-count", type=int)
    parser.add_argument("--extra-arg", action="append", default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    reserved = {"--method", "--data", "--epsilon", "--out-dir", "--seed", "--format", "--bbox", "--osm-cache", "--n-gen"}
    for token in args.extra_arg:
        if token.split("=", 1)[0] in reserved:
            raise ValueError(f"--extra-arg cannot override a bound protocol parameter: {token}")
    epsilon = float(args.epsilon)
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("--epsilon must be a finite positive decimal value")
    if importlib.util.find_spec("requests") is None:
        raise RuntimeError("requests is required by the baseline source; install requirements.txt")
    if args.method.startswith("privtrace") and importlib.util.find_spec("cvxpy") is None:
        raise RuntimeError("cvxpy is required for PrivTrace optimization; install requirements.txt")
    try:
        registered = dataset_config(args.data)
    except KeyError:
        registered = None
    if registered is None and (args.bbox is None or args.osm_cache is None or args.public_slot_count is None):
        raise RuntimeError("custom data requires --bbox, --osm-cache, and --public-slot-count")
    bbox = args.bbox if args.bbox is not None else registered.get("bbox")
    osm_cache = args.osm_cache if args.osm_cache is not None else registered.get("osm_cache")
    public_slot_count = args.public_slot_count if args.public_slot_count is not None else registered.get("public_slot_count")
    if bbox is None or osm_cache is None or public_slot_count is None or public_slot_count <= 0:
        raise RuntimeError("a valid public bbox, OSM cache, and positive slot count are required")
    data_spec = registered.get("data", args.data) if registered is not None else args.data
    data_path = ((PUBLIC_RELEASE / data_spec).resolve() if registered is not None
                 else public_path(data_spec))
    expected_data_sha256 = registered.get("data_sha256") if registered is not None else None
    if expected_data_sha256 is not None:
        if not data_path.is_file() or sha256_file(data_path) != expected_data_sha256:
            raise RuntimeError("frozen baseline input hash mismatch (preflight; generation not started)")
    elif registered is None and not data_path.is_file():
        raise FileNotFoundError(f"trajectory input not found: {data_path}")
    osm_path = ((PUBLIC_RELEASE / osm_cache).resolve() if args.osm_cache is None
                else public_path(osm_cache))
    if not osm_path.is_file():
        raise FileNotFoundError(f"public OSM cache not found: {osm_path}")
    out_dir = require_new_directory(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    pipeline_entry = PUBLIC_RELEASE / "pipeline" / "synthesize_dataset.py"
    data_spec = registered.get("data", args.data) if registered is not None else args.data
    osm_path = ((PUBLIC_RELEASE / osm_cache).resolve() if args.osm_cache is None
                else public_path(osm_cache))
    command = [
        sys.executable, str(pipeline_entry),
        "--method", args.method, "--data", str(data_path) if data_path.is_file() else str(data_spec), "--epsilon", str(args.epsilon),
        "--out-dir", str(out_dir), "--seed", str(args.seed), "--format", args.format,
    ]
    command += ["--bbox", *(str(value) for value in bbox)]
    command += ["--osm-cache", str(osm_path)]
    command += ["--n-gen", str(int(public_slot_count))]
    if registered is not None:
        command += ["--n-train", str(int(public_slot_count))]
    if args.tag:
        command += ["--tag", args.tag]
    command += list(args.extra_arg)
    started = time.time()
    result = subprocess.run(command, cwd=PUBLIC_RELEASE, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    outputs = {
        str(path.relative_to(out_dir)): sha256_file(path)
        for path in out_dir.iterdir() if path.is_file() and path.suffix.lower() in {".pkl", ".npz", ".json"}
    }
    data_path = ((PUBLIC_RELEASE / data_spec).resolve() if registered is not None
                 else public_path(data_spec))
    expected_data_sha256 = registered.get("data_sha256") if registered is not None else None
    if expected_data_sha256 is not None:
        if not data_path.is_file() or sha256_file(data_path) != expected_data_sha256:
            raise RuntimeError("frozen baseline input hash mismatch")
    input_binding = (
        {
            "dataset_config": args.data,
            "spec": str(data_spec),
            "path": str(data_path),
            "sha256": sha256_file(data_path),
        }
        if data_path.is_file()
        else {
            "spec": args.data,
            "sha256": None,
            "hash_note": "Named/multi-file loader input has no single source-file hash.",
        }
    )
    write_json(out_dir / "baseline_wrapper_manifest.json", {
        "schema_version": 1,
        "classification": "BASELINE_REPRODUCTION_WRAPPER_NOT_AN_MTR_RELEASE",
        "command": command,
        "method": args.method,
        "parameters": {
            "data": args.data,
            "epsilon": args.epsilon,
            "seed": args.seed,
            "format": args.format,
            "tag": args.tag,
            "extra_args": list(args.extra_arg),
            "matched_dataset_config": registered,
            "public_bbox": bbox,
            "public_osm_cache": str(osm_path),
            "public_slot_count": int(public_slot_count),
        },
        "input": input_binding,
        "entrypoints": {
            "wrapper": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
            "pipeline": {"path": str(pipeline_entry), "sha256": sha256_file(pipeline_entry)},
        },
        "elapsed_sec": time.time() - started, "outputs": outputs,
    })


if __name__ == "__main__":
    main()

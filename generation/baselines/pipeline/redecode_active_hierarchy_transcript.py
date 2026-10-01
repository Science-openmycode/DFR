from __future__ import annotations

import argparse
import gc
import json
import os
import pickle
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np


PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
FINAL = PUBLIC_RELEASE / "src" / "mtr" / "DP_GSRT" / "final"
for path in (PUBLIC_RELEASE, FINAL):
    sys.path.insert(0, str(path))

from generation.mtr import generate as candidate  # noqa: E402
from generation.common.runtime import add_runtime_paths, dataset_config, public_path, sha256_file  # noqa: E402
from public_utils import filter_osm_ways_by_bbox, filter_osm_ways_by_highway, thin_osm_ways_public  # noqa: E402


CLASSIFICATION = "RESEARCH_ACTIVE_HIERARCHY_TRANSCRIPT_POSTPROCESS_DO_NOT_RELEASE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the public active-hierarchy decoder to an already released "
            "DP transcript. This performs no new private access."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset-config", default="geolife")
    parser.add_argument("--decoder-seed", type=int, default=40260719)
    parser.add_argument("--request-seed", type=int, default=50260719)
    parser.add_argument("--decoder-betas", default="0.03,0.06,0.12,0.24,0.48,0.96")
    parser.add_argument("--length-proposals", type=int, default=1)
    parser.add_argument("--length-log-penalty", type=float, default=8.0)
    parser.add_argument("--od-likelihood-ratio-cap", type=float, default=100.0)
    parser.add_argument("--occupancy-strength", type=float, default=0.25)
    parser.add_argument("--dwell-strength", type=float, default=0.10)
    parser.add_argument("--hierarchy-likelihood-ratio-cap", type=float, default=100.0)
    parser.add_argument(
        "--route-alignment",
        choices=("correct-dp", "shuffled-dp", "public-only"),
        default="correct-dp",
    )
    return parser


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: np.asarray(archive[name], dtype=float) for name in archive.files}


def main() -> None:
    args = build_parser().parse_args()
    add_runtime_paths()
    source_root = args.source_root.resolve()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise FileExistsError(f"output already exists: {out_dir}")

    base_path = source_root / "base" / "sanitized_base_geometry.npz"
    graph_flow_path = source_root / "base" / "sanitized_compact_graph_flow.npz"
    q5_path = source_root / "portal" / "portal_fiber_route_dp_release.npz"
    base_manifest_path = source_root / "base" / "sanitizer_manifest.json"
    audit_manifest_path = source_root / "audit_instance_manifest.json"
    for path in (base_path, graph_flow_path, q5_path, base_manifest_path, audit_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    base = load_npz(base_path)
    graph_flow = load_npz(graph_flow_path)
    q5_raw = load_npz(q5_path)
    if set(base) != {"endpoint", "od", "geometry", "length"}:
        raise RuntimeError("base attack transcript schema mismatch")
    if set(graph_flow) != {"fine_occupancy", "fine_flow", "dwell"}:
        raise RuntimeError("compact graph-flow attack transcript schema mismatch")
    if tuple(q5_raw) != candidate.Q5_BLOCK_NAMES:
        raise RuntimeError("Portal-Fiber attack transcript schema mismatch")

    # Each formal flow block includes one public null-slot coordinate.  The
    # production-compatible decoder verifies that sealed shape and removes the
    # null coordinate internally before constructing a route kernel.
    q5 = dict(q5_raw)

    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    audit_manifest = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    config = dataset_config(args.dataset_config)
    bbox = tuple(float(value) for value in config["bbox"])
    capacity = int(audit_manifest["fixed_capacity"])
    if capacity != int(config["public_slot_count"]):
        raise RuntimeError("attack capacity differs from the registered public capacity")
    if audit_manifest["epsilon_rational"] != "7/5":
        raise RuntimeError("unexpected attack-audit privacy budget")

    osm_spec = base_manifest["public_osm"]["path"]
    osm_path = public_path(osm_spec)
    if not osm_path.is_file():
        osm_path = public_path(config["osm_cache"])
    expected_osm_hash = audit_manifest["public_osm_sha256"]
    if sha256_file(osm_path) != expected_osm_hash:
        raise RuntimeError("public OSM hash differs from the attack audit")
    with osm_path.open("rb") as handle:
        osm = pickle.load(handle)
    osm = filter_osm_ways_by_bbox(osm, bbox)
    osm = filter_osm_ways_by_highway(osm, config.get("osm_highway_classes", []))
    maximum = int(config.get("osm_max_ways", 0))
    if maximum > 0:
        osm = thin_osm_ways_public(osm, bbox, maximum)

    staging = out_dir.parent / f".{out_dir.name}.staging"
    if staging.exists():
        raise FileExistsError(f"stale candidate staging directory: {staging}")
    staging.mkdir(parents=True)
    try:
        decoder_out = candidate._decode(
            staging,
            base,
            graph_flow,
            q5,
            osm,
            expected_osm_hash,
            capacity,
            Fraction(7, 5),
            Fraction(1, 5),
            Fraction(1, 5),
            args.decoder_seed,
            args.request_seed,
            bbox,
            betas=args.decoder_betas,
            length_proposals=args.length_proposals,
            length_log_penalty=args.length_log_penalty,
            od_likelihood_ratio_cap=args.od_likelihood_ratio_cap,
            occupancy_strength=args.occupancy_strength,
            dwell_strength=args.dwell_strength,
            hierarchy_likelihood_ratio_cap=args.hierarchy_likelihood_ratio_cap,
            route_alignment=args.route_alignment,
        )
        shutil.copy2(decoder_out / "dp_gsrt_portal_qrsp.pkl", staging / "trajectories.pkl")
        shutil.copy2(decoder_out / "road_witnesses.pkl", staging / "road_witnesses.pkl")
        decoder_protocol = json.loads((decoder_out / "protocol.json").read_text(encoding="utf-8"))
        shutil.rmtree(decoder_out)
        del base, graph_flow, q5_raw, q5, osm
        gc.collect()

        with (staging / "trajectories.pkl").open("rb") as handle:
            trajectories = pickle.load(handle)
        with (staging / "road_witnesses.pkl").open("rb") as handle:
            witnesses = pickle.load(handle)
        if len(trajectories) != capacity or len(witnesses) != capacity:
            raise RuntimeError("candidate attack release did not fill every public slot")
        report = {
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "algorithm_id": candidate.ALGORITHM_SCHEMA,
            "source_root": str(source_root),
            "source_hashes": {
                "base": sha256_file(base_path),
                "graph_flow": sha256_file(graph_flow_path),
                "portal_fiber_q5": sha256_file(q5_path),
                "audit_manifest": sha256_file(audit_manifest_path),
            },
            "new_private_access": False,
            "additional_privacy_cost": 0,
            "privacy": {
                "epsilon_rational": "7/5",
                "delta": 0,
                "source_adjacency": audit_manifest["adjacency"],
            },
            "public_slot_count": capacity,
            "output_count": len(trajectories),
            "postprocessing": {
                "decoder_seed": args.decoder_seed,
                "request_seed": args.request_seed,
                "betas": args.decoder_betas,
                "length_proposals": args.length_proposals,
                "length_log_penalty": args.length_log_penalty,
                "od_likelihood_ratio_cap": args.od_likelihood_ratio_cap,
                "occupancy_strength": args.occupancy_strength,
                "dwell_strength": args.dwell_strength,
                "hierarchy_likelihood_ratio_cap": args.hierarchy_likelihood_ratio_cap,
                "route_alignment": args.route_alignment,
            },
            "active_hierarchy": decoder_protocol["active_hierarchy"],
            "fallback_count": decoder_protocol["fallback_count"],
            "outputs": {
                "trajectories.pkl": sha256_file(staging / "trajectories.pkl"),
                "road_witnesses.pkl": sha256_file(staging / "road_witnesses.pkl"),
            },
        }
        (staging / "protocol.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (staging / "DO_NOT_RELEASE.txt").write_text(
            "Research-only deterministic post-processing of a released DP transcript.\n",
            encoding="ascii",
        )
        os.replace(staging, out_dir)
        print(json.dumps(report, indent=2))
    except Exception:
        raise


if __name__ == "__main__":
    main()

"""Package decoder witnesses as a versioned consumer-visible release object."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from pathlib import Path

import numpy as np


SCHEMA_ID = "mtr-road-witness-release-v1"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directed_edge_id(pair: tuple[int, int] | list[int]) -> str:
    """Return a stable public-graph directed-edge identifier."""
    if len(pair) != 2:
        raise ValueError("Every directed edge must contain exactly two node IDs")
    return f"{int(pair[0])}:{int(pair[1])}"


def validate_production_protocol(
    protocol_path: Path,
    raw_witness_path: Path,
    coordinate_path: Path,
    public_graph_sha256: str,
) -> dict:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    privacy = protocol.get("privacy_accounting", {})
    release_object = protocol.get("release_object", {})
    outputs = protocol.get("outputs", {})
    if protocol.get("classification") != "PRODUCTION_DP_POSTPROCESS" or protocol.get("certified_release") is not True:
        raise ValueError("Witness packaging requires a certified production post-processing protocol")
    if privacy.get("composed_epsilon_rational") != "7/5" or float(privacy.get("delta", -1)) != 0.0:
        raise ValueError("Production protocol has the wrong privacy accounting")
    if protocol.get("route_alignment") != "correct-dp":
        raise ValueError("Formal witness release requires the correctly aligned DP route block")
    if protocol.get("decoder_seed") is not None or protocol.get("request_seed") is not None:
        raise ValueError("Formal production packaging forbids recorded deterministic seeds")
    if release_object.get("coordinate_polyline") != coordinate_path.name or release_object.get("road_witness_sidecar") != raw_witness_path.name:
        raise ValueError("Protocol release-object filenames disagree with the supplied artifacts")
    if outputs.get(coordinate_path.name) != sha256_file(coordinate_path) or outputs.get(raw_witness_path.name) != sha256_file(raw_witness_path):
        raise ValueError("Protocol output hashes disagree with the supplied artifacts")
    if protocol.get("inputs", {}).get("public_osm_sha256") != public_graph_sha256.lower():
        raise ValueError("Protocol and witness package public-graph hashes disagree")
    return protocol


def build_package(
    raw_witnesses: list[dict],
    coordinate_path: Path,
    public_graph_sha256: str,
    protocol_path: Path | None = None,
) -> dict:
    if len(public_graph_sha256) != 64:
        raise ValueError("public_graph_sha256 must be a full SHA-256 digest")
    with coordinate_path.open("rb") as handle:
        coordinates = pickle.load(handle)
    if not isinstance(coordinates, list) or len(coordinates) != len(raw_witnesses):
        raise ValueError("Coordinate artifact and witness sidecar must have one record per slot")
    records = []
    for expected_slot, (raw, coordinate_record) in enumerate(zip(raw_witnesses, coordinates)):
        if not isinstance(raw, dict) or int(raw.get("slot", -1)) != expected_slot:
            raise ValueError("Raw witness slots must be contiguous and ordered")
        points = np.asarray(coordinate_record, dtype=float)
        if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] < 2 or not np.all(np.isfinite(points)):
            raise ValueError("Every coordinate record must be a finite point polyline")
        pairs = raw.get("directed_edges")
        nodes = raw.get("node_sequence")
        if pairs is None or nodes is None:
            valid = False
            edge_ids = []
            pairs = []
            nodes = []
        else:
            pairs = [[int(a), int(b)] for a, b in pairs]
            nodes = [int(node) for node in nodes]
            if not pairs:
                raise ValueError("A road witness must contain at least one directed edge")
            if len(nodes) != len(pairs) + 1:
                raise ValueError("Node and directed-edge sequence lengths disagree")
            if any([nodes[i], nodes[i + 1]] != pair for i, pair in enumerate(pairs)):
                raise ValueError("Directed edges do not reconstruct the node sequence")
            valid = True
            edge_ids = [directed_edge_id(pair) for pair in pairs]
        records.append(
            {
                "slot": expected_slot,
                "witness_valid_by_construction": valid,
                "directed_edge_ids": edge_ids,
                "directed_edges": pairs,
                "node_sequence": nodes,
                "coordinate_record_index": expected_slot,
                "coordinate_sample_count": int(points.shape[0]),
                "coordinate_sampling_positions": {
                    "parameter": "normalized_arclength",
                    "rule": "linspace(0,1,coordinate_sample_count)",
                    "endpoint_inclusive": True,
                },
                "fallback": bool(raw.get("fallback", False)),
            }
        )
    package = {
        "schema_id": SCHEMA_ID,
        "packager": {
            "entrypoint": Path(__file__).name,
            "sha256": sha256_file(Path(__file__)),
        },
        "privacy_status": (
            "post-processing of an authenticated DP transcript and a fixed public graph; "
            "the package performs no private-data access and spends no additional privacy budget"
        ),
        "public_graph": {
            "version_kind": "sha256",
            "sha256": public_graph_sha256.lower(),
            "directed_edge_id_encoding": "<public-node-id>:<public-node-id>",
        },
        "coordinate_artifact": {
            "path": coordinate_path.name,
            "sha256": sha256_file(coordinate_path),
            "record_count": len(records),
        },
        "record_count": len(records),
        "records": records,
    }
    if protocol_path is not None:
        package["production_protocol"] = {
            "path": protocol_path.name,
            "sha256": sha256_file(protocol_path),
        }
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-witnesses", type=Path, required=True)
    parser.add_argument("--coordinates", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--public-graph-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"Refusing to overwrite an existing witness release: {args.out}")
    staging = args.out.parent / f".{args.out.name}.staging"
    if staging.exists():
        raise FileExistsError(f"Stale witness-release staging file exists: {staging}")
    with args.raw_witnesses.open("rb") as handle:
        raw = pickle.load(handle)
    validate_production_protocol(
        args.protocol,
        args.raw_witnesses,
        args.coordinates,
        args.public_graph_sha256,
    )
    package = build_package(
        raw,
        args.coordinates,
        args.public_graph_sha256,
        args.protocol,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with staging.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staging, args.out)
    print(json.dumps({"path": str(args.out), "sha256": sha256_file(args.out), "records": package["record_count"]}))


if __name__ == "__main__":
    main()

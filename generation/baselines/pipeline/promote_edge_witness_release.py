"""Atomically promote a measured production edge-witness release.

This command never decodes or measures private data.  It only verifies an
already certified post-processing directory, its consumer witness package,
and a current evaluation ledger before updating the two active-status files.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from pipeline.package_edge_witness_release import sha256_file, validate_production_protocol
except ModuleNotFoundError:  # Direct ``python pipeline/...py`` execution.
    from package_edge_witness_release import sha256_file, validate_production_protocol


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: dict) -> None:
    staging = path.with_suffix(path.suffix + ".staging")
    if staging.exists():
        raise FileExistsError(f"Stale staging file exists: {staging}")
    with staging.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staging, path)


def verify_release(release_dir: Path, witness_package: Path, evaluation_dir: Path) -> dict:
    coordinates = release_dir / "dp_gsrt_portal_qrsp.pkl"
    raw_witnesses = release_dir / "road_witnesses.pkl"
    protocol_path = release_dir / "protocol.json"
    control = release_dir / "dp_request_public_shortest_path_control.pkl"
    lineage_audit = release_dir / "source_lineage_compatibility.json"
    for path in (coordinates, raw_witnesses, protocol_path, control, witness_package, lineage_audit):
        if not path.is_file():
            raise FileNotFoundError(path)
    protocol = _read_json(protocol_path)
    lineage = _read_json(lineage_audit)
    if (
        lineage.get("classification") != "FORMAL_QUERY_LINEAGE_COMPATIBILITY_AUDIT"
        or lineage.get("passed") is not True
        or protocol.get("inputs", {}).get("portal_manifest_sha256")
        != lineage.get("transcript_manifest_sha256")
    ):
        raise ValueError("Formal release lacks a matching passed q5 source-lineage audit")
    for name in ("transcript_manifest_path", "archived_graph_core_path", "runtime_graph_core_path"):
        source = Path(lineage[name])
        expected = lineage[
            "transcript_manifest_sha256" if name == "transcript_manifest_path"
            else "archived_graph_core_sha256" if name == "archived_graph_core_path"
            else "runtime_graph_core_sha256"
        ]
        if not source.is_file() or sha256_file(source) != expected:
            raise ValueError(f"Formal source-lineage audit binding changed: {name}")
    graph_sha256 = protocol.get("inputs", {}).get("public_osm_sha256")
    validate_production_protocol(
        protocol_path, raw_witnesses, coordinates, str(graph_sha256)
    )
    if protocol.get("outputs", {}).get(control.name) != sha256_file(control):
        raise ValueError("Production protocol is not bound to the same-request public control")
    package = _read_json(witness_package)
    if package.get("schema_id") != "mtr-road-witness-release-v1":
        raise ValueError("Unknown consumer witness schema")
    if package.get("coordinate_artifact", {}).get("sha256") != sha256_file(coordinates):
        raise ValueError("Consumer witness package is not bound to the production coordinates")
    if package.get("production_protocol", {}).get("sha256") != sha256_file(protocol_path):
        raise ValueError("Consumer witness package is not bound to the production protocol")
    if package.get("public_graph", {}).get("sha256") != graph_sha256:
        raise ValueError("Consumer witness package public-graph binding is invalid")
    if int(package.get("record_count", -1)) != int(protocol.get("limit", -2)):
        raise ValueError("Consumer witness count disagrees with the production protocol")

    metrics_path = evaluation_dir / "metrics.json"
    evaluation_manifest_path = evaluation_dir / "manifest.json"
    control_evaluation_dir = release_dir / "evaluation_public_control"
    control_metrics_path = control_evaluation_dir / "metrics.json"
    control_evaluation_manifest_path = control_evaluation_dir / "manifest.json"
    metrics = _read_json(metrics_path)
    evaluation_manifest = _read_json(evaluation_manifest_path)
    control_metrics = _read_json(control_metrics_path)
    control_evaluation_manifest = _read_json(control_evaluation_manifest_path)
    witness_valid = metrics.get("metrics", {}).get("witness_valid")
    if witness_valid != 1.0:
        raise ValueError(f"Promotion requires measured WitnessValid=1.0, got {witness_valid!r}")
    inputs = evaluation_manifest.get("inputs", {})
    if inputs.get("synthetic", {}).get("sha256") != sha256_file(coordinates):
        raise ValueError("Evaluation ledger used a different coordinate artifact")
    if inputs.get("witness", {}).get("sha256") != sha256_file(witness_package):
        raise ValueError("Evaluation ledger used a different witness package")
    control_inputs = control_evaluation_manifest.get("inputs", {})
    if control_inputs.get("synthetic", {}).get("sha256") != sha256_file(control):
        raise ValueError("Public-control evaluation ledger used a different coordinate artifact")
    if control_inputs.get("witness") is not None:
        raise ValueError("Public-control evaluation must not claim an MTR edge-witness package")
    return {
        "coordinates": coordinates,
        "raw_witnesses": raw_witnesses,
        "protocol": protocol_path,
        "control": control,
        "witness_package": witness_package,
        "metrics": metrics_path,
        "evaluation_manifest": evaluation_manifest_path,
        "public_control_metrics": control_metrics_path,
        "public_control_evaluation_manifest": control_evaluation_manifest_path,
        "source_lineage_audit": lineage_audit,
        "protocol_payload": protocol,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--witness-package", type=Path, required=True)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument(
        "--current-manifest",
        type=Path,
        default=Path("outputs/synthetic_releases/current_best/MANIFEST.json"),
    )
    parser.add_argument(
        "--method-status",
        type=Path,
        default=Path("src/mtr/DP_GSRT/CURRENT_METHOD_STATUS.json"),
    )
    args = parser.parse_args()
    release_dir = args.release_dir.resolve()
    current_root = args.current_manifest.resolve().parent
    try:
        release_dir.relative_to(current_root)
    except ValueError as error:
        raise ValueError("Formal release directory must be inside current_best") from error
    verified = verify_release(release_dir, args.witness_package.resolve(), args.evaluation_dir.resolve())
    protocol = verified.pop("protocol_payload")
    now = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    manifest = _read_json(args.current_manifest)
    status = _read_json(args.method_status)
    for path in (args.current_manifest, args.method_status):
        shutil.copy2(path, path.with_name(f"{path.name}.pre_edge_witness_{stamp}.bak"))

    relative = {
        name: str(path.resolve().relative_to(current_root)).replace("\\", "/")
        for name, path in verified.items()
    }
    dp = manifest.setdefault("dp_gsrt_status", {})
    dp.update(
        {
            "active": True,
            "algorithm_id": "dp-gsrt-portal-fiber-nested-qrsp384-edge-witness-v1",
            "record_count": int(protocol["limit"]),
            "privacy": "pure (7/5,0)-DP under fixed-capacity raw-record add/remove adjacency",
            "artifact_path": relative["coordinates"],
            "artifact_sha256": sha256_file(verified["coordinates"]),
            "witness_path": relative["witness_package"],
            "witness_sha256": sha256_file(verified["witness_package"]),
            "protocol_path": relative["protocol"],
            "protocol_sha256": sha256_file(verified["protocol"]),
            "public_control_path": relative["control"],
            "evaluation_metrics_path": relative["metrics"],
            "evaluation_manifest_path": relative["evaluation_manifest"],
            "public_control_metrics_path": relative["public_control_metrics"],
            "public_control_evaluation_manifest_path": relative["public_control_evaluation_manifest"],
            "witness_valid": 1.0,
        }
    )
    manifest["status"] = "ACTIVE_FINAL_PORTAL_FIBER_DP_GSRT_EDGE_WITNESS_V1"
    manifest["generated_at"] = now
    manifest["purpose"] = "Current full-size production release with consumer-visible directed-edge witnesses."
    historical = manifest.setdefault("historical_active_artifacts", [])
    old_hash = "b770a924c1c491719e36355d9c9bd3fe66e60ca54f11913e98b70b73cfe62668"
    if not any(item.get("sha256") == old_hash for item in historical if isinstance(item, dict)):
        historical.append({"path": "mtr_dp_gsrt.pkl", "sha256": old_hash, "status": "superseded_postprocessing_draw"})
    files = manifest.setdefault("files", [])
    for value in relative.values():
        if value not in files:
            files.append(value)

    status["schema_version"] = max(int(status.get("schema_version", 0)), 3)
    status["promotion_status"] = "APPROVED_ACTIVE_FINAL_EDGE_WITNESS_V1"
    status["active_algorithm_id"] = dp["algorithm_id"]
    status["production_output"] = {
        "record_count": int(protocol["limit"]),
        "sha256": dp["artifact_sha256"],
        "fallback_count": int(protocol["fallback_count"]),
        "witness_sha256": dp["witness_sha256"],
        "witness_valid": 1.0,
        "protocol_sha256": dp["protocol_sha256"],
    }
    status["updated_at"] = now
    _atomic_json(args.current_manifest, manifest)
    _atomic_json(args.method_status, status)
    print(json.dumps({"manifest": str(args.current_manifest), "status": str(args.method_status), "artifact_sha256": dp["artifact_sha256"], "witness_sha256": dp["witness_sha256"]}, indent=2))


if __name__ == "__main__":
    main()

"""Run a fresh, ledger-isolated instance of the active Portal-Fiber MTR.

This wrapper intentionally does not reimplement the mechanism.  It imports the
active production modules and changes only their process-local ledger location
and ledger domains, allowing a privacy-audit release to consume independent
budget.  The fixed 17,123-slot domain, public OSM, DP query, system randomness,
and QRSP decoder parameters remain those of the active mechanism.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = ROOT / "src" / "mtr" / "DP_GSRT" / "final"
STATUS_PATH = ROOT / "src" / "mtr" / "DP_GSRT" / "CURRENT_METHOD_STATUS.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("base", "portal", "decode"))
    parser.add_argument("--real", required=True, type=Path)
    parser.add_argument("--osm", required=True, type=Path)
    parser.add_argument("--base-dir", required=True, type=Path)
    parser.add_argument("--portal-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--audit-ledger", required=True, type=Path)
    parser.add_argument("--audit-id", required=True)
    return parser.parse_args()


def assert_active_status() -> dict:
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    required = (
        status.get("promotion_status") == "APPROVED_ACTIVE_FINAL"
        and status.get("production_status") == "COMMITTED_AND_ARTIFACT_SEALED"
        and status.get("active_algorithm_id") == "dp-gsrt-portal-fiber-nested-qrsp384-v1"
        and status.get("active_privacy_event_ids", {}).get("base")
        and status.get("active_privacy_event_ids", {}).get("portal_fiber_q5")
    )
    if not required:
        raise RuntimeError("The active Portal-Fiber status is not promotion-complete.")
    return status


def configure_isolated_ledger(args: argparse.Namespace):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src" / "mtr"))
    sys.path.insert(0, str(FINAL_DIR))
    import graph_cycle_dp_production_sanitizer as base
    import portal_fiber_route_production_sanitizer as portal

    ledger = args.audit_ledger.resolve()
    base.LEDGER_PATH = ledger
    portal.LEDGER_PATH = ledger
    base.LEDGER_DOMAIN = f"mtr-privacy-audit:{args.audit_id}:base"
    portal.PRIVACY_DOMAIN = f"mtr-privacy-audit:{args.audit_id}:portal-fiber-q5"

    # The production helper opens a buffered read handle before fsync.  That
    # descriptor path raises EBADF on this Windows Python build after NPZ
    # serialization.  Use the same OS-level fsync guarantee through an
    # unbuffered descriptor; this affects durability only, never a query,
    # random draw, or released value.
    def windows_safe_fsync(path: Path) -> None:
        descriptor = os.open(path, os.O_RDWR)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    base.fsync_file = windows_safe_fsync
    return base, portal


def write_audit_manifest(args: argparse.Namespace, status: dict) -> None:
    destination = args.out_dir.parent / "audit_instance_manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_files = [
        FINAL_DIR / "graph_cycle_dp_production_sanitizer.py",
        FINAL_DIR / "portal_fiber_route_production_sanitizer.py",
        FINAL_DIR / "portal_fiber_qrsp_production.py",
        FINAL_DIR / "portal_fiber_qrsp_production_gate.py",
        FINAL_DIR / "quotient_rsp_bridge_development.py",
    ]
    payload = {
        "purpose": "fresh disjoint-release privacy audit; not the paper production artifact",
        "algorithm_id": status["active_algorithm_id"],
        "active_proof_id": status["active_proof_id"],
        "fixed_capacity": 17123,
        "adjacency": status["privacy"]["adjacency"],
        "epsilon_rational": status["privacy"]["composed_epsilon_rational"],
        "delta": status["privacy"]["delta"],
        "audit_id": args.audit_id,
        "base_ledger_domain": f"mtr-privacy-audit:{args.audit_id}:base",
        "portal_ledger_domain": f"mtr-privacy-audit:{args.audit_id}:portal-fiber-q5",
        "audit_ledger": str(args.audit_ledger.resolve()),
        "private_source_sha256": sha256(args.real.resolve()),
        "public_osm_sha256": sha256(args.osm.resolve()),
        "active_status_sha256": sha256(STATUS_PATH),
        "production_source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in source_files},
        "isolation_statement": "Only process-local ledger path/domain constants are changed; no mechanism, query, capacity, public graph, or decoder parameter is changed.",
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    args = parse_args()
    status = assert_active_status()
    if not args.real.is_file() or not args.osm.is_file():
        raise FileNotFoundError("Both --real and --osm must be regular files.")
    base, portal = configure_isolated_ledger(args)
    write_audit_manifest(args, status)

    if args.stage == "base":
        sys.argv = [
            "graph_cycle_dp_production_sanitizer.py",
            "--private-source", str(args.real.resolve()),
            "--out-dir", str(args.base_dir.resolve()),
            "--production-release",
        ]
        base.main()
        return
    if args.stage == "portal":
        sys.argv = [
            "portal_fiber_route_production_sanitizer.py",
            "--real", str(args.real.resolve()), "--osm", str(args.osm.resolve()),
            "--out-dir", str(args.portal_dir.resolve()), "--capacity", "17123",
            "--epsilon-route", "1/5", "--coarse-occupancy-regions", "24",
            "--coarse-transition-regions", "96", "--fine-regions", "384",
            "--macro-regions", "4", "--phase-count", "3", "--portals-per-fine-edge", "6",
            "--production-release",
        ]
        portal.main()
        return

    import portal_fiber_qrsp_production_gate as gate
    import quotient_rsp_bridge_development as decoder

    # The gate imports the same module objects, so its lineage checks read the
    # isolated ledger and the audit-instance seals created above.
    gate.base_sanitizer = base
    gate.portal_sanitizer = portal
    sys.argv = [
        "portal_fiber_qrsp_production.py", "--portal-release-dir", str(args.portal_dir.resolve()),
        "--out-dir", str(args.out_dir.resolve()),
        "--limit", "17123", "--route-release-schema", "portal-fiber-nested384",
        "--regions", "384", "--reference-source", "dp-flow", "--reference-conditioning", "portal-fiber",
        "--od-family-source", "released", "--od-likelihood-ratio-cap", "100", "--portal-count", "6",
        "--max-region-steps", "192", "--length-proposals", "9", "--length-log-penalty", "8",
        "--betas", "0.003,0.006,0.012,0.024,0.048,0.096,0.192,0.384,0.768",
        "--production-postprocess",
    ]
    decoder.main()


if __name__ == "__main__":
    main()

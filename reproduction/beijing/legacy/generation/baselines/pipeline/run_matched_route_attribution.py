"""Decode one rigorously matched q5 attribution arm from a sealed DP transcript."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import run_mtr_portal_fiber_audit_instance as audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--osm", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--portal-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--audit-ledger", type=Path, required=True)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--arm", choices=("public-only", "shuffled-dp", "correct-dp"), required=True)
    parser.add_argument("--decoder-seed", type=int, required=True)
    parser.add_argument("--request-seed", type=int, required=True)
    parser.add_argument("--public-fallback-cache", type=Path)
    parser.add_argument("--emit-matched-candidate-bank", action="store_true")
    parser.add_argument("--matched-candidate-bank", type=Path)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError("Matched arm output directory must be new")
    status = audit.assert_active_status()
    base, portal = audit.configure_isolated_ledger(args)
    sys.path.insert(0, str(audit.FINAL_DIR))
    import portal_fiber_qrsp_production_gate as gate
    import quotient_rsp_bridge_matched as decoder

    gate.base_sanitizer = base
    gate.portal_sanitizer = portal
    sys.argv = [
        "portal_fiber_qrsp_production.py", "--portal-release-dir", str(args.portal_dir.resolve()),
        "--out-dir", str(args.out_dir.resolve()), "--limit", "17123",
        "--route-release-schema", "portal-fiber-nested384", "--regions", "384",
        "--reference-source", "dp-flow", "--reference-conditioning", "portal-fiber",
        "--od-family-source", "released", "--od-likelihood-ratio-cap", "100",
        "--portal-count", "6", "--max-region-steps", "192", "--length-proposals", "9",
        "--length-log-penalty", "8", "--betas",
        "0.003,0.006,0.012,0.024,0.048,0.096,0.192,0.384,0.768",
        "--route-alignment", args.arm, "--decoder-seed", str(args.decoder_seed),
        "--request-seed", str(args.request_seed),
        "--production-postprocess",
    ]
    if args.public_fallback_cache is not None:
        sys.argv.extend(["--public-fallback-cache", str(args.public_fallback_cache.resolve())])
    if args.emit_matched_candidate_bank:
        sys.argv.append("--emit-matched-candidate-bank")
    if args.matched_candidate_bank is not None:
        sys.argv.extend(["--matched-candidate-bank", str(args.matched_candidate_bank.resolve())])
    decoder.main()


if __name__ == "__main__":
    main()

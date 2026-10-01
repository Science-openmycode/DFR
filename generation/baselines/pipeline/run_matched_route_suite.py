"""Run the three-arm matched q5 suite over sealed independent DP transcripts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_arm(out: Path, arm: str, decoder_seed: int, request_seed: int) -> dict | None:
    protocol_path = out / "protocol.json"
    if not protocol_path.is_file():
        return None
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if (
        protocol.get("classification") != "MATCHED_RESEARCH_AUTHENTICATED_DP_POSTPROCESS_DO_NOT_RELEASE"
        or protocol.get("certified_release") is not False
        or protocol.get("route_alignment") != arm
        or protocol.get("decoder_seed") != decoder_seed
        or protocol.get("request_seed") != request_seed
        or not isinstance(protocol.get("matched_candidate_contract"), dict)
    ):
        return None
    for filename, expected in protocol.get("outputs", {}).items():
        path = out / filename
        if not path.is_file() or sha256_file(path) != expected:
            return None
    contract = protocol["matched_candidate_contract"]
    shared_bank = out.parent / "public_only" / "candidate_bank.npz"
    if (
        contract.get("schema_id") != "mtr-matched-candidate-bank-v1"
        or contract.get("generation_arm") != "public-only"
        or not shared_bank.is_file()
        or sha256_file(shared_bank) != contract.get("candidate_bank_sha256")
        or not contract.get("candidate_order_sha256")
        or not contract.get("selection_uniform_sha256")
        or int(contract.get("candidate_count", 0)) <= 0
    ):
        return None
    if not (out / "DO_NOT_RELEASE.txt").is_file():
        return None
    return protocol


def atomic_manifest(path: Path, payload: dict) -> None:
    staging = path.with_suffix(path.suffix + ".staging")
    with staging.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staging, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--osm", type=Path, required=True)
    parser.add_argument("--seed", action="append", nargs=4, metavar=("NAME", "BASE", "PORTAL", "LEDGER"), required=True)
    parser.add_argument("--decoder-seed", type=int, default=93001)
    parser.add_argument("--request-seed", type=int, default=483729)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    runner = Path(__file__).with_name("run_matched_route_attribution.py")
    args.root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.root / "suite_manifest.json"
    shared = {
        "real": str(args.real.resolve()),
        "real_sha256": sha256_file(args.real.resolve()),
        "osm": str(args.osm.resolve()),
        "osm_sha256": sha256_file(args.osm.resolve()),
    }
    manifest = {
        "classification": "MATCHED_RESEARCH_CONTROLS_DO_NOT_RELEASE",
        "decoder_seed": args.decoder_seed,
        "request_seed": args.request_seed,
        "arms": [],
        "shared": shared,
    }
    if manifest_path.exists():
        if not args.resume:
            raise FileExistsError(f"Suite manifest already exists: {manifest_path}")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            existing.get("decoder_seed") != args.decoder_seed
            or existing.get("request_seed") != args.request_seed
            or existing.get("shared") != shared
        ):
            raise RuntimeError("Existing suite manifest disagrees with the fixed matched contract")
        manifest = existing
    for name, base, portal, ledger in args.seed:
        shared_candidate_bank = args.root / name / "public_only" / "candidate_bank.npz"
        for arm in ("public-only", "shuffled-dp", "correct-dp"):
            out = args.root / name / arm.replace("-", "_")
            protocol = verified_arm(out, arm, args.decoder_seed, args.request_seed) if out.exists() else None
            if protocol is not None and args.resume:
                print(f"[matched-suite] skip verified {name} {arm}", flush=True)
            else:
                if out.exists():
                    raise RuntimeError(f"Matched arm directory exists but is incomplete or invalid: {out}")
                command = [
                    sys.executable, str(runner), "--real", str(args.real), "--osm", str(args.osm),
                    "--base-dir", base, "--portal-dir", portal, "--out-dir", str(out),
                    "--audit-ledger", ledger, "--audit-id", name, "--arm", arm,
                    "--decoder-seed", str(args.decoder_seed),
                    "--request-seed", str(args.request_seed),
                    "--public-fallback-cache", str((args.root / name / "public_fallback.pkl").resolve()),
                ]
                if arm == "public-only":
                    command.append("--emit-matched-candidate-bank")
                else:
                    if not shared_candidate_bank.is_file():
                        raise FileNotFoundError(
                            f"Public-only candidate bank must exist before {arm}: {shared_candidate_bank}"
                        )
                    command.extend(["--matched-candidate-bank", str(shared_candidate_bank.resolve())])
                print(f"[matched-suite] {name} {arm}", flush=True)
                subprocess.run(command, check=True)
                protocol = verified_arm(out, arm, args.decoder_seed, args.request_seed)
                if protocol is None:
                    raise RuntimeError(f"Matched arm returned success but verification failed: {out}")
            entry = {
                "seed": name, "arm": arm, "out": str(out.resolve()),
                "request_sha256": protocol["inputs"]["request_sha256"],
                "q5_sha256": protocol["inputs"]["dp_route_release_sha256"],
                "witness_sha256": protocol["outputs"]["road_witnesses.pkl"],
                "candidate_bank_sha256": protocol["matched_candidate_contract"]["candidate_bank_sha256"],
                "candidate_order_sha256": protocol["matched_candidate_contract"]["candidate_order_sha256"],
                "selection_uniform_sha256": protocol["matched_candidate_contract"]["selection_uniform_sha256"],
            }
            manifest["arms"] = [
                item for item in manifest["arms"]
                if not (item.get("seed") == name and item.get("arm") == arm)
            ]
            manifest["arms"].append(entry)
            atomic_manifest(manifest_path, manifest)


if __name__ == "__main__":
    main()

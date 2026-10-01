"""Fail-closed audit of the complete MTR epsilon-by-seed artifact matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = "RESEARCH_ONLY_REPRODUCIBLE_NOISE_DO_NOT_RELEASE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def epsilon_dir(value: str) -> str:
    fraction = Fraction(value)
    return f"eps_{fraction.numerator}_{fraction.denominator}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="geolife")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "mtr_epsilon_sweep_beijing.json")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    input_root = (args.input_root or ROOT / "results" / "synthetic_datasets" / "mtr" / args.dataset).resolve()
    expected_count = int(config["expected_output_count"])
    expected_pairs = {(value, int(seed)) for value in config["epsilons"] for seed in config["noise_seeds"]}
    source_dir = ROOT / "src" / "mtr" / "DP_GSRT" / "final"
    rows = []
    failures = []
    for epsilon, seed in sorted(expected_pairs, key=lambda item: (Fraction(item[0]), item[1])):
        run_dir = input_root / epsilon_dir(epsilon) / f"seed_{seed}"
        protocol_path = run_dir / "protocol.json"
        if not protocol_path.is_file():
            failures.append(f"missing protocol: {protocol_path}")
            continue
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        checks = {
            "classification": protocol.get("classification") == CLASSIFICATION,
            "epsilon": protocol.get("privacy", {}).get("epsilon_total_rational") == str(Fraction(epsilon)),
            "noise_seed": protocol.get("privacy", {}).get("noise_seed") == seed,
            "delta_zero": protocol.get("privacy", {}).get("delta") == 0,
            "fixed_count": protocol.get("input_record_count") == protocol.get("output_count") == protocol.get("public_slot_count") == expected_count,
            "yield_one": protocol.get("output_yield") == 1.0,
            "fallback_zero": protocol.get("decoder", {}).get("fallback_count") == 0,
            "no_exact_serialization": protocol.get("shared_query_execution", {}).get("exact_totals_serialized") is False,
        }
        output_hashes = {}
        for name, expected_hash in protocol.get("outputs", {}).items():
            path = run_dir / name
            actual = sha256_file(path) if path.is_file() else None
            output_hashes[name] = actual
            checks[f"hash:{name}"] = actual == expected_hash
        bound_sources = {
            item["file"]: item["current_sha256"]
            for item in protocol.get("source_binding", {}).get("known_post_manifest_files", [])
        }
        current_sources = {
            name: sha256_file(source_dir / name) for name in bound_sources
        }
        checks["current_source_binding"] = bound_sources == current_sources
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            failures.append(f"{epsilon}/{seed}: {', '.join(failed)}")
        rows.append({
            "epsilon": epsilon,
            "noise_seed": seed,
            "run_dir": str(run_dir),
            "checks": checks,
            "recorded_sources": bound_sources,
            "current_sources": current_sources,
            "output_sha256": output_hashes,
        })
    observed_protocols = list(input_root.rglob("protocol.json"))
    if len(observed_protocols) != len(expected_pairs):
        failures.append(
            f"matrix contains {len(observed_protocols)} protocols; expected {len(expected_pairs)}"
        )
    report = {
        "schema_version": 1,
        "dataset": args.dataset,
        "input_root": str(input_root),
        "expected_matrix": {"epsilons": config["epsilons"], "noise_seeds": config["noise_seeds"]},
        "protocol_count": len(observed_protocols),
        "artifact_hash_count": sum(len(row["output_sha256"]) for row in rows),
        "passed": not failures,
        "failures": failures,
        "runs": rows,
    }
    out = (args.out or input_root / "matrix_audit.json").resolve()
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("protocol_count", "artifact_hash_count", "passed", "failures")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

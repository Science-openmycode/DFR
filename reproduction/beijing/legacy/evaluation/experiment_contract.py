"""Private-side experiment validation. Never include these records in a DP release.

This checks provenance, not the truth of a manually authored provenance claim.
No matching, routing, path completion, or synthesis happens here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from route_metric_core import load_pickle, normalize_routes

POPULATIONS = ("full-corpus", "accepted-road-subset")
REJECTED_REFERENCE_HASHES = {
    "b818a3e5e7f5681f22471b068b09741913ee17968abfec77babf6db074b149b3",
    "56db05d127a2d80292185a3e86d95550c825d5f0640dc25600f0c76f30941fd3",
    "df5bda6d92ba123a069657f86cb5cc8f366a8666a428d987eabfdb1c2f595168",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_synthetic_reference(path: Path) -> str:
    digest = sha(path)
    if digest in REJECTED_REFERENCE_HASHES:
        raise ValueError("Known synthetic artifact supplied as a real reference")
    side = path.with_name(path.name + ".manifest.json")
    if side.is_file():
        record = json.loads(side.read_text(encoding="utf-8-sig"))
        if (record.get("schema") == "road-route-coordinate-derivation-v1"
                or "synthetic" in str(record.get("classification", "")).lower()):
            raise ValueError("Derived/synthetic coordinates cannot be the raw real source")
    return digest


def validate_road_population(rows, cache, population: str) -> dict:
    if population not in POPULATIONS:
        raise ValueError("Unknown input population")
    public = set(map(tuple, cache["edge_nodes"].values()))
    try:
        routes = normalize_routes(rows, cache)
    except ValueError as exc:
        raise ValueError(f"unknown public edge in accepted private route: {exc}") from exc
    accepted = 0
    for route in routes:
        if not route:
            continue
        if any(edge not in public for edge in route):
            raise ValueError("unknown public edge in accepted private route")
        if any(a[1] != b[0] for a, b in zip(route, route[1:])):
            raise ValueError("disconnected accepted private route; no implicit repair permitted")
        accepted += 1
    record = {"source_slots": len(rows), "measured_routes": accepted,
              "excluded_slots": len(rows) - accepted, "population": population}
    if population == "full-corpus" and accepted != len(rows):
        raise ValueError("full-corpus requires all records to reach the declared measurement; "
                         f"source_slots={len(rows)}, measured_routes={accepted}. "
                         "Current DFR is road-record based; use accepted-road-subset only "
                         "for an explicitly conditional experiment, not as a full-corpus substitute.")
    return record


def validate_real_reference(matched: Path, raw: Path, cache, population: str,
                            network: Path | None = None) -> dict:
    matched, raw = Path(matched).resolve(), Path(raw).resolve()
    matched_sha = reject_synthetic_reference(matched)
    raw_sha = reject_synthetic_reference(raw)
    side = matched.with_name(matched.name.replace(".pkl.gz", ".manifest.json"))
    if side == matched or not side.is_file():
        raise ValueError("Real road reference requires an input/output-bound matching manifest")
    record = json.loads(side.read_text(encoding="utf-8-sig"))
    if record.get("classification") != "COMMON_MAP_MATCH_CACHE_NO_SYNTHESIS":
        raise ValueError("Real reference must come from the declared real-source matching step")
    if record.get("input_sha256") != raw_sha or record.get("output_sha256") != matched_sha:
        raise ValueError("Real reference source/output hash mismatch")
    if network is not None and record.get("network_sha256") != sha(network):
        raise ValueError("Real reference public network hash mismatch")
    rows, source = load_pickle(matched), load_pickle(raw)
    if isinstance(source, dict):
        source = next((source[key] for key in ("trajectories", "data") if key in source), source)
    if len(rows) != len(source) or record.get("record_count") != len(rows):
        raise ValueError("Real source/reference slot counts differ")
    return {**validate_road_population(rows, cache, population),
            "source_sha256": raw_sha, "matched_sha256": matched_sha,
            "matching_manifest_sha256": sha(side),
            "classification": "PRIVATE_EXPERIMENT_AUDIT_NOT_FOR_RELEASE"}


def validate_attack_indices(indices: dict) -> None:
    groups = {}
    for key in ("member_training", "member_candidates", "nonmember_candidates", "reference"):
        values = indices[key]
        groups[key] = set(values)
        if not values or len(values) != len(groups[key]):
            raise ValueError(f"Empty or duplicate attack indices: {key}")
    train, member, nonmember, ref = (groups[key] for key in groups)
    if not member <= train:
        raise ValueError("Member candidates were not used for training")
    if train & nonmember:
        raise ValueError("nonmember candidates overlap generator training")
    if train & ref or nonmember & ref:
        raise ValueError("Attack reference overlaps training/nonmembers")


def validate_native_mr_cell(method: str, router: str, binding: dict) -> None:
    if method not in {"MTR-DFR", "DPMM", "MTNet"}:
        return
    if router in {"Original", "Native"}:
        if binding.get("parameters", {}).get("matcher"):
            raise ValueError("Matched cache is not a native road release")
        return
    if method == "MTR-DFR" and binding.get("experiment_kind") == "dp_transcript_reroute":
        if not binding.get("transcript_sha256") or not binding.get("router_source_sha256"):
            raise ValueError("Transcript rerouting requires transcript/router code binding")
        if binding.get("private_access_after_measurement") is not False:
            raise ValueError("R may not read private records")
        return
    raise ValueError(f"{method}/{router}: native generator rematching is a secondary diagnostic, "
                     "not an M-by-R replacement; use its Original release")


def validate_routing_source(routes: Path, measurement: Path) -> dict:
    """Require an explicit, hash-bound public postprocessing source."""
    side = routes.with_name(routes.name.replace(".pkl.gz", ".manifest.json"))
    if side == routes or not side.is_file():
        raise ValueError("R output is missing its measurement-source manifest")
    record = json.loads(side.read_text(encoding="utf-8-sig"))
    if record.get("output_sha256") != sha(routes):
        raise ValueError("R output hash mismatch")
    if record.get("input_sha256") != sha(measurement):
        raise ValueError("R input differs from the declared measurement release")
    if record.get("classification") != "COMMON_MAP_MATCH_CACHE_NO_SYNTHESIS":
        raise ValueError("Unknown R provenance; explicit composition binding is required")
    return {"measurement_sha256": sha(measurement), "routed_sha256": sha(routes),
            "manifest_sha256": sha(side), "parameters": record.get("parameters", {})}


def validate_attack_release(split: Path, lineage: Path, release: Path,
                            members: Path, nonmembers: Path, reference: Path) -> dict:
    from synthesis_lineage import validate_record
    from run_tstr_experiment import base_release_hash
    record = json.loads(split.read_text(encoding="utf-8-sig"))
    validate_attack_indices(record["source_indices"])
    for key, path in (("member_candidates", members), ("nonmember_candidates", nonmembers),
                      ("reference", reference)):
        if record["artifacts"][key]["sha256"] != sha(path):
            raise ValueError(f"Attack candidate file does not match its split: {key}")
    bound = validate_record(lineage, record["artifacts"]["member_training"]["sha256"],
                            record["source_test_sha256"], base_release_hash(release))
    return {"verified": True, "attack_split_sha256": sha(split), **bound}


def validate_generation_source(ledger: Path, source: Path, release: Path, population: str) -> dict:
    from run_tstr_experiment import base_release_hash
    record = json.loads(ledger.read_text(encoding="utf-8-sig"))
    source_sha = reject_synthetic_reference(source)
    if record.get("classification") == "BASELINE_REPRODUCTION_WRAPPER_NOT_AN_MTR_RELEASE":
        input_sha = record.get("input", {}).get("sha256")
        scope = "full-corpus"
        extras = record.get("parameters", {}).get("extra_args", [])
        if any(str(item).split("=", 1)[0] in {"--n-train", "--limit"} for item in extras):
            raise ValueError("Restricted baseline input requires a separate population audit")
    else:
        audit = record.get("input_audit", {})
        input_sha, scope = audit.get("source_sha256"), audit.get("population")
    if input_sha != source_sha:
        raise ValueError("Generation source does not match evaluation real source")
    if scope != population:
        raise ValueError("Generation population differs from evaluation population")
    release_sha = base_release_hash(release)
    if release_sha not in record.get("outputs", {}).values():
        raise ValueError("Generation record does not bind the evaluated release")
    return {"record_sha256": sha(ledger), "source_sha256": source_sha,
            "release_sha256": release_sha, "population": scope,
            "evidence_scope": "executed-file provenance, not a formal privacy proof"}

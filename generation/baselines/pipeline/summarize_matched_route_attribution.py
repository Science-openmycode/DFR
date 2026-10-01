"""Summarize the sealed matched q5 experiment from route witnesses.

The synthetic side is read from the release-object directed-edge witnesses,
never re-snapped from coordinate polylines.  The real reference is projected
once to the same frozen public graph only to obtain a comparable diagnostic
edge sequence.  This is an evaluation operation, not part of the release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src" / "mtr" / "shared_graph", ROOT / "src" / "mtr" / "DP_GSRT" / "final"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from public_utils import filter_osm_ways_by_bbox, load_osm_ways, load_trajectories
from route_structure_potential_experiment import prepare_graph
from graph_voronoi_doptimal_support_probe import BBOX

ARMS = ("public_only", "shuffled_dp", "correct_dp")
PERIPHERAL_RING_BINS = 4
PERIPHERAL_TRUNK_TOP_K = 200


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixed_contract_fingerprint(protocol: dict) -> str:
    """Hash every protocol field that the matched arms are required to share."""
    inputs = protocol["inputs"]
    outputs = protocol["outputs"]
    length = protocol["length_conditioning"]
    fixed = {
        "algorithm": protocol["algorithm"],
        "classification": protocol.get("classification"),
        "certified_release": protocol.get("certified_release"),
        "implementation_source_sha256": protocol.get("implementation_source_sha256"),
        "reference_source": protocol["reference_source"],
        "reference_conditioning": protocol["reference_conditioning"],
        "route_release_schema": protocol["route_release_schema"],
        "decoder_seed": protocol["decoder_seed"],
        "request_seed": protocol["request_seed"],
        "od_family_source": protocol["od_family_source"],
        "od_family_granularity": protocol["od_family_granularity"],
        "limit": protocol["limit"],
        "quotient_regions": protocol["quotient_regions"],
        "od_likelihood_ratio_cap": protocol["od_likelihood_ratio_cap"],
        "betas_inverse_km": protocol["betas_inverse_km"],
        "matched_candidate_contract": protocol.get("matched_candidate_contract"),
        "length_conditioning": {
            "proposal_count": length["proposal_count"],
            "potential": length["potential"],
            "lambda": length["lambda"],
        },
        "graph": protocol["graph"],
        "release_object": protocol["release_object"],
        "inputs": {
            name: inputs.get(name)
            for name in (
                "request_sha256",
                "dp_route_release_sha256",
                "base_sanitizer_manifest_sha256",
                "portal_manifest_sha256",
                "public_osm_sha256",
                "fallback_input_sha256",
                "public_fallback_cache_sha256",
                "production_fallback_source",
            )
        },
        "public_fallback_output_sha256": outputs.get(
            "dp_request_public_shortest_path_control.pkl"
        ),
    }
    encoded = json.dumps(fixed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def jsd_counts(left: Counter, right: Counter) -> float:
    keys = sorted(set(left) | set(right), key=repr)
    a = np.asarray([left[key] for key in keys], dtype=float)
    b = np.asarray([right[key] for key in keys], dtype=float)
    a = (a + 1e-12) / (a.sum() + 1e-12 * len(a))
    b = (b + 1e-12) / (b.sum() + 1e-12 * len(b))
    m = .5 * (a + b)
    return float(.5 * ((a * np.log2(a / m)).sum() + (b * np.log2(b / m)).sum()))


def mass_weighted_topk_recall(target: Counter, candidate: Counter, k: int) -> float:
    """Recall of a frozen target top-k set, weighted by target mass.

    Ties are resolved by ``repr`` so the selected target set is independent of
    dictionary insertion order.  Candidate magnitudes do not affect recall;
    an atom is recovered exactly when its released witness count is positive.
    """
    if k <= 0:
        raise ValueError("top-k must be positive")
    ranked = sorted(target.items(), key=lambda item: (-item[1], repr(item[0])))[:k]
    denominator = float(sum(value for _, value in ranked))
    if denominator <= 0:
        return 0.0
    numerator = sum(value for key, value in ranked if candidate.get(key, 0) > 0)
    return float(numerator / denominator)


def edge_sequences_from_real(real: list[np.ndarray], coords: np.ndarray, graph: dict) -> list[list[tuple[int, int]]]:
    tree = cKDTree(coords)
    edges = {(int(u), int(v)) for u, ns in graph.items() for v, _ in ns}
    sequences = []
    for trajectory in real:
        points = np.asarray(trajectory, dtype=float)
        points = points[np.linspace(0, len(points) - 1, min(len(points), 128)).round().astype(int)]
        nodes = tree.query(points, k=1)[1].astype(int).tolist()
        nodes = [node for i, node in enumerate(nodes) if not i or node != nodes[i - 1]]
        sequences.append([(u, v) for u, v in zip(nodes[:-1], nodes[1:]) if (u, v) in edges])
    return sequences


def load_witnesses(path: Path, edges: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    with path.open("rb") as handle:
        rows = pickle.load(handle)
    if not isinstance(rows, list):
        raise ValueError(f"Witness sidecar is not a list: {path}")
    output = []
    for slot, row in enumerate(rows):
        if not isinstance(row, dict) or int(row.get("slot", -1)) != slot:
            raise ValueError(f"Invalid witness slot in {path}")
        sequence = [tuple(map(int, pair)) for pair in (row.get("directed_edges") or [])]
        if any(pair not in edges for pair in sequence):
            raise ValueError(f"Witness contains an edge outside frozen public graph: {path}")
        if any(left[1] != right[0] for left, right in zip(sequence[:-1], sequence[1:])):
            raise ValueError(f"Witness path is discontinuous: {path}")
        output.append(sequence)
    return output


def counters(sequences: list[list[tuple[int, int]]], coords: np.ndarray, grid: int = 24) -> dict[str, Counter]:
    edge = Counter(item for sequence in sequences for item in sequence)
    transition = Counter((left, right) for sequence in sequences for left, right in zip(sequence[:-1], sequence[1:]))
    corridor = Counter()
    peripheral_corridor = Counter()
    lo = np.asarray([BBOX[0], BBOX[2]]); span = np.asarray([BBOX[1] - BBOX[0], BBOX[3] - BBOX[2]])
    for sequence in sequences:
        if not sequence:
            continue
        start = coords[sequence[0][0]]; end = coords[sequence[-1][1]]
        bins = np.clip(((np.vstack((start, end)) - lo) / span * grid).astype(int), 0, grid - 1)
        od = (int(bins[0, 0] * grid + bins[0, 1]), int(bins[1, 0] * grid + bins[1, 1]))
        corridor.update((od, item) for item in sequence)
        peripheral = bool(
            np.any(bins < PERIPHERAL_RING_BINS)
            or np.any(bins >= grid - PERIPHERAL_RING_BINS)
        )
        if peripheral:
            peripheral_corridor.update((od, item) for item in sequence)
    return {
        "edge": edge,
        "transition": transition,
        "od_corridor": corridor,
        "peripheral_corridor": peripheral_corridor,
    }


def score_counters(target: dict[str, Counter], candidate: dict[str, Counter]) -> dict[str, float]:
    return {
        "edge_jsd": jsd_counts(target["edge"], candidate["edge"]),
        "transition_jsd": jsd_counts(target["transition"], candidate["transition"]),
        "od_corridor_jsd": jsd_counts(target["od_corridor"], candidate["od_corridor"]),
        "peripheral_trunk_recall": mass_weighted_topk_recall(
            target["peripheral_corridor"],
            candidate["peripheral_corridor"],
            PERIPHERAL_TRUNK_TOP_K,
        ),
    }


def acceptance_decision(per_seed: list[dict]) -> dict:
    """Apply the preregistered strict-direction rule to the three primary endpoints."""
    directions = {
        "od_corridor_jsd": "lower",
        "transition_jsd": "lower",
        "peripheral_trunk_recall": "higher",
    }
    checks = []
    for row in per_seed:
        seed_checks = {}
        for metric, direction in directions.items():
            correct = float(row["arms"]["correct_dp"][metric])
            controls = (
                float(row["arms"]["public_only"][metric]),
                float(row["arms"]["shuffled_dp"][metric]),
            )
            seed_checks[metric] = (
                correct < min(controls) if direction == "lower" else correct > max(controls)
            )
        checks.append({"seed": row["seed"], "metrics": seed_checks, "all_primary": all(seed_checks.values())})
    passed = bool(checks) and all(row["all_primary"] for row in checks)
    return {
        "rule": "Correct-DP must strictly improve over both Public-only and Shuffled-DP on all three primary endpoints for every independent DP-noise seed.",
        "directions": directions,
        "per_seed": checks,
        "passed": passed,
        "claim_if_failed": "Treat q5 only as an optional bounded route-distribution refinement; do not claim causal route-choice improvement.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--osm", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    real = load_trajectories(str(args.real), limit=None)
    osm = filter_osm_ways_by_bbox(load_osm_ways(args.osm), BBOX)
    coords, graph = prepare_graph(real, bbox=BBOX, osm_ways=osm, raw_graph=False)
    public_edges = {(int(u), int(v)) for u, ns in graph.items() for v, _ in ns}
    target = counters(edge_sequences_from_real(real, coords, graph), coords)
    per_seed = []
    for seed_dir in sorted(path for path in args.suite_root.iterdir() if path.is_dir()):
        row = {"seed": seed_dir.name, "arms": {}}
        fixed_inputs = {"request_sha256": set(), "dp_route_release_sha256": set(), "public_osm_sha256": set()}
        fixed_randomness = {"decoder_seed": set(), "request_seed": set()}
        fixed_contracts = set()
        matched_candidate_contracts = set()
        for arm in ARMS:
            protocol_path = seed_dir / arm / "protocol.json"
            witness_path = seed_dir / arm / "road_witnesses.pkl"
            if not protocol_path.exists() or not witness_path.exists():
                raise FileNotFoundError(f"Incomplete matched suite arm: {seed_dir.name}/{arm}")
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            if (
                protocol.get("classification")
                != "MATCHED_RESEARCH_AUTHENTICATED_DP_POSTPROCESS_DO_NOT_RELEASE"
                or protocol.get("certified_release") is not False
                or protocol.get("privacy_accounting", {}).get("composed_epsilon_rational") != "7/5"
                or float(protocol.get("privacy_accounting", {}).get("delta", -1)) != 0.0
                or not (seed_dir / arm / "DO_NOT_RELEASE.txt").is_file()
            ):
                raise ValueError(f"Matched arm has an invalid research/privacy classification: {seed_dir.name}/{arm}")
            for filename, expected_hash in protocol.get("outputs", {}).items():
                output_path = seed_dir / arm / filename
                if not output_path.is_file() or sha256_file(output_path) != expected_hash:
                    raise ValueError(f"Matched arm output hash mismatch: {seed_dir.name}/{arm}/{filename}")
            for name in fixed_inputs:
                fixed_inputs[name].add(protocol["inputs"][name])
            report = protocol
            matched_contract = report.get("matched_candidate_contract")
            if (
                not isinstance(matched_contract, dict)
                or matched_contract.get("schema_id") != "mtr-matched-candidate-bank-v1"
                or matched_contract.get("generation_arm") != "public-only"
                or not matched_contract.get("candidate_bank_sha256")
                or not matched_contract.get("candidate_order_sha256")
                or not matched_contract.get("selection_uniform_sha256")
                or int(matched_contract.get("candidate_count", 0)) <= 0
            ):
                raise ValueError(f"Missing strict matched candidate contract: {seed_dir.name}/{arm}")
            matched_candidate_contracts.add(json.dumps(matched_contract, sort_keys=True))
            for name in fixed_randomness:
                fixed_randomness[name].add(report.get(name))
            fixed_contracts.add(fixed_contract_fingerprint(report))
            expected_alignment = arm.replace("_", "-")
            if report.get("route_alignment") != expected_alignment:
                raise ValueError(f"Unexpected route alignment in {seed_dir.name}/{arm}")
            seq = load_witnesses(witness_path, public_edges)
            if len(seq) != int(protocol.get("limit", -1)) or len(seq) != 17123:
                raise ValueError(f"Matched arm has the wrong fixed slot count: {seed_dir.name}/{arm}")
            values = counters(seq, coords)
            row["arms"][arm] = score_counters(target, values)
            row["arms"][arm]["witness_count"] = len(seq)
        if any(len(values) != 1 for values in fixed_inputs.values()):
            raise ValueError(f"Unmatched sealed transcript or public input within seed {seed_dir.name}")
        if any(len(values) != 1 or None in values for values in fixed_randomness.values()):
            raise ValueError(f"Unmatched or unrecorded random stream within seed {seed_dir.name}")
        if len(fixed_contracts) != 1:
            raise ValueError(
                f"Matched arms changed a fixed candidate/fallback/serialization contract: {seed_dir.name}"
            )
        if len(matched_candidate_contracts) != 1:
            raise ValueError(
                f"Matched arms do not share the exact candidate order and selection stream: {seed_dir.name}"
            )
        public_bank = seed_dir / "public_only" / "candidate_bank.npz"
        matched_contract = json.loads(next(iter(matched_candidate_contracts)))
        if (
            not public_bank.is_file()
            or sha256_file(public_bank) != matched_contract["candidate_bank_sha256"]
        ):
            raise ValueError(f"Shared matched candidate bank hash mismatch: {seed_dir.name}")
        row["fixed_contract_sha256"] = next(iter(fixed_contracts))
        row["candidate_order_sha256"] = matched_contract["candidate_order_sha256"]
        row["selection_uniform_sha256"] = matched_contract["selection_uniform_sha256"]
        per_seed.append(row)
    if not per_seed:
        raise RuntimeError("matched suite contains no DP-noise seed directories")
    summary = {"protocol": {"synthetic_metric_source": "directed edge witness sidecars", "real_reference": "one fixed public-graph projection", "independent_unit": "sealed DP transcript seed", "n_seeds": len(per_seed), "peripheral_definition": f"origin or destination lies in the outer {PERIPHERAL_RING_BINS} bins of the fixed 24x24 bbox grid", "peripheral_trunk_top_k": PERIPHERAL_TRUNK_TOP_K, "peripheral_trunk_recall": "real-mass-weighted recovery of the frozen top-k peripheral OD-directed-edge atoms"}, "per_seed": per_seed, "mean_sd": {}, "acceptance": acceptance_decision(per_seed)}
    for arm in ARMS:
        summary["mean_sd"][arm] = {}
        for metric in per_seed[0]["arms"][arm]:
            vals = np.asarray([row["arms"][arm][metric] for row in per_seed], dtype=float)
            summary["mean_sd"][arm][metric] = {"mean": float(vals.mean()), "sd": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["mean_sd"], indent=2))


if __name__ == "__main__":
    main()

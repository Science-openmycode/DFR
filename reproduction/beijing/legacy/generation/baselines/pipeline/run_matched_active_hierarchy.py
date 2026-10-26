from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path


PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PUBLIC_RELEASE
for path in (
    PUBLIC_RELEASE,
    PUBLIC_RELEASE / "pipeline",
    PUBLIC_RELEASE / "src" / "mtr" / "shared_graph",
    PUBLIC_RELEASE / "src" / "mtr" / "DP_GSRT" / "final",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generation.common.runtime import sha256_file  # noqa: E402
from public_utils import filter_osm_ways_by_bbox, load_osm_ways, load_trajectories  # noqa: E402
from graph_voronoi_doptimal_support_probe import BBOX  # noqa: E402
from route_structure_potential_experiment import prepare_graph  # noqa: E402
from summarize_matched_route_attribution import (  # noqa: E402
    acceptance_decision,
    counters,
    edge_sequences_from_real,
    load_witnesses,
    score_counters,
)


ARMS = ("public_only", "shuffled_dp", "correct_dp")
SEEDS = ("seed_v4", "seed_v5")
SOURCE_FILES = {
    "base": Path("base/sanitized_base_geometry.npz"),
    "graph_flow": Path("base/sanitized_compact_graph_flow.npz"),
    "portal_fiber_q5": Path("portal/portal_fiber_route_dp_release.npz"),
    "audit_manifest": Path("audit_instance_manifest.json"),
}


def verify_resume(suite_root: Path, summary: dict) -> None:
    if len(summary.get("per_seed", [])) != 2:
        raise RuntimeError("existing matched suite is incomplete")
    for seed_row in summary["per_seed"]:
        if set(seed_row.get("arms", {})) != set(ARMS):
            raise RuntimeError("existing matched suite arm matrix is incomplete")
        hashes = {
            tuple(sorted(arm["source_dp_hashes"].items()))
            for arm in seed_row["arms"].values()
        }
        if len(hashes) != 1:
            raise RuntimeError("matched arms do not share one DP transcript")
        expected = dict(next(iter(hashes)))
        source = PUBLIC_RELEASE / "outputs" / "matched_q5_20260717" / seed_row["seed"]
        for key, relative in SOURCE_FILES.items():
            path = source / relative
            if not path.is_file() or sha256_file(path) != expected[key]:
                raise RuntimeError(f"matched source hash mismatch: {seed_row['seed']}/{key}")
    manifest_path = suite_root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("matched resume manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in manifest["outputs"].items():
        if sha256_file(suite_root / relative) != expected:
            raise RuntimeError(f"matched output hash mismatch: {relative}")
    for relative, expected in manifest["implementations"].items():
        if sha256_file(PUBLIC_RELEASE / relative) != expected:
            raise RuntimeError(f"matched implementation hash mismatch: {relative}")


def decode_and_score(
    seed: str,
    arm: str,
    suite_root: Path,
    target: dict,
    coordinates,
    public_edges: set[tuple[int, int]],
) -> dict:
    source = PUBLIC_RELEASE / "outputs" / "matched_q5_20260717" / seed
    out = suite_root / seed / arm
    command = [
        sys.executable,
        str(PUBLIC_RELEASE / "pipeline" / "redecode_active_hierarchy_transcript.py"),
        "--source-root",
        str(source),
        "--out-dir",
        str(out),
        "--decoder-seed",
        "93001",
        "--request-seed",
        "483729",
        "--occupancy-strength",
        "0.25",
        "--dwell-strength",
        "0.10",
        "--hierarchy-likelihood-ratio-cap",
        "100",
        "--route-alignment",
        arm.replace("_", "-"),
    ]
    log = PUBLIC_RELEASE / "logs" / "matched_active_hierarchy" / f"{seed}_{arm}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"candidate matched arm failed; see {log}")
    protocol_path = out / "protocol.json"
    witness_path = out / "road_witnesses.pkl"
    trajectory_path = out / "trajectories.pkl"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if (
        protocol["postprocessing"]["route_alignment"] != arm.replace("_", "-")
        or protocol["new_private_access"] is not False
        or protocol["additional_privacy_cost"] != 0
        or protocol["output_count"] != 17123
    ):
        raise RuntimeError(f"candidate matched contract mismatch: {seed}/{arm}")
    if sha256_file(witness_path) != protocol["outputs"]["road_witnesses.pkl"]:
        raise RuntimeError(f"candidate witness hash mismatch: {seed}/{arm}")
    if sha256_file(trajectory_path) != protocol["outputs"]["trajectories.pkl"]:
        raise RuntimeError(f"candidate trajectory hash mismatch: {seed}/{arm}")
    sequences = load_witnesses(witness_path, public_edges)
    values = score_counters(target, counters(sequences, coordinates))
    values.update(
        {
            "witness_count": len(sequences),
            "seconds": time.time() - started,
            "source_dp_hashes": protocol["source_hashes"],
            "trajectory_sha256": protocol["outputs"]["trajectories.pkl"],
            "witness_sha256": protocol["outputs"]["road_witnesses.pkl"],
            "protocol_sha256": sha256_file(protocol_path),
        }
    )
    # These large objects are exactly reproducible from the sealed DP transcript
    # and recorded public seeds. Retain their hashes and protocol, then release
    # disk space for the next isolated arm.
    trajectory_path.unlink()
    witness_path.unlink()
    (out / "PRUNED_REPRODUCIBLE_FILES.json").write_text(
        json.dumps(
            {
                "reason": "hash-verified candidate object pruned after metric extraction",
                "reproduce_command": command,
                "removed": {
                    "trajectories.pkl": values["trajectory_sha256"],
                    "road_witnesses.pkl": values["witness_sha256"],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated active-hierarchy MTR-GSRT Public-only, "
            "Shuffled-DP, and Correct-DP controls on two sealed DP transcripts."
        )
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PUBLIC_RELEASE / "results" / "matched_active_hierarchy" / "current",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--what-if", action="store_true")
    args = parser.parse_args()
    suite_root = args.out_dir.resolve()
    if args.what_if:
        for seed in SEEDS:
            for arm in ARMS:
                print(f"DECODE_AND_SCORE seed={seed} arm={arm}")
        print("SUMMARIZE matched_active_hierarchy")
        return
    if suite_root.exists():
        summary_path = suite_root / "matched_summary.json"
        if not args.resume or not summary_path.is_file():
            raise FileExistsError(f"matched suite already exists: {suite_root}")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        verify_resume(suite_root, summary)
        print(json.dumps({"status": "verified-resume", "runs": 6}))
        return
    suite_root.mkdir(parents=True)

    real_path = PUBLIC_RELEASE / "outputs" / "kdd_revised" / "split" / "real_full_frozen.pkl"
    osm_path = PUBLIC_RELEASE / "data" / "osm" / "osm_cache_beijing.pkl"
    real = load_trajectories(str(real_path), limit=None)
    osm = filter_osm_ways_by_bbox(load_osm_ways(osm_path), BBOX)
    coordinates, graph = prepare_graph(real, bbox=BBOX, osm_ways=osm, raw_graph=False)
    public_edges = {(int(u), int(v)) for u, neighbors in graph.items() for v, _ in neighbors}
    target = counters(edge_sequences_from_real(real, coordinates, graph), coordinates)
    del real, osm, graph

    per_seed = []
    for seed in SEEDS:
        row = {"seed": seed, "arms": {}}
        for arm in ARMS:
            row["arms"][arm] = decode_and_score(
                seed, arm, suite_root, target, coordinates, public_edges
            )
            print(
                json.dumps(
                    {
                        "seed": seed,
                        "arm": arm,
                        "metrics": {
                            key: value
                            for key, value in row["arms"][arm].items()
                            if isinstance(value, (int, float))
                        },
                    }
                ),
                flush=True,
            )
        per_seed.append(row)

    summary = {
        "schema_version": 1,
        "classification": "RESEARCH_ACTIVE_HIERARCHY_MATCHED_CONTROLS_DO_NOT_RELEASE",
        "algorithm_id": "mtr-gsrt-active-hierarchy-v1",
        "experiment_revision": "matched_v3_corrected_decoder_parameters",
        "only_mtr_gsrt_recomputed": True,
        "matching": {
            "same_sealed_dp_transcript_within_seed": True,
            "same_decoder_seed": 93001,
            "same_request_seed": 483729,
            "arms": list(ARMS),
            "independent_dp_transcripts": list(SEEDS),
        },
        "per_seed": per_seed,
        "acceptance": acceptance_decision(per_seed),
    }
    summary_path = suite_root / "matched_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    implementations = (
        Path("pipeline/run_matched_active_hierarchy.py"),
        Path("pipeline/redecode_active_hierarchy_transcript.py"),
        Path("pipeline/summarize_matched_route_attribution.py"),
    )
    (suite_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "CURRENT_ACTIVE_HIERARCHY_MATCHED_EVIDENCE",
                "outputs": {"matched_summary.json": sha256_file(summary_path)},
                "implementations": {
                    str(path).replace("\\", "/"): sha256_file(PUBLIC_RELEASE / path)
                    for path in implementations
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary["acceptance"], indent=2))


if __name__ == "__main__":
    main()

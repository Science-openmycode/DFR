"""Standalone minimal Strong-Family MTR for the Beijing road corpus.

The mechanism has exactly two private releases: (i) a factorized endpoint
demand carrier and (ii) a stable histogram of complete Region96 route
families plus a noisy record count.  Every road path is then constructed on
the declared public road graph.  This exploration never edits public_release.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import pickle
import secrets
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LEGACY = REPO / "exploration" / "public_prior_tdrive_20260829"
sys.path.insert(0, str(LEGACY))
sys.path.insert(0, str(REPO.parent / "evaluation"))
from experiment_contract import validate_road_population, reject_synthetic_reference

EDGE_CACHE = HERE / 'ordered_portal_route_cache.pkl.gz'
REAL_MATCHED = HERE / 'Real.pkl.gz'
NETWORK = HERE / 'network.shp'
# The public repository keeps the protocol inputs under public_assets.  The
# local algorithm directory remains supported for the original standalone
# layout, while this fallback makes the CLI reproducible from a clean clone.
if not EDGE_CACHE.exists():
    EDGE_CACHE = REPO.parent / 'public_assets' / 'ordered_portal_route_cache.pkl.gz'
if not REAL_MATCHED.exists():
    REAL_MATCHED = REPO.parent.parent / 'check' / 'budget14_eval' / 'stmatch_parallel' / 'matched_paths' / 'Real.pkl.gz'
if not NETWORK.exists():
    NETWORK = REPO.parent / 'public_assets' / 'beijing_network' / 'network.shp'
from dfr_compat import (EdgeStateRouter, constrained_path, digest, family, heading,
                        road_class, sample_counter, stable_release)  # noqa: E402


# The relative allocation is inherited from the DFR design.  All reported
# comparisons use the common total epsilon=1.4; the scale is chosen per
# release variant so adding the optional length query does not change the
# total privacy budget.
EPS_FINE_BASE = 0.04
EPS_ENDPOINT_ATOM_BASE = 0.28
EPS_OD_BASE = 0.33
EPS_FAMILY_BASE = 0.38
EPS_COUNT_BASE = 0.02
EPS_LENGTH_BASE = 0.10
TOTAL_EPSILON = 1.4
DELTA_FAMILY = 1e-6
# Public default for the frozen Beijing experiment.  It is a public protocol
# parameter, not a value inferred from the private input record count.  Other
# release sizes must be supplied explicitly with --public-slot-count.
DEFAULT_PUBLIC_SLOT_COUNT = 17123
SELECTED_CELLS_PER_ROLE = 8
POPULATION_SCOPE = "full-corpus"
PUBLIC_VARIANTS_PER_FAMILY = 16
MAX_ENDPOINT_PAIRS_PER_FAMILY = 96
LENGTH_BINS_KM = np.asarray([0.0, .5, 1, 2, 3, 5, 8, 12, 20, 35, 60, 100, np.inf])


def budget_components(length_aware=False, total_epsilon=TOTAL_EPSILON):
    """Return the proportional DFR allocation for a requested total budget."""
    if not math.isfinite(float(total_epsilon)) or float(total_epsilon) <= 0:
        raise ValueError("epsilon must be positive and finite")
    raw = {
        "fine_endpoint": EPS_FINE_BASE,
        "endpoint_atom": EPS_ENDPOINT_ATOM_BASE,
        "coarse_od": EPS_OD_BASE,
        "stable_family": EPS_FAMILY_BASE,
        "noisy_total": EPS_COUNT_BASE,
    }
    if length_aware:
        raw["global_length"] = EPS_LENGTH_BASE
    scale = float(total_epsilon) / sum(raw.values())
    return {key: value * scale for key, value in raw.items()}


def load_private_inputs():
    """Load only the declared public graph cache and private road records."""
    reject_synthetic_reference(REAL_MATCHED)
    with gzip.open(EDGE_CACHE, "rb") as handle:
        cache = pickle.load(handle)
    edge_nodes = cache["edge_nodes"]
    with gzip.open(REAL_MATCHED, "rb") as handle:
        matched = pickle.load(handle)
    validate_road_population(matched, cache, POPULATION_SCOPE)
    real = [tuple(edge_nodes[int(edge)] for edge in row["cpath"])
            for row in matched if row.get("accepted") and row.get("cpath")]
    return cache, real


def probability(values):
    values = np.maximum(np.asarray(values, dtype=float), 0.0)
    total = float(values.sum())
    return values / total if total else np.full(len(values), 1.0 / len(values))


def sample_index(values, rng):
    return int(rng.choice(len(values), p=probability(values)))


def fixed_allocation(weights, scale, slots):
    """Largest-remainder allocation with a public fixed-slot cap."""
    raw = {key: max(float(value) * scale, 0.0) for key, value in weights.items()}
    total = sum(raw.values())
    if total > slots and total:
        raw = {key: value * slots / total for key, value in raw.items()}
    counts = {key: int(math.floor(value)) for key, value in raw.items()}
    remaining = min(slots - sum(counts.values()),
                    int(round(sum(raw.values()))) - sum(counts.values()))
    if remaining > 0:
        order = sorted(raw, key=lambda key: (raw[key] - counts[key], repr(key)), reverse=True)
        for key in order[:remaining]:
            counts[key] += 1
    return {key: value for key, value in counts.items() if value > 0}


def build_public_endpoint_domain(cache):
    edge_nodes = cache["edge_nodes"]
    edges = sorted(set(tuple(edge) for edge in edge_nodes.values()))
    ids = defaultdict(list)
    for edge_id, edge in edge_nodes.items():
        ids[tuple(edge)].append(int(edge_id))
    frame = gpd.read_file(NETWORK)[["id", "osm_way", "highway", "geometry"]]
    by_id = {int(row.id): (str(row.osm_way), road_class(row.highway), heading(row.geometry))
             for row in frame.itertuples(index=False)}
    attrs = {}
    for edge in edges:
        candidates = [edge_id for edge_id in ids[edge] if edge_id in by_id]
        if candidates:
            attrs[edge] = by_id[min(candidates)]
        else:
            attrs[edge] = ("UNKNOWN_PUBLIC_WAY", "other", 0)
    return edges, attrs


def measure_and_sample_endpoints(cache, real, seed, *, length_aware=False, router=None,
                                 length_candidates=8, public_detour_factor=1.25,
                                 slots=DEFAULT_PUBLIC_SLOT_COUNT, budget=None):
    budget = budget or budget_components(length_aware)
    labels384, labels24 = cache["labels384"], cache["labels24"]
    edges, attrs = build_public_endpoint_domain(cache)
    parent_votes = defaultdict(Counter)
    for node, fine in labels384.items():
        if node in labels24:
            parent_votes[int(fine)][int(labels24[node])] += 1
    parent = {fine: votes.most_common(1)[0][0] for fine, votes in parent_votes.items()}
    fine_by_parent = defaultdict(list)
    for fine in range(384):
        fine_by_parent[parent.get(fine, 0)].append(fine)

    endpoint_rows = []
    exact_cells = np.zeros((2, 384), dtype=float)
    exact_od = np.zeros((24, 24), dtype=float)
    exact_length = np.zeros(len(LENGTH_BINS_KM) - 1, dtype=float)
    for path in real:
        if not path:
            continue
        row = []
        for role, edge in enumerate((path[0], path[-1])):
            node = edge[0 if role == 0 else 1]
            cell = int(labels384[node])
            row.append((edge, cell, attrs[edge]))
            exact_cells[role, cell] += 0.5
        endpoint_rows.append(row)
        exact_od[parent[row[0][1]], parent[row[1][1]]] += 1.0
        if length_aware:
            if router is None:
                raise ValueError("length-aware endpoint sampling requires the public router")
            length = sum(router.length.get(edge, 0.0) for edge in path) / 1000.0
            index = min(int(np.searchsorted(LENGTH_BINS_KM, length, side="right") - 1),
                        len(exact_length) - 1)
            exact_length[index] += 1.0

    fine_rng, atom_rng, od_rng, length_rng, sample_rng = [
        np.random.default_rng(child) for child in np.random.SeedSequence(seed).spawn(5)]
    noisy_cells = exact_cells + fine_rng.laplace(
        0.0, 1.0 / budget["fine_endpoint"], exact_cells.shape)
    noisy_od = exact_od + od_rng.laplace(
        0.0, 1.0 / budget["coarse_od"], exact_od.shape)
    noisy_length = (exact_length + length_rng.laplace(
        0.0, 1.0 / budget["global_length"], exact_length.shape)
                    if length_aware else None)
    selected = set()
    for role in range(2):
        for cell in np.argpartition(noisy_cells[role], -SELECTED_CELLS_PER_ROLE)[
                -SELECTED_CELLS_PER_ROLE:]:
            selected.add((role, int(cell)))

    def atom(role, edge, cell, attr):
        return ((role, "head_way", cell, attr[0]) if (role, cell) in selected
                else (role, "tail_cell", cell))

    public_atoms = defaultdict(list)
    edges_by_role_cell = defaultdict(list)
    for role in range(2):
        for edge in edges:
            node = edge[0 if role == 0 else 1]
            cell = int(labels384[node])
            public_atoms[atom(role, edge, cell, attrs[edge])].append(edge)
            edges_by_role_cell[(role, cell)].append(edge)
    exact_atoms = Counter()
    for row in endpoint_rows:
        for role, (edge, cell, attr) in enumerate(row):
            exact_atoms[atom(role, edge, cell, attr)] += 0.5
    noisy_atoms = {key: max(0.0, exact_atoms.get(key, 0.0) +
                            atom_rng.laplace(0.0, 1.0 / budget["endpoint_atom"]))
                   for key in public_atoms}
    endpoint_prior = defaultdict(Counter)
    for key, value in noisy_atoms.items():
        for edge in public_atoms[key]:
            role = int(key[0])
            node = edge[0 if role == 0 else 1]
            cell = int(labels384[node])
            endpoint_prior[(role, cell)][edge] += value / len(public_atoms[key])

    coarse_pairs = [(left, right) for left in range(24) for right in range(24)]
    coarse_p = probability([noisy_od[pair] for pair in coarse_pairs])
    def draw_endpoint_pair(coarse_o, coarse_d):
        source_cells = fine_by_parent.get(coarse_o, list(range(384)))
        dest_cells = fine_by_parent.get(coarse_d, list(range(384)))
        source_cell = source_cells[sample_index(
            [noisy_cells[0, cell] for cell in source_cells], sample_rng)]
        dest_cell = dest_cells[sample_index(
            [noisy_cells[1, cell] for cell in dest_cells], sample_rng)]
        source_edge = sample_counter(endpoint_prior.get((0, source_cell), {}), sample_rng)
        dest_edge = sample_counter(endpoint_prior.get((1, dest_cell), {}), sample_rng)
        if source_edge is None:
            source_edge = edges_by_role_cell[(0, source_cell)][0]
            fallback["source"] += 1
        if dest_edge is None:
            dest_edge = edges_by_role_cell[(1, dest_cell)][0]
            fallback["destination"] += 1
        return tuple(source_edge), tuple(dest_edge)

    def public_distance_score(pair, target):
        source_edge, dest_edge = pair
        left, right = source_edge[0], dest_edge[1]
        if router is None or left not in router.xy or right not in router.xy:
            return math.inf
        dx = router.xy[left][0] - router.xy[right][0]
        dy = router.xy[left][1] - router.xy[right][1]
        estimate = max(math.hypot(dx, dy) / 1000.0 * public_detour_factor, 1e-3)
        return abs(math.log(estimate / max(target, 1e-3)))

    def length_midpoint(index):
        left, right = LENGTH_BINS_KM[index], LENGTH_BINS_KM[index + 1]
        return 130.0 if not np.isfinite(right) else (left + right) / 2.0

    endpoints = []
    fallback = Counter()
    for _ in range(slots):
        coarse_o, coarse_d = coarse_pairs[int(sample_rng.choice(len(coarse_pairs), p=coarse_p))]
        if length_aware:
            length_index = sample_index(noisy_length, sample_rng)
            target = length_midpoint(length_index)
            candidates = [draw_endpoint_pair(coarse_o, coarse_d)
                          for _attempt in range(length_candidates)]
            endpoints.append(min(candidates, key=lambda pair: public_distance_score(pair, target)))
        else:
            endpoints.append(draw_endpoint_pair(coarse_o, coarse_d))
    transcript = {
        "selected_cells": sorted([list(value) for value in selected]),
        "noisy_cells": noisy_cells.tolist(),
        "noisy_od": noisy_od.tolist(),
        "noisy_length": noisy_length.tolist() if noisy_length is not None else None,
        "length_aware": length_aware,
        "length_candidates": length_candidates if length_aware else None,
        "public_detour_factor": public_detour_factor if length_aware else None,
        "noisy_atoms": [(list(key), float(value)) for key, value in noisy_atoms.items()],
        "fallback_counts": dict(fallback),
    }
    return endpoints, transcript


def public_shortest_routes(cache, endpoints, router=None):
    router = router or EdgeStateRouter(NETWORK, cache["edge_nodes"],
                                      {None: {}}, {None: {}}, 0.0, 0.0)
    routes, states = [], Counter()
    for source_edge, destination_edge in endpoints:
        route = router.path(source_edge, destination_edge)
        if route:
            routes.append(tuple(route)); states["public_shortest"] += 1
        else:
            routes.append((source_edge,)); states["single_edge_fallback"] += 1
    return router, routes, states


def route_family_release(cache, real, endpoints, public_tail, router, seed, oracle=None,
                         slots=DEFAULT_PUBLIC_SLOT_COUNT, budget=None):
    budget = budget or budget_components(False)
    labels = cache["labels96"]
    endpoint_pool = defaultdict(list)
    for source_edge, destination_edge in endpoints:
        endpoint_pool[(int(labels.get(source_edge[0], -1)),
                       int(labels.get(destination_edge[1], -1)))].append(
                           (int(source_edge[0]), int(destination_edge[1])))
    exact = Counter(family(route, labels) for route in real)
    family_rng, count_rng, output_rng = [
        np.random.default_rng(child) for child in np.random.SeedSequence(seed + 700000).spawn(3)]
    epsilon_family = budget["stable_family"]
    threshold = 1.0 + np.log(1.0 / (2.0 * DELTA_FAMILY)) / epsilon_family
    if oracle == "thresholded":
        released = {key: float(value) for key, value in exact.items() if value >= threshold}
        noisy_total = float(len(real))
    elif oracle == "full":
        released = {key: float(value) for key, value in exact.items()}
        noisy_total = float(len(real))
    else:
        released, threshold = stable_release(
            exact, epsilon_family, DELTA_FAMILY, family_rng)
        noisy_total = max(float(len(real) + count_rng.laplace(
            0.0, 1.0 / budget["noisy_total"])), 1.0)
    requested = fixed_allocation(released, slots / noisy_total, slots)

    realized = {}
    stats = []
    for value, count in sorted(requested.items(), key=lambda item: (-item[1], repr(item[0]))):
        pairs = endpoint_pool.get((value[0], value[-1]), ())
        variants, expansions = [], 0
        order_seed = int.from_bytes(hashlib.sha256(
            f"{seed}:{value!r}".encode("ascii")).digest()[:8], "little")
        if pairs:
            order = np.random.default_rng(order_seed).permutation(
                min(len(pairs), MAX_ENDPOINT_PAIRS_PER_FAMILY))
            for index in order:
                candidate, visited = constrained_path(
                    router, labels, *pairs[int(index)], value)
                expansions += visited
                if candidate and family(candidate, labels) == value:
                    variants.append(candidate)
                    if len(variants) == PUBLIC_VARIANTS_PER_FAMILY:
                        break
        if variants:
            realized[value] = variants
        stats.append({"family": list(value), "requested": count,
                      "endpoint_pairs": len(pairs), "variants": len(variants),
                      "expansions": expansions})

    head = []
    unsupported = 0
    for value, count in requested.items():
        variants = realized.get(value, ())
        if variants:
            head.extend(variants[index % len(variants)] for index in range(count))
        else:
            unsupported += count
    if len(head) > slots:
        head = head[:slots]
    tail_needed = slots - len(head)
    tail_indices = output_rng.choice(len(public_tail), size=tail_needed,
                                     replace=tail_needed > len(public_tail))
    output = head + [public_tail[int(index)] for index in tail_indices]
    output_rng.shuffle(output)
    return output, {
        "threshold": float(threshold), "released_families": len(released),
        "requested_head": int(sum(requested.values())), "realized_head": len(head),
        "unsupported_head": unsupported, "realized_families": len(realized),
        "noisy_total": noisy_total, "realization": stats,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--seed", type=int,
                      help="reproducible research run; seed is public, so artifact is not a formal release")
    mode.add_argument("--formal", action="store_true",
                      help="draw unrevealed entropy for a formal DP release")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results" / "runs")
    parser.add_argument("--public-slot-count", type=int,
                        default=DEFAULT_PUBLIC_SLOT_COUNT,
                        help=("public synthetic release size; defaults to the public Beijing "
                              "protocol value and is never inferred from private input size"))
    parser.add_argument("--oracle", choices=("thresholded", "full"))
    parser.add_argument("--length-aware", action="store_true",
                        help="add a DP global length query and length-conditioned endpoint sampling")
    parser.add_argument("--epsilon-total", type=float, default=TOTAL_EPSILON,
                        help="total epsilon for a research budget-sweep release; default is 1.4")
    args = parser.parse_args()
    if args.public_slot_count <= 0:
        parser.error("--public-slot-count must be a positive public integer")
    if args.formal and args.oracle:
        parser.error("a nonprivate oracle cannot be a formal release")
    if not math.isfinite(args.epsilon_total) or args.epsilon_total <= 0:
        parser.error("--epsilon-total must be positive")
    started = time.time()
    internal_seed = secrets.randbits(128) if args.formal else args.seed
    cache, real = load_private_inputs()
    router = EdgeStateRouter(NETWORK, cache["edge_nodes"],
                             {None: {}}, {None: {}}, 0.0, 0.0)
    budget = budget_components(args.length_aware, args.epsilon_total)
    endpoints, endpoint_transcript = measure_and_sample_endpoints(
        cache, real, internal_seed, length_aware=args.length_aware, router=router,
        slots=args.public_slot_count, budget=budget)
    router, public_tail, tail_states = public_shortest_routes(cache, endpoints, router)
    output, family_transcript = route_family_release(
        cache, real, endpoints, public_tail, router, internal_seed, args.oracle,
        slots=args.public_slot_count, budget=budget)
    if len(output) != args.public_slot_count:
        raise RuntimeError(f"fixed-slot violation: {len(output)} != {args.public_slot_count}")
    if not all(route and all(a[1] == b[0] for a, b in zip(route, route[1:])) for route in output):
        raise RuntimeError("invalid consumer-visible directed route")

    suffix = f"_{args.oracle}" if args.oracle else ""
    length_suffix = "_length" if args.length_aware else ""
    run_name = (f"formal_{secrets.token_hex(6)}" if args.formal else
                f"seed_{args.seed}{length_suffix}{suffix}")
    run_dir = args.out_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    routes_path = run_dir / "road_routes.pkl.gz"
    transcript_path = run_dir / "dp_transcript.pkl.gz"
    with gzip.open(routes_path, "wb", compresslevel=6) as handle:
        pickle.dump(output, handle, pickle.HIGHEST_PROTOCOL)
    with gzip.open(transcript_path, "wb", compresslevel=6) as handle:
        pickle.dump({"endpoint": endpoint_transcript, "family": family_transcript},
                    handle, pickle.HIGHEST_PROTOCOL)
    classification = ("NONPRIVATE_ATTRIBUTION_ORACLE_DO_NOT_RELEASE" if args.oracle else
                      "FORMAL_MINIMAL_STRONG_FAMILY_APPROX_DP_RELEASE" if args.formal else
                      "RESEARCH_ONLY_REPRODUCIBLE_NOISE_DO_NOT_RELEASE")
    # Consumer-visible manifest: whitelist only public protocol fields and
    # hashes.  Private input counts, runtime diagnostics, seeds, and internal
    # route-family diagnostics are written to a separate research file below.
    runtime_seconds = time.time() - started
    manifest = {
        "classification": classification,
        "algorithm": ("DFR: demand-family measurement + family-guided routing"
                      + (" + DP length-conditioned endpoint reconstruction" if args.length_aware else "")),
        "removed": ["legacy q5", "legacy route field", "residual deconvolution",
                    "length OT", "carrier reweighting"],
        "adjacency": "one road-realized trajectory record add/remove",
        "privacy": ({"epsilon": args.epsilon_total, "delta": 1e-6,
                     "composition": budget}
                    if not args.oracle else None),
        "public_slot_count": args.public_slot_count,
        "fixed_output_slots": args.public_slot_count,
        "outputs": {routes_path.name: digest(routes_path),
                    transcript_path.name: digest(transcript_path)},
        "paper_modified": False, "public_release_modified": False,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                        allow_nan=False) + "\n", encoding="utf8")
    if not args.formal:
        # Research-only diagnostics stay local and are never part of the
        # consumer-visible release manifest.
        research_metadata = {
            "classification": classification,
            "research_seed": args.seed,
            "oracle": args.oracle,
            "input_records": len(real),
            "public_slot_count": args.public_slot_count,
            "tail_states": dict(tail_states),
            "family_release": family_transcript,
            "runtime_seconds": runtime_seconds,
        }
        (run_dir / "research_metadata.json").write_text(
            json.dumps(research_metadata, ensure_ascii=False, indent=2,
                       allow_nan=False) + "\n", encoding="utf8")
    public_summary = {"manifest": str(manifest_path.resolve()),
                      "routes": str(routes_path.resolve()),
                      "sha256": digest(routes_path), "slots": len(output)}
    if not args.formal:
        public_summary.update(head=family_transcript["realized_head"], runtime_seconds=runtime_seconds)
    print(json.dumps(public_summary, indent=2))


if __name__ == "__main__":
    main()

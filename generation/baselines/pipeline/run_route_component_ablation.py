from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import (  # noqa: E402
    PUBLIC_ROOT,
    filter_osm_ways_by_bbox,
    load_osm_ways,
    load_trajectories,
    parse_bbox,
    save_trajectories_pkl,
    thin_osm_ways_public,
    write_json,
)


def log(message: str) -> None:
    print(f"[component-ablation] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run the full-release MTR route-decoder component ablation: public "
            "shortest path, public stochastic candidate sampling, DP-GSRT tilt, "
            "and non-private route-choice upper bound. PRA is read from an "
            "already generated OSM-wrapped release for table comparison."
        )
    )
    p.add_argument("--data", default="geolife")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--bbox", nargs=4, type=float)
    p.add_argument("--n-train", type=int)
    p.add_argument("--n-gen", type=int)
    p.add_argument("--public-slot-count", type=int)
    p.add_argument("--epsilon-base", type=float, default=1.0)
    p.add_argument("--epsilon-route", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-attempts-per-slot", type=int, default=40)
    p.add_argument("--max-candidates", type=int, default=32)
    p.add_argument("--osm-max-ways", type=int, default=0)
    p.add_argument("--tag-prefix", default=None)
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "component_ablation" / "synthetic"))
    p.add_argument("--paper-dir", default=str(PUBLIC_ROOT / "paper_latex"))
    p.add_argument("--metrics-csv")
    p.add_argument("--downstream-csv")
    p.add_argument("--route-sim-csv")
    p.add_argument("--pra-method", default=None, help="method stem for PRA row, e.g. geolife_dptrajpm_osm_full")
    return p


def add_method_paths() -> None:
    method_dir = PUBLIC_ROOT / "src" / "mtr" / "DP_GSRT"
    for path in [method_dir, PUBLIC_ROOT / "src" / "experiments", PUBLIC_ROOT / "src" / "mtr" / "shared_graph"]:
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)


def display_name(stem: str) -> str:
    mapping = {
        "public_shortest": "Public shortest path",
        "public_stochastic": "Public stochastic candidates",
        "dp_gsrt_tilted": "DP-GSRT tilted sampling",
        "nonprivate_upper": "Non-private route-choice upper",
        "pra": "PRA best OSM-wrapped baseline",
    }
    for key, val in mapping.items():
        if stem.endswith(key):
            return val
    return stem


def choose_candidate(
    variant: str,
    candidates: list[tuple[str, list[int]]],
    probs_dp: np.ndarray | None,
    probs_np: np.ndarray | None,
    rng: np.random.Generator,
) -> tuple[int, str]:
    if variant == "public_shortest":
        return 0, candidates[0][0]
    if variant == "public_stochastic":
        idx = int(rng.integers(0, len(candidates)))
        return idx, candidates[idx][0]
    if variant == "dp_gsrt_tilted":
        if probs_dp is None or probs_dp.size == 0:
            return 0, "fallback_shortest"
        idx = int(rng.choice(len(candidates), p=probs_dp))
        return idx, candidates[idx][0]
    if variant == "nonprivate_upper":
        if probs_np is None or probs_np.size == 0:
            return 0, "fallback_shortest"
        idx = int(rng.choice(len(candidates), p=probs_np))
        return idx, candidates[idx][0]
    raise ValueError(f"unknown variant: {variant}")


def synthesize_variants(args: argparse.Namespace) -> dict:
    if args.public_slot_count is None:
        raise RuntimeError("--public-slot-count is required when generating component-ablation releases")
    add_method_paths()
    import dp_gsrt_release as gsrt
    import reward_candidate_probe as probe
    import route_structure_potential_experiment as rse

    rng = np.random.default_rng(int(args.seed))
    bbox = parse_bbox(args.bbox)
    log(f"loading {args.data}")
    real = load_trajectories(args.data, limit=args.n_train)
    if not real:
        raise RuntimeError("no trajectories loaded")
    n_train = int(args.n_train or len(real))
    n_target = int(args.public_slot_count)
    log(f"loaded {len(real):,} trajectories; public slots={n_target:,}")

    osm_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_raw, bbox)
    if int(args.osm_max_ways) > 0 and len(osm_ways) > int(args.osm_max_ways):
        before = len(osm_ways)
        osm_ways = thin_osm_ways_public(osm_ways, bbox, int(args.osm_max_ways))
        log(f"public OSM thinning: kept {len(osm_ways):,}/{before:,} ways")
    else:
        log(f"loaded {len(osm_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")

    gsrt.SEED = int(args.seed)
    gsrt.EPS_BASE = float(args.epsilon_base)
    gsrt.EPS_ROUTE = float(args.epsilon_route)
    gsrt.PUBLIC_SLOT_COUNT = n_target
    gsrt.MAX_ATTEMPTS_PER_SLOT = int(args.max_attempts_per_slot)
    gsrt.MAX_CANDIDATES = int(args.max_candidates)
    gsrt.BBOX = bbox

    train = real[:n_train]
    norm_train, mn, span = rse.normalize_with_public_bbox(train, bbox)
    anchor_eps = gsrt.EPS_BASE * 0.20
    log("fitting DP anchors and base trip measurements")
    centers_norm = rse.dp_anchors(norm_train, anchor_eps, rng)
    centers_real = centers_norm * span + mn
    measurements = rse.fit_measurements(norm_train, centers_norm, rng, pgm=False, eps_total=gsrt.EPS_BASE, eps_anchor=anchor_eps)

    log("building public road graph")
    road_coords, graph = rse.prepare_graph(real, bbox=bbox, osm_ways=osm_ways, raw_graph=False)
    tree = cKDTree(road_coords)
    anchor_nodes = [int(tree.query(c)[1]) for c in centers_real]
    reverse_graph = probe.reverse_adjacency(graph)

    log("releasing DP graph-sketch moment")
    theta_dp, diag_dp = gsrt.release_graph_sketch_moment(
        train, mn, span, centers_norm, road_coords, graph, anchor_nodes, tree, reverse_graph, rng, public_denominator=n_target
    )
    log("computing non-private diagnostic graph-sketch moment")
    theta_np, diag_np = gsrt.release_graph_sketch_moment(
        train,
        mn,
        span,
        centers_norm,
        road_coords,
        graph,
        anchor_nodes,
        tree,
        reverse_graph,
        rng,
        public_denominator=n_target,
        private_mode="nonprivate_upper",
    )

    variants = ["public_shortest", "public_stochastic", "dp_gsrt_tilted", "nonprivate_upper"]
    syn = {v: [] for v in variants}
    stats = {
        v: {
            "attempted": 0,
            "fallback_slots": 0,
            "skipped_same_anchor": 0,
            "skipped_unroutable": 0,
            "selected_labels": {},
            "candidate_counts": [],
        }
        for v in variants
    }
    candidate_cache: dict[tuple[int, int], dict | None] = {}
    route_draw_buffer: list[tuple[int, int, int]] = []
    progress_every = max(1, min(1000, max(50, n_target // 10)))

    def next_trip_draw() -> tuple[int, int, int]:
        nonlocal route_draw_buffer
        if not route_draw_buffer:
            route_draw_buffer = gsrt.sample_trip_draws(measurements, centers_norm, rng, max(1024, n_target // 4))
        return route_draw_buffer.pop()

    def fallback_path(length: int) -> np.ndarray:
        for _ in range(gsrt.MAX_ATTEMPTS_PER_SLOT):
            o = int(rng.integers(0, len(anchor_nodes)))
            d = int(rng.integers(0, len(anchor_nodes)))
            if o == d:
                continue
            nodes = rse.shortest_path(graph, road_coords, anchor_nodes[o], anchor_nodes[d])
            if nodes is not None and len(nodes) >= 2:
                return rse.resample(road_coords[np.asarray(nodes, dtype=int)], max(2, length))
        node = int(rng.integers(0, len(road_coords)))
        return np.repeat(road_coords[[node]], max(2, length), axis=0)

    log("decoding shared fixed slots for all component variants")
    for slot in range(n_target):
        fallback_length = 16
        made = False
        for _ in range(gsrt.MAX_ATTEMPTS_PER_SLOT):
            o, d, lb = next_trip_draw()
            src, dst = int(anchor_nodes[o]), int(anchor_nodes[d])
            fallback_length = rse.sample_exact_len(measurements["len"], lb, rng)
            for v in variants:
                stats[v]["attempted"] += 1
            if src == dst:
                for v in variants:
                    stats[v]["skipped_same_anchor"] += 1
                continue
            key = (src, dst)
            if key not in candidate_cache:
                candidates = probe.generate_public_candidates(
                    graph,
                    road_coords,
                    src,
                    dst,
                    max_candidates=gsrt.MAX_CANDIDATES,
                    mode=gsrt.CANDIDATE_MODE,
                    tree=tree,
                    reverse_graph=reverse_graph,
                    anchor_nodes=anchor_nodes,
                    max_stretch=gsrt.CANDIDATE_MAX_STRETCH,
                    spur_trials=gsrt.CANDIDATE_SPUR_TRIALS,
                )
                if candidates:
                    probs_dp, _ = gsrt.candidate_probs(candidates, road_coords, mn, span, theta_dp, src, dst)
                    probs_np, _ = gsrt.candidate_probs(candidates, road_coords, mn, span, theta_np, src, dst)
                    candidate_cache[key] = {"candidates": candidates, "dp": probs_dp, "np": probs_np}
                else:
                    candidate_cache[key] = None
            item = candidate_cache[key]
            if item is None:
                for v in variants:
                    stats[v]["skipped_unroutable"] += 1
                continue
            candidates = item["candidates"]
            for v in variants:
                idx, label = choose_candidate(v, candidates, item["dp"], item["np"], rng)
                nodes = candidates[idx][1]
                stats[v]["candidate_counts"].append(len(candidates))
                labels = stats[v]["selected_labels"]
                labels[str(label)] = labels.get(str(label), 0) + 1
                syn[v].append(rse.resample(road_coords[np.asarray(nodes, dtype=int)], max(2, fallback_length)))
            made = True
            break
        if not made:
            path = fallback_path(fallback_length)
            for v in variants:
                syn[v].append(path.copy())
                stats[v]["fallback_slots"] += 1
                labels = stats[v]["selected_labels"]
                labels["public_fallback"] = labels.get("public_fallback", 0) + 1
        if (slot + 1) % progress_every == 0 or slot + 1 == n_target:
            log(f"decoded {slot + 1:,}/{n_target:,}; candidate_cache={len(candidate_cache):,}")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tag_prefix = args.tag_prefix or args.data
    outputs = {}
    for v in variants:
        tag = f"{tag_prefix}_{v}"
        path = save_trajectories_pkl(out_dir / f"{tag}.pkl", syn[v])
        outputs[v] = str(path.resolve())
        diag = {
            "command_role": "route_component_ablation",
            "variant": v,
            "display_name": display_name(v),
            "data": args.data,
            "n_train": n_train,
            "n_syn": len(syn[v]),
            "public_slot_count": n_target,
            "bbox": bbox,
            "osm_cache": args.osm_cache,
            "osm_max_ways": int(args.osm_max_ways),
            "epsilon_base": float(args.epsilon_base),
            "epsilon_route": float(args.epsilon_route) if v == "dp_gsrt_tilted" else 0.0,
            "privacy_class": "DP post-processing of base measurements" if v.startswith("public") else ("trajectory-level DP" if v == "dp_gsrt_tilted" else "non-private diagnostic upper bound"),
            "moment_dp": diag_dp if v == "dp_gsrt_tilted" else None,
            "moment_nonprivate": diag_np if v == "nonprivate_upper" else None,
            "stats": {
                k: (float(np.mean(val)) if k == "candidate_counts" and val else val)
                for k, val in stats[v].items()
            },
            "output": str(path.resolve()),
        }
        write_json(out_dir / f"{tag}_protocol.json", diag)

    manifest = {
        "command_role": "route_component_ablation",
        "data": args.data,
        "tag_prefix": tag_prefix,
        "outputs": outputs,
        "public_slot_count": n_target,
        "candidate_cache_size": len(candidate_cache),
        "privacy_note": (
            "public_shortest and public_stochastic consume no route-choice privacy beyond DP base measurements; "
            "dp_gsrt_tilted additionally consumes epsilon_route; nonprivate_upper is not DP and is diagnostic only."
        ),
    }
    write_json(out_dir / f"{tag_prefix}_component_ablation_manifest.json", manifest)
    return manifest


def read_csv(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_summary_tables(args: argparse.Namespace) -> None:
    metrics = {r["method"]: r for r in read_csv(args.metrics_csv)}
    downstream = {r["method"]: r for r in read_csv(args.downstream_csv)}
    route_sim = {r["method"]: r for r in read_csv(args.route_sim_csv)}
    if not metrics and not downstream:
        return
    rows = []
    stems = sorted(set(metrics) | set(downstream))
    if args.pra_method and args.pra_method not in stems:
        stems.append(args.pra_method)
    for stem in stems:
        if args.tag_prefix and not stem.startswith(args.tag_prefix) and stem != args.pra_method:
            continue
        m = metrics.get(stem, {})
        d = downstream.get(stem, {})
        variant = stem.replace(f"{args.tag_prefix}_", "") if args.tag_prefix and stem.startswith(args.tag_prefix) else "pra"
        rows.append(
            {
                "variant": variant,
                "display": display_name(variant),
                "j2": float(m.get("jump_gt2km", "nan")),
                "r200": float(m.get("road_200m", "nan")),
                "len": float(m.get("length_jsd", "nan")),
                "route_ready": float(d.get("accept_rate", "nan")),
                "route_sim": float(route_sim.get(stem, {}).get("mean_best_jaccard", "nan")),
                "usable": int(float(d.get("n_accepted", 0))) if d else 0,
                "n": int(float(m.get("n_traj", d.get("n_total", 0)))) if (m or d) else 0,
            }
        )
    order = ["public_shortest", "public_stochastic", "pra", "dp_gsrt_tilted", "nonprivate_upper"]
    rows.sort(key=lambda r: order.index(r["variant"]) if r["variant"] in order else 99)
    paper_dir = Path(args.paper_dir)
    paper_dir.mkdir(parents=True, exist_ok=True)
    tex_path = paper_dir / "tables_kdd_component_ablation.tex"
    lines = [
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Component & J2 & R200 & Len & Route-ready & RouteSim & Usable \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            f"{r['display']} & {r['j2']:.3f} & {r['r200']:.3f} & {r['len']:.3f} & "
            f"{r['route_ready']:.3f} & {r['route_sim']:.3f} & {r['usable']:,} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    tex_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(paper_dir / "tables_kdd_component_ablation.json", {"rows": rows, "metrics_csv": args.metrics_csv, "downstream_csv": args.downstream_csv})
    log(f"wrote {tex_path}")


def main() -> None:
    args = build_parser().parse_args()
    if args.metrics_csv or args.downstream_csv:
        write_summary_tables(args)
    else:
        synthesize_variants(args)


if __name__ == "__main__":
    main()

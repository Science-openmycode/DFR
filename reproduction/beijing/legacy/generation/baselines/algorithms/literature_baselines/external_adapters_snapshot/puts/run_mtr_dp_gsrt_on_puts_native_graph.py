"""Run a *separate*, graph-matched MTR / DP-GSRT diagnostic for PUTS.

PUTS represents Beijing as road segments, with two segments adjacent iff they
share an explicitly stored geometry point.  Its geometry file is therefore
not a normal OSM edge list.  This script rebuilds that exact public graph,
then executes a small, proof-shaped DP-GSRT adapter on it:

* a trajectory-level L1-clipped endpoint (anchor) histogram;
* a trajectory-level L1-clipped road-segment sketch; and
* public, randomized shortest-path candidate supports tilted by that noisy
  sketch before a fixed-size release is decoded.

This is intentionally a standalone *reduced-road diagnostic*, not a claim
that PUTS can run on full Beijing and not a replacement for the manuscript's
full-city MTR implementation.  It exists to make the PUTS comparison use the
same 3,000-road public graph and the same 1,000 private training records.
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np


def read_lines(path: Path, limit: int) -> list[np.ndarray]:
    lines: list[np.ndarray] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            if len(lines) >= limit:
                break
            points = []
            for token in raw.strip().removeprefix("LINESTRING (").removesuffix(")").split(","):
                try:
                    lon, lat = map(float, token.split()[:2])
                    points.append([lat, lon])
                except ValueError:
                    continue
            lines.append(np.asarray(points, dtype=float))
    if not lines or any(len(x) == 0 for x in lines):
        raise ValueError("PUTS geometry parsing produced empty road segments")
    return lines


def read_selected_lines(path: Path, road_ids: list[int]) -> list[np.ndarray]:
    """Select raw PUTS geometry rows in the order of PUTS's index map."""
    wanted = set(road_ids)
    selected: dict[int, np.ndarray] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_id, raw in enumerate(handle):
            if raw_id not in wanted:
                continue
            points = []
            for token in raw.strip().removeprefix("LINESTRING (").removesuffix(")").split(","):
                try:
                    lon, lat = map(float, token.split()[:2])
                    points.append([lat, lon])
                except ValueError:
                    continue
            selected[raw_id] = np.asarray(points, dtype=float)
    if set(selected) != wanted or any(len(selected[i]) == 0 for i in road_ids):
        raise ValueError("could not recover every requested PUTS raw road geometry")
    return [selected[i] for i in road_ids]


def native_puts_graph(lines: list[np.ndarray]) -> list[tuple[int, ...]]:
    """Mirror PUTS `buildAdjacentRoadDic`: shared stored point => adjacency."""
    owners: dict[tuple[float, float], list[int]] = defaultdict(list)
    for road_id, line in enumerate(lines):
        for lat, lon in line:
            owners[(round(float(lat), 7), round(float(lon), 7))].append(road_id)
    graph = [set() for _ in lines]
    for ids in owners.values():
        for road_id in ids:
            graph[road_id].update(other for other in ids if other != road_id)
    return [tuple(sorted(x)) for x in graph]


def components(graph: list[tuple[int, ...]]) -> np.ndarray:
    label = np.full(len(graph), -1, dtype=int)
    component = 0
    for seed in range(len(graph)):
        if label[seed] >= 0:
            continue
        label[seed] = component
        queue = [seed]
        for node in queue:
            for neighbour in graph[node]:
                if label[neighbour] < 0:
                    label[neighbour] = component
                    queue.append(neighbour)
        component += 1
    return label


def bfs_path(
    graph: list[tuple[int, ...]], src: int, dst: int, rng: np.random.Generator, *, perturb: bool
) -> list[int] | None:
    if src == dst:
        return [src]
    parent = {src: -1}
    queue = [src]
    for node in queue:
        neighbours = list(graph[node])
        if perturb and len(neighbours) > 1:
            rng.shuffle(neighbours)
        for neighbour in neighbours:
            if neighbour in parent:
                continue
            parent[neighbour] = node
            if neighbour == dst:
                path = [dst]
                while parent[path[-1]] >= 0:
                    path.append(parent[path[-1]])
                return path[::-1]
            queue.append(neighbour)
    return None


def public_candidate_paths(
    graph: list[tuple[int, ...]], src: int, dst: int, rng: np.random.Generator, count: int
) -> list[list[int]]:
    """Finite candidate support using only the public PUTS graph and RNG."""
    result: list[list[int]] = []
    signatures: set[tuple[int, ...]] = set()
    for attempt in range(max(1, count * 5)):
        path = bfs_path(graph, src, dst, rng, perturb=attempt > 0)
        if not path:
            continue
        signature = tuple(path)
        if signature not in signatures:
            signatures.add(signature)
            result.append(path)
        if len(result) >= count:
            break
    return result


def nearest_roads(points: np.ndarray, midpoints: np.ndarray, max_samples: int = 12) -> np.ndarray:
    if len(points) > max_samples:
        idx = np.linspace(0, len(points) - 1, max_samples, dtype=int)
        points = points[idx]
    distance2 = ((points[:, None, :] - midpoints[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(distance2, axis=1)


def path_feature(path: list[int], road_count: int) -> np.ndarray:
    feature = np.zeros(road_count, dtype=float)
    for road_id in path:
        feature[road_id] += 1.0
    norm = float(np.abs(feature).sum())
    return feature / norm if norm else feature


def polyline(path: list[int], lines: list[np.ndarray]) -> np.ndarray:
    points: list[list[float]] = []
    for road_id in path:
        line = lines[road_id]
        if points and np.allclose(points[-1], line[0]):
            points.extend(line[1:].tolist())
        else:
            points.extend(line.tolist())
    return np.asarray(points, dtype=float)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n-roads", type=int, default=3000)
    parser.add_argument("--road-ids", type=Path, default=None,
                        help="optional raw PUTS road ids; matches CpathDatabase's selected-road graph")
    parser.add_argument("--n-gen", type=int, default=1000)
    parser.add_argument("--epsilon", type=float, default=1.20)
    parser.add_argument("--epsilon-anchor", type=float, default=0.60)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--tilt-temperature", type=float, default=0.025)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.epsilon_anchor <= 0 or args.epsilon_anchor >= args.epsilon:
        raise ValueError("epsilon-anchor must be strictly between 0 and epsilon")
    eps_route = args.epsilon - args.epsilon_anchor
    rng = np.random.default_rng(args.seed)

    print("[1/5] Reading PUTS native geometry and rebuilding its segment graph...", flush=True)
    road_ids = None
    if args.road_ids is not None:
        road_ids = [int(x) for x in args.road_ids.read_text(encoding="utf-8").splitlines() if x.strip()]
        lines = read_selected_lines(args.geometry, road_ids)
    else:
        lines = read_lines(args.geometry, args.n_roads)
    graph = native_puts_graph(lines)
    component = components(graph)
    midpoints = np.asarray([line.mean(axis=0) for line in lines])
    print(f"      roads={len(lines):,}; components={component.max()+1:,}", flush=True)

    print("[2/5] Loading the private small training corpus...", flush=True)
    with args.real.open("rb") as handle:
        real = [np.asarray(x, dtype=float) for x in pickle.load(handle)]
    real = [x for x in real if len(x) >= 2]
    if not real:
        raise ValueError("no drawable real trajectories")

    print("[3/5] Releasing DP anchor histogram and DP graph-sketch moment...", flush=True)
    anchors = np.zeros(len(lines), dtype=float)
    sketch = np.zeros(len(lines), dtype=float)
    for trajectory in real:
        endpoint_ids = nearest_roads(trajectory[[0, -1]], midpoints, max_samples=2)
        # Endpoint vector has L1=1.  Per-trajectory road sketch also has L1=1.
        anchors[endpoint_ids[0]] += 0.5
        anchors[endpoint_ids[1]] += 0.5
        visited = nearest_roads(trajectory, midpoints)
        local = np.bincount(visited, minlength=len(lines)).astype(float)
        sketch += local / max(float(local.sum()), 1.0)
    noisy_anchor = np.maximum(anchors + rng.laplace(0.0, 1.0 / args.epsilon_anchor, len(lines)), 0.0)
    noisy_sketch = sketch + rng.laplace(0.0, 1.0 / eps_route, len(lines))
    noisy_anchor += 1e-12
    # Divide by the public fixed training-slot count, as in the full DP-GSRT release.
    theta = noisy_sketch / float(len(real))

    by_component: dict[int, np.ndarray] = {}
    for cid in np.unique(component):
        by_component[int(cid)] = np.flatnonzero(component == cid)

    print("[4/5] Decoding fixed public release slots with public candidates + DP tilt...", flush=True)
    generated: list[np.ndarray] = []
    attempted = 0
    candidate_counts: list[int] = []
    for slot in range(args.n_gen):
        source = int(rng.choice(len(lines), p=noisy_anchor / noisy_anchor.sum()))
        roads_in_component = by_component[int(component[source])]
        target_weights = noisy_anchor[roads_in_component]
        target = int(rng.choice(roads_in_component, p=target_weights / target_weights.sum()))
        candidates = public_candidate_paths(graph, source, target, rng, args.candidates)
        attempted += 1
        if not candidates:
            continue
        features = np.vstack([path_feature(path, len(lines)) for path in candidates])
        logits = (features @ theta) / max(args.tilt_temperature, 1e-12)
        logits = np.clip(logits - np.max(logits), -60.0, 60.0)
        probs = np.exp(logits)
        probs /= probs.sum()
        path = candidates[int(rng.choice(len(candidates), p=probs))]
        generated.append(polyline(path, lines))
        candidate_counts.append(len(candidates))
        if (slot + 1) % max(1, args.n_gen // 10) == 0:
            print(f"      decoded {slot+1:,}/{args.n_gen:,} slots; emitted={len(generated):,}", flush=True)
    if len(generated) != args.n_gen:
        raise RuntimeError(f"fixed-slot decoder emitted {len(generated)} rather than {args.n_gen}")

    print("[5/5] Writing synthetic release and audit ledger...", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as handle:
        pickle.dump(generated, handle, pickle.HIGHEST_PROTOCOL)
    ledger = {
        "method": "MTR-DP-GSRT native-PUTS-graph diagnostic",
        "purpose": "graph-matched reduced-road PUTS comparison only",
        "n_train": len(real),
        "n_gen_public_fixed": args.n_gen,
        "n_roads_public": len(lines),
        "raw_puts_road_ids": "CpathDatabase-selected subset" if road_ids is not None else "first n-roads geometry rows",
        "public_graph": "PUTS RoadGeometry shared-stored-point segment adjacency",
        "epsilon_total": args.epsilon,
        "epsilon_anchor": args.epsilon_anchor,
        "epsilon_route_sketch": eps_route,
        "composition": "sequential pure-DP composition at trajectory level",
        "anchor_l1_sensitivity": 1.0,
        "route_sketch_l1_sensitivity": 1.0,
        "candidate_support": "public graph + fixed hyperparameters + fresh randomness",
        "decoder": "post-processing of the two noisy releases",
        "mean_public_candidates": float(np.mean(candidate_counts)),
        "seed": args.seed,
    }
    args.out.with_suffix(".json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Done: {args.out} ({len(generated):,} trajectories).", flush=True)


if __name__ == "__main__":
    main()

"""Strict train-on-release/test-on-held-out-real task-utility evaluation.

The historical admission evaluator remains available for diagnostics.  This
file is intentionally separate: every model is fitted only on a release made
from the persisted training split and scored only against the persisted test
split.  It reports lightweight, public-road operational tasks rather than
claiming a production map-matcher or traffic-simulator benchmark.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import sys

import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
for path in [PUBLIC_RELEASE, PUBLIC_RELEASE / "pipeline", PUBLIC_RELEASE / "src" / "plotting", PUBLIC_RELEASE / "src" / "experiments", PUBLIC_RELEASE / "src" / "mtr" / "shared_graph"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from public_utils import PUBLIC_ROOT, filter_osm_ways_by_bbox, jsonable, load_osm_ways, load_trajectories, parse_bbox, write_json
from evaluate_kdd_revised_statistics import graph_context, ids, road_counts, sampled


def trajectory_cells(trajs: list[np.ndarray], bbox, grid: int = 32) -> list[np.ndarray]:
    return [ids(sampled(np.asarray(t, dtype=float), 128), bbox, grid) for t in trajs if len(t) >= 2]


def range_query_are(train: list[np.ndarray], test: list[np.ndarray], bbox, seed: int, n_queries: int = 100) -> float:
    """Average relative error of fixed public rectangular range queries."""
    rng = np.random.default_rng(seed)
    lat0, lat1, lon0, lon1 = bbox
    rects = []
    for _ in range(n_queries):
        a, b = sorted(rng.uniform(lat0, lat1, 2)); c, d = sorted(rng.uniform(lon0, lon1, 2))
        # Avoid degenerate rectangles while retaining a public, data-free workload.
        if b - a < .03 * (lat1 - lat0): b = min(lat1, a + .03 * (lat1 - lat0))
        if d - c < .03 * (lon1 - lon0): d = min(lon1, c + .03 * (lon1 - lon0))
        rects.append((a, b, c, d))
    def answers(trajs):
        result = []
        for a, b, c, d in rects:
            count = 0
            for t in trajs:
                p = sampled(np.asarray(t, dtype=float), 128)
                if np.any((a <= p[:, 0]) & (p[:, 0] <= b) & (c <= p[:, 1]) & (p[:, 1] <= d)):
                    count += 1
            result.append(count / max(len(trajs), 1))
        return np.asarray(result)
    a, b = answers(train), answers(test)
    return float(np.mean(np.abs(a - b) / np.maximum(b, 1.0 / max(len(test), 1))))


def mapped_node_sequences(trajs: list[np.ndarray], tree) -> list[list[int]]:
    out = []
    for t in trajs:
        seq = tree.query(sampled(np.asarray(t, dtype=float), 128), k=1)[1].astype(int).tolist()
        seq = [v for i, v in enumerate(seq) if i == 0 or v != seq[i - 1]]
        if len(seq) >= 2:
            out.append(seq)
    return out


def next_road_scores(train: list[np.ndarray], test: list[np.ndarray], tree) -> tuple[float, float]:
    """Train a first-order next-road predictor on a release; test on held-out GPS."""
    transitions: dict[int, Counter] = defaultdict(Counter)
    for seq in mapped_node_sequences(train, tree):
        for u, v in zip(seq[:-1], seq[1:]): transitions[u][v] += 1
    hit, rr, total = 0., 0., 0
    for seq in mapped_node_sequences(test, tree):
        for u, v in zip(seq[:-1], seq[1:]):
            ranked = [x for x, _ in transitions.get(u, Counter()).most_common(5)]
            total += 1
            if v in ranked:
                rank = ranked.index(v) + 1; hit += 1; rr += 1.0 / rank
    return (hit / total if total else 0.0, rr / total if total else 0.0)


def od_route_popularity(train: list[np.ndarray], test: list[np.ndarray], bbox) -> tuple[float, float]:
    """Public-grid origin-conditioned destination ranking, a route-demand task."""
    ranking: dict[int, Counter] = defaultdict(Counter)
    for t in train:
        a = np.asarray(t, dtype=float)
        if len(a) >= 2:
            o, d = ids(a[[0, -1]], bbox, 32)
            ranking[int(o)][int(d)] += 1
    hit, ndcg, total = 0., 0., 0
    for t in test:
        a = np.asarray(t, dtype=float)
        if len(a) < 2: continue
        o, d = ids(a[[0, -1]], bbox, 32)
        ranked = [x for x, _ in ranking[int(o)].most_common(10)]
        total += 1
        if int(d) in ranked:
            rank = ranked.index(int(d)) + 1; hit += 1; ndcg += 1.0 / np.log2(rank + 1)
    return (hit / total if total else 0.0, ndcg / total if total else 0.0)


def suffix_accuracy(train: list[np.ndarray], test: list[np.ndarray], tree) -> float:
    """Exact two-node suffix continuation accuracy; reported as a hard diagnostic."""
    model: dict[tuple[int, int], Counter] = defaultdict(Counter)
    for seq in mapped_node_sequences(train, tree):
        for a, b, c in zip(seq[:-2], seq[1:-1], seq[2:]): model[(a, b)][c] += 1
    correct = total = 0
    for seq in mapped_node_sequences(test, tree):
        for a, b, c in zip(seq[:-2], seq[1:-1], seq[2:]):
            pred = model[(a, b)].most_common(1)
            total += 1; correct += int(bool(pred) and pred[0][0] == c)
    return correct / total if total else 0.0


def evaluate(name: str, train: list[np.ndarray], test: list[np.ndarray], bbox, ctx, seed: int) -> dict:
    _, edges, tree, edge_index = ctx
    _counts, validity, compatible = road_counts(train, ctx[0], edges, tree, edge_index)
    hit5, mrr = next_road_scores(train, test, tree)
    pop_hit10, pop_ndcg = od_route_popularity(train, test, bbox)
    return {
        "method": name,
        "range_query_are": range_query_are(train, test, bbox, seed),
        "next_road_hit_at_5": hit5,
        "next_road_mrr": mrr,
        "route_popularity_hit_at_10": pop_hit10,
        "route_popularity_ndcg_at_10": pop_ndcg,
        "trajectory_suffix_accuracy": suffix_accuracy(train, test, tree),
        "train_directed_road_validity": validity,
        "train_route_compatible_yield": compatible,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run strict TSTR task utility on a persisted train/test split.")
    p.add_argument("--train-real", required=True)
    p.add_argument("--test-real", required=True)
    p.add_argument("--synthetic", action="append", default=[])
    p.add_argument("--names", nargs="*", default=None)
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--bbox", nargs=4, type=float, default=parse_bbox(None))
    p.add_argument("--seed", type=int, default=20260713)
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "kdd_revised" / "task_utility"))
    args = p.parse_args(); bbox = tuple(args.bbox)
    out = Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    train, test = load_trajectories(args.train_real, None), load_trajectories(args.test_real, None)
    print(f"[tstr] loaded {len(train):,} training and {len(test):,} held-out trajectories", flush=True)
    ctx = graph_context(filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox), bbox)
    rows = [evaluate("Real-train", train, test, bbox, ctx, args.seed)]
    names = args.names or [Path(x).stem for x in args.synthetic]
    if len(names) != len(args.synthetic): raise ValueError("--names must match --synthetic")
    for name, path in zip(names, args.synthetic):
        print(f"[tstr] fitting task models on {name}", flush=True)
        rows.append(evaluate(name, load_trajectories(path, None), test, bbox, ctx, args.seed))
    fields = list(rows[0])
    with (out / "task_utility.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows([{k: jsonable(v) for k, v in r.items()} for r in rows])
    write_json(out / "task_utility.json", {"protocol": "kdd_revised_strict_tstr_v1", "train_count": len(train), "test_count": len(test), "metrics": fields[1:], "rows": rows})
    print(f"[tstr] wrote {out}", flush=True)


if __name__ == "__main__":
    main()

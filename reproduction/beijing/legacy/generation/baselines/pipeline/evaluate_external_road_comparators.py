"""Evaluate full-release MTR and external road-generator diagnostics.

This is intentionally an appendix-only evaluator.  It does not claim a common
leaderboard: MTNet is a conditional generator whose unconditional release here
uses public uniform start-edge/time conditions, whereas MTR synthesizes a
complete release.  The script saves the exact full-population protocol and
keeps every measured metric, including metrics on which MTNet is stronger.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
ARA = ROOT.parent
for path in (ROOT, ROOT / 'src' / 'mtr' / 'shared_graph', ARA / 'scripts'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from public_utils import filter_osm_ways_by_bbox, load_osm_ways, load_trajectories
from route_structure_potential_experiment import prepare_graph


def js_from_counts(first: np.ndarray, second: np.ndarray) -> float:
    first = np.asarray(first, dtype=float).ravel()
    second = np.asarray(second, dtype=float).ravel()
    if first.sum() <= 0:
        first = np.ones_like(first)
    if second.sum() <= 0:
        second = np.ones_like(second)
    first /= first.sum(); second /= second.sum()
    mean = .5 * (first + second)
    return float(.5 * (np.sum(first[first > 0] * np.log2(first[first > 0] / mean[first > 0])) +
                        np.sum(second[second > 0] * np.log2(second[second > 0] / mean[second > 0]))))


def fast_edge_metric_suite(real: list[np.ndarray], synthetic: list[np.ndarray], context: list[np.ndarray],
                           road_coords: np.ndarray, graph: dict) -> dict[str, float]:
    """Vectorized equivalent of the paper edge evaluator for full populations."""
    edge_ids: dict[tuple[int, int], int] = {}
    edge_list: list[tuple[int, int]] = []
    for left, neighbors in graph.items():
        for right, _ in neighbors:
            key = (min(int(left), int(right)), max(int(left), int(right)))
            if key not in edge_ids:
                edge_ids[key] = len(edge_list); edge_list.append(key)
    midpoints = np.asarray([.5 * (road_coords[left] + road_coords[right]) for left, right in edge_list])
    tree = cKDTree(midpoints)
    n_edges = len(edge_list)

    def sequences(trajectories: list[np.ndarray]) -> list[np.ndarray]:
        result = []
        for trajectory in trajectories:
            arr = np.asarray(trajectory, dtype=float)
            if len(arr) < 2:
                continue
            mids = .5 * (arr[:-1] + arr[1:])
            result.append(np.asarray(tree.query(mids, workers=-1)[1], dtype=np.int32))
        return result

    real_seq = sequences(real); syn_seq = sequences(synthetic); context_seq = sequences(context)

    def flow(sequences_: list[np.ndarray]) -> np.ndarray:
        nonempty = [sequence for sequence in sequences_ if len(sequence)]
        return np.bincount(np.concatenate(nonempty), minlength=n_edges).astype(float) if nonempty else np.zeros(n_edges)

    real_flow, syn_flow = flow(real_seq), flow(syn_seq)
    real_active, syn_active = set(np.flatnonzero(real_flow)), set(np.flatnonzero(syn_flow))
    precision = len(real_active & syn_active) / len(syn_active) if syn_active else 0.0
    recall = len(real_active & syn_active) / len(real_active) if real_active else 0.0
    coverage_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    top_edges = np.argsort(flow(context_seq))[-512:]
    remap = np.full(n_edges, -1, dtype=np.int32); remap[top_edges] = np.arange(len(top_edges), dtype=np.int32)

    def transition_hist(sequences_: list[np.ndarray]) -> np.ndarray:
        hist = np.zeros((len(top_edges), len(top_edges)), dtype=float)
        for sequence in sequences_:
            compact = remap[sequence]; compact = compact[compact >= 0]
            if len(compact):
                compact = compact[np.r_[True, compact[1:] != compact[:-1]]]
            if len(compact) >= 2:
                np.add.at(hist, (compact[:-1], compact[1:]), 1.0)
        return hist

    stack = np.vstack(context); lower, upper = stack.min(axis=0), stack.max(axis=0)
    span = np.maximum(upper - lower, 1e-12)
    bins = np.asarray([0.0, .12, .25, .50, .80, np.inf])
    def corridor_hist(trajectories: list[np.ndarray], sequences_: list[np.ndarray]) -> np.ndarray:
        hist = np.zeros((5, len(top_edges)), dtype=float)
        for trajectory, sequence in zip(trajectories, sequences_):
            arr = np.asarray(trajectory, dtype=float)
            distance = float(np.linalg.norm((arr[-1] - arr[0]) / span))
            bucket = min(max(int(np.searchsorted(bins, distance, side='right') - 1), 0), 4)
            mapped = remap[sequence]; mapped = mapped[mapped >= 0]
            if len(mapped):
                hist[bucket] += np.bincount(mapped, minlength=len(top_edges))
        return hist

    return {
        'edge_flow_jsd': js_from_counts(real_flow, syn_flow),
        'edge_coverage_f1': float(coverage_f1),
        'edge_transition_jsd': js_from_counts(transition_hist(real_seq), transition_hist(syn_seq)),
        'od_corridor_jsd': js_from_counts(corridor_hist(real, real_seq), corridor_hist(synthetic, syn_seq)),
        'edge_unique_ratio': float(len(syn_active) / max(len(syn_seq), 1)),
    }


def log(message: str) -> None:
    print(f'[external-metrics] {time.strftime("%H:%M:%S")} {message}', flush=True)


def load_pickle(path: Path) -> list[np.ndarray]:
    import pickle
    with path.open('rb') as handle:
        payload = pickle.load(handle)
    if isinstance(payload, dict):
        raise ValueError(f'{path} is a dictionary payload, not a release list')
    return [np.asarray(t, dtype=float)[:, :2] for t in payload if len(t) >= 2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real', default='geolife')
    parser.add_argument('--mtr', type=Path,
        default=ROOT / 'outputs' / 'synthetic_releases' / 'current_best' / 'mtr_dp_gsrt.pkl')
    parser.add_argument('--mtnet', type=Path,
        default=ROOT / 'outputs' / 'synthetic_releases' / 'external_competitors' / 'mtnet_dpsgd_public_seed.pkl')
    parser.add_argument('--osm-cache', default='data/osm/osm_cache_beijing.pkl')
    parser.add_argument('--bbox', nargs=4, type=float, default=[39.75, 40.15, 116.10, 116.65])
    parser.add_argument('--out-dir', type=Path,
        default=ROOT / 'outputs' / 'external_competitors' / 'mtnet_vs_mtr' / 'edge_metrics_full')
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    log('loading full real corpus and two fixed synthetic releases')
    real = load_trajectories(args.real, limit=None)
    releases = {'MTR--DP-GSRT': load_pickle(args.mtr), 'MTNet--DP-SGD (public seeds)': load_pickle(args.mtnet)}
    log('loading public OSM graph')
    osm = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), tuple(args.bbox))
    road_coords, graph = prepare_graph(real, bbox=tuple(args.bbox), osm_ways=osm, raw_graph=False)
    log(f'protocol: real={len(real):,}; graph nodes={len(road_coords):,}; releases=' +
        ', '.join(f'{name}={len(value):,}' for name, value in releases.items()))

    rows = []
    for name, synthetic in releases.items():
        log(f'evaluating all edge metrics for {name}; this is full population, not a 300-route diagnostic')
        started = time.time()
        metrics = fast_edge_metric_suite(real, synthetic, real, road_coords, graph)
        row = {'method': name, 'n_real': len(real), 'n_synthetic': len(synthetic), **metrics}
        rows.append(row)
        log(f'completed {name} in {time.time() - started:.1f}s: ' +
            ' '.join(f'{key}={value:.6f}' for key, value in metrics.items()))
        with (args.out_dir / 'edge_metrics_partial.json').open('w', encoding='utf-8') as handle:
            json.dump({'rows': rows}, handle, indent=2)

    fields = list(rows[0])
    with (args.out_dir / 'edge_metrics_full.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    with (args.out_dir / 'edge_metrics_full.json').open('w', encoding='utf-8') as handle:
        json.dump({
            'protocol': 'Full 17,123-release appendix diagnostic; no subsampling.',
            'comparison_boundary': (
                'MTNet uses uniform public OSM start-edge and zero-time conditions; '
                'it is a conditional-generator transfer, not a shared-protocol leaderboard row.'),
            'bbox': args.bbox, 'rows': rows}, handle, indent=2)
    log(f'wrote {args.out_dir / "edge_metrics_full.csv"}')


if __name__ == '__main__':
    main()

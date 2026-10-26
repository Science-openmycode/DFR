"""Explicit audit-v2 corrections; never change the frozen road-choice core."""
from collections import Counter
import math

import numpy as np

PROTOCOL = 'metric-audit-v2-20261016'


def preserve_slots(obj):
    if isinstance(obj, dict):
        for key in ('trajs', 'trajectories', 'data', 'real', 'synthetic'):
            if key in obj:
                obj = obj[key]
                break
    result = []
    for index, row in enumerate(obj):
        a = np.asarray(row, dtype=float)
        if a.size == 0:
            a = np.empty((0, 2), dtype=float)
        if a.ndim != 2 or a.shape[1] < 2 or not np.isfinite(a[:, :2]).all():
            raise ValueError(f'Invalid coordinate slot {index}; never silently discard it')
        result.append(a[:, :2])
    return result


def reference_length_edges(real, length_function):
    values = np.asarray([length_function(t).sum() for t in real if len(t) >= 2])
    if not len(values) or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('Length reference must contain finite nonnegative paths')
    # Thirty-two finite bins determined only by the frozen real reference,
    # plus an overflow bin. nextafter retains ties at the 99th percentile.
    upper = np.nextafter(max(float(np.quantile(values, .99)), 1e-6), np.inf)
    return np.r_[np.linspace(0, upper, 33), np.inf]


def length_statistics(real, synthetic, stats):
    edges = reference_length_edges(real, stats.segment_lengths_km)
    left = stats.length_hist(real, edges)
    right = stats.length_hist(synthetic, edges)
    return dict(path_length_jsd=stats.jsd(left, right) if right.sum() else None,
                edges_km=[float(x) if np.isfinite(x) else 'inf' for x in edges],
                real_counted=int(left.sum()), synthetic_counted=int(right.sum()),
                real_overflow=int(left[-1]), synthetic_overflow=int(right[-1]))


def blind_candidate_order(query_grams, candidates, route_grams, cap=512):
    """Ranking is a function of the observed prefix and training corpus only."""
    if cap < 1:
        raise ValueError('Candidate cap must be positive')
    # Preserve the frozen candidate cap and primary ranking; replace only
    # the leaked relevance tie-break by the stable training record index.
    ids = sorted(candidates)[:cap]
    return sorted(ids, key=lambda i: (-len(query_grams & route_grams[i]), i))


def normalized_probability(counts, truth, public_options, alpha=1e-12):
    options = set(public_options)
    if not options or truth not in options or not set(counts).issubset(options):
        raise ValueError('Continuation outcome/count outside public outgoing support')
    return (counts[truth] + alpha) / (sum(counts.values()) + alpha * len(options))


def install_road_fixes(module):
    """Load corrected retrieval source in the original function namespace.

    Only the one confirmed faulty sorting key changes. The original source
    function is copied, not its file, and the exact expected key is required.
    The retained source and replacement are hashed by the runner manifest.
    """
    import inspect
    original = inspect.getsource(module.retrieval_metrics)
    old = 'scored.sort(key=lambda x: (-x[0], -x[1], x[2]))'
    new = 'scored.sort(key=lambda x: (-x[0], x[2]))'
    if original.count(old) != 1:
        raise RuntimeError('Unexpected retrieval implementation; review before applying correction')
    exec(compile(original.replace(old, new), str(module.__file__) + ':audit-v2', 'exec'), module.__dict__)
    original_continuation = module.continuation_metrics
    original_graph = module.graph_context
    outgoing = {}

    def graph_context(*args, **kwargs):
        context = original_graph(*args, **kwargs)
        for u, v in context[1]:
            outgoing.setdefault(u, set()).add(v)
        return context

    module.graph_context = graph_context

    def continuation(train_runs, test_runs):
        output = original_continuation(train_runs, test_runs)
        tri, uni = module.build_backoff_model(train_runs)
        # Add the same tiny smoothing mass to every PUBLIC outgoing option.
        # Neither the candidate support nor denominator depends on the answer.
        losses = []
        for seq in test_runs:
            for a, b, c in zip(seq[:-2], seq[1:-1], seq[2:]):
                counts = tri.get((a, b)) or uni.get(b)
                if counts:
                    probability = normalized_probability(counts, c, outgoing.get(b, ()))
                    losses.append(-math.log(probability))
        output['continuation_nll'] = float(np.mean(losses)) if losses else None
        return output

    module.continuation_metrics = continuation


def dirvalid_fields(metrics, source):
    """Keep pair validity diagnostic separate from complete-object validity."""
    pair = metrics.get('coordinate_projection_directed_road_validity',
                       metrics.get('directed_road_validity'))
    metrics['CoordinatePairValidity'] = pair
    if source == 'coordinate_projection':
        metrics['directed_road_validity'] = None
        metrics['DirValidRoadObject'] = None
    else:
        metrics['DirValidRoadObject'] = metrics['directed_road_validity']
    return metrics

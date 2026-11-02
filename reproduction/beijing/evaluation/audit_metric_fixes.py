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

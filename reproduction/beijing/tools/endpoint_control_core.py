"""Postprocess an existing DFR endpoint transcript; never read private trajectories.

Random routes choose uniformly among outgoing edges that strictly decrease public
distance to the destination. This is NOT uniform sampling over all legal paths.
The strictly decreasing potential guarantees termination without a length cap.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import pickle
import sys
import time
import numpy as np


def load(p):
    with gzip.open(p, 'rb') as f:
        return pickle.load(f)


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, x):
    with gzip.open(p, 'wb') as f:
        pickle.dump(x, f, protocol=4)


def replay(m, cache, router, transcript, slots, seed):
    """Preserve the original post-noise ordering and independent fifth RNG stream."""
    t = transcript['endpoint']
    edges, attrs = m.build_public_endpoint_domain(cache)
    labels, coarse = cache['labels384'], cache['labels24']
    votes = defaultdict(Counter)
    for node, fine in labels.items():
        if node in coarse:
            votes[int(fine)][int(coarse[node])] += 1
    parent = {f: c.most_common(1)[0][0] for f, c in votes.items()}
    fine_by_parent = defaultdict(list)
    for fine in range(384):
        fine_by_parent[parent.get(fine, 0)].append(fine)
    selected = set(map(tuple, t['selected_cells']))
    atoms, by_cell = defaultdict(list), defaultdict(list)
    for role in range(2):
        for edge in edges:
            cell = int(labels[edge[0 if role == 0 else 1]])
            key = ((role, 'head_way', cell, attrs[edge][0]) if (role, cell) in selected
                   else (role, 'tail_cell', cell))
            atoms[key].append(edge)
            by_cell[role, cell].append(edge)
    prior = defaultdict(Counter)
    noisy_atoms = {tuple(k): v for k, v in t['noisy_atoms']}
    if list(noisy_atoms) != list(atoms):
        raise ValueError('Public endpoint atom domain/order differs')
    for key, value in noisy_atoms.items():
        for edge in atoms[key]:
            role = int(key[0])
            cell = int(labels[edge[0 if role == 0 else 1]])
            prior[role, cell][edge] += value / len(atoms[key])
    noisy_cells, noisy_od = np.asarray(t['noisy_cells']), np.asarray(t['noisy_od'])
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(5)[4])
    pairs = [(o, d) for o in range(24) for d in range(24)]
    probs = m.probability([noisy_od[pair] for pair in pairs])
    fallback = Counter()
    def draw(o, d):
        cells = [fine_by_parent.get(c, list(range(384))) for c in (o, d)]
        chosen = [cells[r][m.sample_index([noisy_cells[r,c] for c in cells[r]], rng)] for r in range(2)]
        result = []
        for role, cell in enumerate(chosen):
            edge = m.sample_counter(prior.get((role,cell), {}), rng)
            if edge is None:
                edge = by_cell[role,cell][0]
                fallback['source' if role == 0 else 'destination'] += 1
            result.append(tuple(edge))
        return tuple(result)
    result = []
    for _ in range(slots):
        o,d = pairs[int(rng.choice(len(pairs), p=probs))]
        if t['length_aware']:
            i = m.sample_index(t['noisy_length'], rng)
            left,right = m.LENGTH_BINS_KM[i:i+2]
            target = 130.0 if not np.isfinite(right) else (left+right)/2
            def score(pair):
                a,b = pair[0][0], pair[1][1]
                if a not in router.xy or b not in router.xy:
                    return math.inf
                x,y = router.xy[a], router.xy[b]
                estimate = max(math.hypot(x[0]-y[0],x[1]-y[1])/1000*t['public_detour_factor'],1e-3)
                return abs(math.log(estimate/max(target,1e-3)))
            candidates = [draw(o,d) for _ in range(t['length_candidates'])]
            result.append(min(candidates, key=score))
        else:
            result.append(draw(o,d))
    if dict(fallback) != t['fallback_counts']:
        raise ValueError('Endpoint replay fallback mismatch')
    return result


def random_route(router, dist, index, s, d, seed, slot):
    if s == d:
        return (s,)
    if not np.isfinite(dist[index[s[1]]]):
        return ()
    rng = np.random.default_rng(np.random.SeedSequence([seed, slot, 20261019]))
    route = [s]
    v, goal = s[1], d[0]
    while v != goal:
        choices = [e for e in router.outgoing.get(v, ()) if dist[index[e[1]]] < dist[index[v]]]
        if not choices:
            raise ValueError('No decreasing edge despite reachable goal')
        edge = choices[int(rng.integers(len(choices)))]
        route.append(edge)
        v = edge[1]
    return tuple(route) + (d,)

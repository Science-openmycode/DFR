from __future__ import annotations

import hashlib
import heapq
import math
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def family(route, labels):
    if not route:
        return ()
    values = [labels.get(route[0][0], -1)] + [labels.get(edge[1], -1) for edge in route]
    result = []
    for value in values:
        value = int(value)
        if not result or value != result[-1]:
            result.append(value)
    return tuple(result)


def road_class(value):
    value = str(value).lower()
    if value.startswith(("motorway", "trunk", "primary")):
        return "major"
    if value.startswith(("secondary", "tertiary")):
        return "collector"
    return "local"


def heading(geometry, bins=4):
    coords = list(geometry.coords)
    angle = (math.atan2(coords[-1][1] - coords[0][1],
                        coords[-1][0] - coords[0][0]) + 2 * math.pi) % (2 * math.pi)
    return int(angle * bins / (2 * math.pi)) % bins


def sample_counter(values, rng):
    items = list(values)
    weights = np.asarray([values[item] for item in items], dtype=float)
    weights = np.maximum(weights, 0.0)
    if not len(items) or weights.sum() <= 0:
        return None
    return items[int(rng.choice(len(items), p=weights / weights.sum()))]


def stable_release(counts, epsilon, delta, rng):
    threshold = 1.0 + np.log(1.0 / (2.0 * delta)) / epsilon
    released = {}
    for key, count in counts.items():
        noisy = float(count + rng.laplace(0.0, 1.0 / epsilon))
        if noisy > threshold:
            released[key] = noisy
    return released, float(threshold)


class EdgeStateRouter:
    def __init__(self, network: Path, canonical_edge_nodes: dict[int, tuple[int, int]],
                 real_edges: dict[tuple | None, Counter], real_turns: dict[tuple | None, Counter],
                 beta: float, edge_weight: float, cost_mode: str = "exponential",
                 length_weight: float = 0.05):
        frame = gpd.read_file(network)[["id", "source", "target", "length_m", "geometry"]]
        self.source, self.target, self.length, self.xy = {}, {}, {}, {}
        self.outgoing = defaultdict(list)
        for row in frame.itertuples(index=False):
            edge_id = int(row.id)
            if edge_id not in canonical_edge_nodes:
                continue
            source, target = map(int, canonical_edge_nodes[edge_id])
            edge = (source, target)
            length = max(float(row.length_m), 1e-3)
            if edge in self.length and self.length[edge] <= length:
                continue
            self.source[edge], self.target[edge] = source, target
            self.length[edge] = length
            coords = list(row.geometry.coords)
            self.xy.setdefault(source, tuple(map(float, coords[0][:2])))
            self.xy.setdefault(target, tuple(map(float, coords[-1][:2])))
        for edge, source in self.source.items():
            self.outgoing[source].append(edge)
        self.edge_score = self._scores(real_edges)
        self.turn_score = self._scores(real_turns)
        self.beta = float(beta)
        self.edge_weight = float(edge_weight)
        self.cost_mode = cost_mode
        self.length_weight = float(length_weight)
        self.median_length = max(float(np.median(list(self.length.values()))), 1e-3)
        self.min_multiplier = (math.exp(-self.beta) if self.cost_mode == "exponential"
                               else self.length_weight / self.median_length)
        self.cache = {}

    @staticmethod
    def _scores(grouped):
        result = {}
        for group, counts in grouped.items():
            scale = max(float(np.quantile(list(counts.values()), .99)), 1.0) if counts else 1.0
            result[group] = {atom: min(math.log1p(count) / math.log1p(scale), 1.0)
                             for atom, count in counts.items()}
        return result

    def transition_cost(self, left, right, group):
        edge_score = self.edge_score.get(group, self.edge_score.get(None, {}))
        turn_score = self.turn_score.get(group, self.turn_score.get(None, {}))
        score = (self.edge_weight * edge_score.get(right, 0.0)
                 + (1.0 - self.edge_weight) * turn_score.get((left[0], left[1], right[1]), 0.0))
        if self.cost_mode == "shifted-linear":
            return self.beta * (1.0 - score) + self.length_weight * self.length[right] / self.median_length
        return self.length[right] * math.exp(-self.beta * score)

    def heuristic(self, edge, destination):
        left = self.xy.get(self.target[edge]); right = self.xy.get(self.source[destination])
        if left is None or right is None:
            return 0.0
        return self.min_multiplier * math.hypot(left[0] - right[0], left[1] - right[1])

    def path(self, start, destination, group=None):
        key = (start, destination, group)
        if key in self.cache:
            return self.cache[key]
        if start not in self.target or destination not in self.source:
            self.cache[key] = None; return None
        if start == destination:
            self.cache[key] = (start,); return (start,)
        distance, parent = {start: 0.0}, {}
        queue, settled = [(self.heuristic(start, destination), 0.0, start)], set()
        while queue:
            _, cost, edge = heapq.heappop(queue)
            if edge in settled:
                continue
            settled.add(edge)
            if edge == destination:
                result = [edge]
                while result[-1] != start:
                    result.append(parent[result[-1]])
                answer = tuple(reversed(result)); self.cache[key] = answer; return answer
            for nxt in self.outgoing.get(self.target[edge], ()):
                proposal = cost + self.transition_cost(edge, nxt, group)
                if proposal < distance.get(nxt, math.inf):
                    distance[nxt], parent[nxt] = proposal, edge
                    heapq.heappush(queue, (proposal + self.heuristic(nxt, destination), proposal, nxt))
        self.cache[key] = None
        return None


def constrained_path(router, labels, source, destination, route_family, max_expansions=2_000_000):
    route_family = tuple(map(int, route_family)); source, destination = int(source), int(destination)
    if int(labels.get(source, -1)) != route_family[0]:
        return (), 0
    start = (source, 0); distance = {start: 0.0}; previous = {}; queue = [(0.0, start)]
    expansions, goal = 0, None
    while queue and expansions < max_expansions:
        cost, state = heapq.heappop(queue)
        if cost != distance.get(state):
            continue
        node, stage = state; expansions += 1
        if node == destination and stage == len(route_family) - 1:
            goal = state; break
        for edge in router.outgoing.get(node, ()):
            target = int(edge[1]); target_region = int(labels.get(target, -1)); next_stage = stage
            if target_region == route_family[stage]:
                pass
            elif stage + 1 < len(route_family) and target_region == route_family[stage + 1]:
                next_stage += 1
            else:
                continue
            candidate = (target, next_stage); proposal = cost + router.length.get(edge, math.inf)
            if proposal < distance.get(candidate, math.inf):
                distance[candidate] = proposal; previous[candidate] = (state, edge)
                heapq.heappush(queue, (proposal, candidate))
    if goal is None:
        return (), expansions
    edges, state = [], goal
    while state != start:
        state, edge = previous[state]; edges.append(edge)
    return tuple(reversed(edges)), expansions

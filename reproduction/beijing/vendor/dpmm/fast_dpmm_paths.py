"""Exact-target Dijkstra for the frozen nonnegative directed DPMM public graph.

Preserves NetworkX 3.2.1 full single-source Dijkstra's relaxation order,
heap insertion tie-breaks and floating-point additions. Only requested target
paths are materialized, after all reachable requested targets settle. This is
an optimization of the existing adapter, NOT a claim to reproduce A* ties.
The graph and weights must remain frozen after installation.
"""
from heapq import heappop, heappush
from itertools import count


def target_paths(graph, source, targets):
    pending = {t for t in targets if t in graph}
    if source not in graph or not pending:
        return {}
    wanted = pending.copy()
    dist, seen, parent = {}, {source: 0}, {}
    serial = count()
    fringe = [(0, next(serial), source)]
    while fringe:
        d, _, v = heappop(fringe)
        if v in dist:
            continue
        dist[v] = d
        pending.discard(v)
        if not pending:
            break
        for u, edge in graph._adj[v].items():
            cost = edge.get('length', 1)
            if cost is None:
                continue
            vu = d + cost
            if u in dist:
                if vu < dist[u]:
                    raise ValueError('Negative weights are not supported')
            elif u not in seen or vu < seen[u]:
                seen[u] = vu
                parent[u] = v
                heappush(fringe, (vu, next(serial), u))
    result = {}
    for target in wanted:
        if target not in dist:
            continue
        path = [target]
        while path[-1] != source:
            path.append(parent[path[-1]])
        path.reverse()
        result[target] = (path, float(dist[target]))
    return result


def install_semantic_path_cache(mm, max_entries=100_000):
    cache = {}

    def gen_path_list(source_nodes, target_nodes):
        targets = list(target_nodes)
        paths, distances = [], []
        for raw_source in source_nodes:
            source = int(raw_source)
            if source not in mm.graph:
                continue
            missing = {int(t) for t in targets if source != t and (source, int(t)) not in cache}
            computed = target_paths(mm.graph, source, missing) if missing else {}
            # Copy cached results for this call so cache eviction cannot change
            # output enumeration, including duplicate candidates.
            results = {int(t): cache.get((source, int(t)), computed.get(int(t))) for t in targets}
            for raw_target in targets:
                target = int(raw_target)
                if source == target:
                    continue
                key = (source, target)
                if key not in cache:
                    if len(cache) >= max_entries:
                        cache.clear()
                    cache[key] = results[target]
                result = cache[key]
                if result is not None:
                    path, length = result
                    paths.append(path)
                    distances.append(length)
        return paths, distances

    mm.gen_path_list = gen_path_list
    mm._official_adapter_path_cache = cache

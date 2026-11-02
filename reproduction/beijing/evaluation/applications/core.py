"""Road-application rules, detached from experiment-specific directories."""
import math
from bisect import insort
from collections import Counter, defaultdict


def erase_loops(seq, edges):
    if not seq:
        return []
    nodes = [edges[seq[0]]['u']]
    positions = {nodes[0]: 0}
    path = []
    for eid in seq:
        e = edges[eid]
        if e['u'] != nodes[-1]:
            raise ValueError('Not a directed walk')
        v = e['v']
        if v in positions:
            j = positions[v]
            for n in nodes[j+1:]:
                del positions[n]
            del nodes[j+1:]
            del path[j:]
        else:
            path.append(eid); nodes.append(v); positions[v] = len(nodes)-1
    return path


def better(a, b):
    if b is None:
        return a is not None
    if a is None:
        return False
    for x, y in zip(a, b):
        if x != y:
            return x > y
    return len(a) < len(b)


def solve(weights, destination, edges):
    """Unchanged sparse synchronous recurrence from the verified MFP solver."""
    incoming = defaultdict(list); vertices = {destination}
    for eid, count in weights.items():
        e = edges[eid]
        if count <= 0:
            raise ValueError('Non-positive footmark')
        incoming[e['v']].append((e['u'], eid, count)); vertices.update((e['u'], e['v']))
    for values in incoming.values():
        values.sort()
    labels = {destination: ((), (), (destination,))}; changed = {destination}
    for _ in range(1, len(vertices)):
        old = labels; new = dict(old); next_changed = set()
        for v in sorted(changed):
            freq, path, nodes = old[v]
            for u, eid, count in incoming[v]:
                if u in nodes:
                    continue
                f = list(freq); insort(f, count)
                candidate = (tuple(f), (eid,) + path, (u,) + nodes)
                previous = new.get(u)
                if (previous is None or better(candidate[0], previous[0])
                        or (candidate[0] == previous[0] and candidate[1] < previous[1])):
                    new[u] = candidate; next_changed.add(u)
        labels = new
        if not next_changed:
            break
        changed = next_changed
    return labels


def ordered(a, b, edges):
    if not a or not b:
        return 0.0
    pos = {e: i+1 for i, e in enumerate(a)}
    if len(pos) != len(a) or len(set(b)) != len(b):
        raise ValueError('Ordered comparison requires loop-erased paths')
    tree = [0.0] * (len(a)+1)
    for e in b:
        if e not in pos:
            continue
        j, best = pos[e]-1, 0.0
        while j:
            best = max(best, tree[j]); j -= j & -j
        value, j = best + edges[e]['length_m'], pos[e]
        while j < len(tree):
            tree[j] = max(tree[j], value); j += j & -j
    j, best = len(a), 0.0
    while j:
        best = max(best, tree[j]); j -= j & -j
    return 2*best/(sum(edges[e]['length_m'] for e in a)+sum(edges[e]['length_m'] for e in b))


def overlap(a, b):
    sa, sb = sum(a.values()), sum(b.values())
    if not sa:
        raise ValueError('No reference demand')
    return math.fsum(min(v/sa, b.get(k, 0)/sb) for k, v in a.items()) if sb else 0.0


def marginal_score(a, b):
    def marginals(c):
        origins, destinations = Counter(), Counter()
        for (o, d), n in c.items():
            origins[o] += n; destinations[d] += n
        return origins, destinations
    ao, ad = marginals(a); bo, bd = marginals(b)
    return .5*(overlap(ao, bo)+overlap(ad, bd))


def clip(a, b, box):
    dx, dy = b[0]-a[0], b[1]-a[1]; lo, hi = 0., 1.
    for p, q in [(-dx, a[0]-box[0]), (dx, box[2]-a[0]), (-dy, a[1]-box[1]), (dy, box[3]-a[1])]:
        if p == 0:
            if q < 0:
                return None
        else:
            z = q/p
            if p < 0:
                lo = max(lo, z)
            else:
                hi = min(hi, z)
            if lo >= hi:
                return None
    x, y = (a[0]+lo*dx, a[1]+lo*dy), (a[0]+hi*dx, a[1]+hi*dy)
    return (x, y) if math.dist(x, y) > 1e-9 else None


def author_greedy(roads, bits, k, budget):
    """Exact integer-mask port of patched author connect_first, not a new heuristic.

    Ascending edge IDs; strictly greater gain; left before right; no cycles;
    remove selected edges; stop at zero marginal gain. Selection order retained.
    """
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for i, row in enumerate(roads):
        outgoing[row[1]].append(i); incoming[row[2]].append(i)
    active = set(range(len(roads))); routes = []; covered = 0
    for _ in range(k):
        best, gain = None, 0
        for i in sorted(active):
            if roads[i][-1] <= budget:
                g = (bits[i] & ~covered).bit_count()
                if g > gain:
                    best, gain = i, g
        if best is None:
            break
        route = [best]; length = roads[best][-1]; covered |= bits[best]
        while True:
            nodes = {n for i in route for n in roads[i][1:3]}
            chosen, gain, prepend = None, 0, False
            for left, candidates in [(True, incoming[roads[route[0]][1]]), (False, outgoing[roads[route[-1]][2]])]:
                for i in candidates:
                    if i not in active or length+roads[i][-1] > budget or roads[i][1 if left else 2] in nodes:
                        continue
                    g = (bits[i] & ~covered).bit_count()
                    if g > gain:
                        chosen, gain, prepend = i, g, left
            if chosen is None:
                break
            route = [chosen]+route if prepend else route+[chosen]
            length += roads[chosen][-1]; covered |= bits[chosen]
        active.difference_update(route); routes.append(route)
    return routes

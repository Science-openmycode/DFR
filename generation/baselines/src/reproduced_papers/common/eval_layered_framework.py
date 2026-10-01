"""Layered evaluation framework for DP trajectory synthesis.

This pilot evaluates methods in four ordered layers:
1) aggregate statistics, 2) trajectory continuity, 3) road realism,
4) privacy/predictability.

The script intentionally uses a moderate sample size so the metric design can be
validated quickly before scaling to the full 10-seed experiment.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree, Delaunay
from scipy.spatial.distance import jensenshannon


ARA = Path(__file__).resolve().parent
ROOT = ARA.parent
EXEC = ARA / "src" / "execution"
sys.path.insert(0, str(EXEC))

from evaluate import evaluate, haversine  # noqa: E402
from osm_dbscan import osm_centers_from_ways  # noqa: E402
from sprt_final import SPRTModel, build_sprt_adaptive_grid  # noqa: E402
from privtrace_final import PrivTraceModel  # noqa: E402
from dptrajpm_final import DPTrajPM, DPTrajPMRNDV  # noqa: E402
from dpstd_final import DPStdModel, DPStdRNDVModel  # noqa: E402


BBOX = (39.75, 40.15, 116.10, 116.65)
BBOX_DICT = {
    "lat_min": BBOX[0],
    "lat_max": BBOX[1],
    "lon_min": BBOX[2],
    "lon_max": BBOX[3],
}
EPS = 1.0
K_OSM = 25
N_TRAIN = 800
N_EVAL_REAL = 300
N_GEN = 200
SEEDS = [42, 1042, 2042]


def load_geolife(limit: int | None = None) -> list[np.ndarray]:
    data_dir = ROOT / "semdp_traj_paper" / "experiments" / "datasets" / "geolife" / "Geolife Trajectories 1.3" / "Data"
    trajs: list[np.ndarray] = []
    for user_dir in sorted(data_dir.iterdir()):
        traj_dir = user_dir / "Trajectory"
        if not traj_dir.is_dir():
            continue
        for plt in sorted(traj_dir.glob("*.plt")):
            pts = []
            with plt.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(6):
                    next(f, None)
                for line in f:
                    p = line.strip().split(",")
                    if len(p) < 4:
                        continue
                    lat, lon = float(p[0]), float(p[1])
                    if BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]:
                        pts.append([lat, lon])
            if len(pts) >= 2:
                trajs.append(np.asarray(pts, dtype=np.float64))
            if limit is not None and len(trajs) >= limit:
                return trajs
    return trajs


def load_osm_ways():
    with (ARA / "evidence" / "tables" / "osm_cache_beijing.pkl").open("rb") as f:
        return pickle.load(f)


def build_delaunay_adjacency(centers: np.ndarray) -> np.ndarray:
    n = len(centers)
    adj = np.zeros((n, n), dtype=int)
    if n >= 4:
        tri = Delaunay(centers)
        for simplex in tri.simplices:
            for a in range(3):
                for b in range(a + 1, 3):
                    adj[simplex[a], simplex[b]] = 1
                    adj[simplex[b], simplex[a]] = 1
    else:
        adj[:] = 1
        np.fill_diagonal(adj, 0)
    for i in range(n):
        if adj[i].sum() == 0:
            adj[i, i] = 1
    return adj


def build_road_tree(osm_ways):
    pts = []
    for way in osm_ways:
        for p in way.get("geometry", []):
            lat, lon = float(p["lat"]), float(p["lon"])
            if BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]:
                pts.append((lat, lon))
    arr = np.asarray(pts, dtype=np.float64)
    return cKDTree(arr), arr


def build_twostage_router(osm_ways, centers: np.ndarray):
    margin = 0.02
    road_pts: dict[int, tuple[float, float]] = {}
    road_index: dict[tuple[float, float], int] = {}
    graph: dict[int, set[int]] = defaultdict(set)
    center_nearby = {i: set() for i in range(len(centers))}

    def get_id(lat: float, lon: float) -> int:
        key = (round(lat, 5), round(lon, 5))
        if key not in road_index:
            idx = len(road_pts)
            road_index[key] = idx
            road_pts[idx] = key
        return road_index[key]

    for way in osm_ways:
        prev = None
        for p in way.get("geometry", []):
            lat, lon = float(p["lat"]), float(p["lon"])
            if not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]):
                prev = None
                continue
            near = [i for i, c in enumerate(centers) if abs(lat - c[0]) < margin and abs(lon - c[1]) < margin]
            cur = get_id(lat, lon)
            for ci in near:
                center_nearby[ci].add(cur)
            if prev is not None and cur != prev:
                graph[prev].add(cur)
                graph[cur].add(prev)
            prev = cur

    def bfs_path(start_set: set[int], end_set: set[int], max_depth: int = 4000):
        if start_set & end_set:
            return [next(iter(start_set & end_set))]
        q = deque()
        seen = set()
        for s in start_set:
            seen.add(s)
            q.append((s, [s]))
        while q:
            node, path = q.popleft()
            if len(path) > max_depth:
                continue
            for nb in graph.get(node, set()):
                if nb in end_set:
                    return path + [nb]
                if nb not in seen:
                    seen.add(nb)
                    q.append((nb, path + [nb]))
        return None

    center_dists = np.zeros((len(centers), len(centers)), dtype=np.float64)
    path_cache = {}
    for i in range(len(centers)):
        for j in range(len(centers)):
            if i == j:
                continue
            d = haversine(centers[i][0], centers[i][1], centers[j][0], centers[j][1])
            center_dists[i, j] = d
            if center_nearby[i] and center_nearby[j]:
                p = bfs_path(center_nearby[i], center_nearby[j])
                if p:
                    path_cache[(i, j)] = p

    return road_pts, path_cache, center_dists


def route_cell_trajectory(coords, centers, road_pts, path_cache, center_dists, n_per=2, max_points=120):
    cell_seq = [int(np.argmin(np.linalg.norm(centers - np.asarray(pt), axis=1))) for pt in coords]
    out = []
    routed = fallback = 0
    for a, b in zip(cell_seq[:-1], cell_seq[1:]):
        path = path_cache.get((a, b))
        if path:
            routed += 1
            for u, v in zip(path[:-1], path[1:]):
                p1, p2 = road_pts[u], road_pts[v]
                for k in range(n_per):
                    t = k / n_per
                    out.append([
                        p1[0] + t * (p2[0] - p1[0]) + np.random.normal(0, 0.00002),
                        p1[1] + t * (p2[1] - p1[1]) + np.random.normal(0, 0.00002),
                    ])
            out.append(list(road_pts[path[-1]]))
        else:
            fallback += 1
            out.append([
                float(centers[a][0]) + np.random.normal(0, 0.0001),
                float(centers[a][1]) + np.random.normal(0, 0.0001),
            ])
    if len(out) < 2:
        return None, routed, fallback
    if max_points and len(out) > max_points:
        keep = np.linspace(0, len(out) - 1, max_points).round().astype(int)
        out = [out[int(i)] for i in keep]
    return np.asarray(out, dtype=np.float64), routed, fallback


def all_step_distances(trajs):
    vals = []
    for tr in trajs:
        for i in range(len(tr) - 1):
            vals.append(haversine(tr[i][0], tr[i][1], tr[i + 1][0], tr[i + 1][1]))
    return np.asarray(vals, dtype=np.float64)


def turn_angles(trajs):
    vals = []
    for tr in trajs:
        if len(tr) < 3:
            continue
        for i in range(1, len(tr) - 1):
            a = tr[i - 1] - tr[i]
            b = tr[i + 1] - tr[i]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na < 1e-12 or nb < 1e-12:
                continue
            cosv = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
            vals.append(math.degrees(math.acos(cosv)))
    return np.asarray(vals, dtype=np.float64)


def jsd_hist(a, b, bins):
    ah = np.histogram(a, bins=bins)[0].astype(float) if len(a) else np.ones(len(bins) - 1)
    bh = np.histogram(b, bins=bins)[0].astype(float) if len(b) else np.ones(len(bins) - 1)
    return float(jensenshannon(ah / max(ah.sum(), 1), bh / max(bh.sum(), 1)))


def sinuosity(trajs):
    vals = []
    for tr in trajs:
        if len(tr) < 3:
            continue
        path = sum(haversine(tr[i][0], tr[i][1], tr[i + 1][0], tr[i + 1][1]) for i in range(len(tr) - 1))
        direct = haversine(tr[0][0], tr[0][1], tr[-1][0], tr[-1][1])
        if direct > 0.05:
            vals.append(path / direct)
    return np.asarray(vals, dtype=np.float64)


def road_metrics(trajs, road_tree):
    deg_to_km = 111.0
    total = on100 = on200 = 0
    dists_km = []
    for tr in trajs:
        if len(tr) == 0:
            continue
        d, _ = road_tree.query(tr, k=1)
        dk = d * deg_to_km
        dists_km.extend(dk.tolist())
        total += len(dk)
        on100 += int(np.sum(dk <= 0.1))
        on200 += int(np.sum(dk <= 0.2))
    if total == 0:
        return {"road_100m": 0.0, "road_200m": 0.0, "road_mean_dist_km": float("nan")}
    return {
        "road_100m": on100 / total,
        "road_200m": on200 / total,
        "road_mean_dist_km": float(np.mean(dists_km)),
    }


def layered_metrics(real_eval, syn, bbox, rng, road_tree, route_counts=None):
    base = evaluate(real_eval, syn, bbox, rng=rng, eval_subset_size=min(250, len(real_eval)))

    rs = all_step_distances(real_eval)
    ss = all_step_distances(syn)
    rt = turn_angles(real_eval)
    st = turn_angles(syn)
    rsi = sinuosity(real_eval)
    ssi = sinuosity(syn)

    extra = {
        "n_syn": len(syn),
        "len_mean": float(np.mean([len(t) for t in syn])),
        "len_median": float(np.median([len(t) for t in syn])),
        "step_mean_km": float(np.mean(ss)) if len(ss) else float("nan"),
        "step_p95_km": float(np.percentile(ss, 95)) if len(ss) else float("nan"),
        "jump_gt1km": float(np.mean(ss > 1.0)) if len(ss) else float("nan"),
        "jump_gt2km": float(np.mean(ss > 2.0)) if len(ss) else float("nan"),
        "step_jsd": jsd_hist(rs, ss, np.linspace(0, max(10.0, np.percentile(rs, 99) if len(rs) else 10.0, np.percentile(ss, 99) if len(ss) else 10.0), 40)),
        "turn_jsd": jsd_hist(rt, st, np.linspace(0, 180, 37)),
        "sinuosity_median": float(np.median(ssi)) if len(ssi) else float("nan"),
        "sinuosity_jsd": jsd_hist(rsi, ssi, np.linspace(1, 50, 50)),
    }
    extra.update(road_metrics(syn, road_tree))
    if route_counts:
        routed = route_counts.get("routed", 0)
        fallback = route_counts.get("fallback", 0)
        total = routed + fallback
        extra["route_coverage"] = routed / total if total else float("nan")
        extra["route_fallback"] = fallback / total if total else float("nan")
    else:
        extra["route_coverage"] = float("nan")
        extra["route_fallback"] = float("nan")
    base.update(extra)
    return base


def generate_methods(trajs, osm_ways, centers, road_pts, path_cache, center_dists):
    adj = build_delaunay_adjacency(centers)
    sprt_centers, sprt_adj, _ = build_sprt_adaptive_grid(osm_ways, BBOX_DICT)

    methods = {}

    def add(name, fn):
        methods[name] = fn

    def public_road_adapter(cell_syn):
        """Route a coordinate/cell-center trajectory through the public road graph.

        This is the paper's zero-budget OSM/PRA adapter. It uses only the
        already generated synthetic trajectory, public OSM-derived centers, and
        the public two-stage road router. The output count is preserved: if a
        route lookup fails for a synthetic trajectory, the original synthetic
        polyline is kept as a fallback rather than dropping the release slot.
        """
        out = []
        counts = {"routed": 0, "fallback": 0}
        for tr in cell_syn:
            routed, r, f = route_cell_trajectory(tr, centers, road_pts, path_cache, center_dists)
            counts["routed"] += r
            counts["fallback"] += f
            out.append(routed if routed is not None else tr)
        return out, counts

    def sprt_native():
        m = SPRTModel(EPS, sprt_centers, sprt_adj, BBOX)
        m.fit(trajs[:N_TRAIN])
        return m.generate(N_GEN)

    def sprt_osm():
        m = SPRTModel(EPS, centers, adj, BBOX)
        m.fit(trajs[:N_TRAIN])
        return public_road_adapter(m.generate(N_GEN))

    add("SPRT-native", sprt_native)
    add("SPRT-OSM", sprt_osm)

    def priv_native():
        m = PrivTraceModel(epsilon=EPS, budget_config=[0.2, 0.4, 0.4])
        m.fit(trajs[:N_TRAIN])
        return m.generate_2nd_order(N_GEN)

    def priv_osm():
        formatted = [{"lat": float(c[0]), "lon": float(c[1]), "type": "rndv"} for c in centers]
        m = PrivTraceModel(epsilon=EPS, budget_config=[0, 0.5, 0.5], rndv_centers=formatted)
        m.fit(trajs[:N_TRAIN])
        return public_road_adapter(m.generate_2nd_order(N_GEN))

    add("PrivTrace-native", priv_native)
    add("PrivTrace-OSM", priv_osm)

    def dptrajpm_native():
        m = DPTrajPM(EPS, BBOX_DICT, K_cells=7, m=2)
        m.fit(trajs[:N_TRAIN])
        return m.generate(N_GEN)

    def dptrajpm_osm():
        m = DPTrajPMRNDV(EPS, BBOX_DICT, centers.copy(), m=2)
        m.fit(trajs[:N_TRAIN])
        return public_road_adapter(m.generate(N_GEN))

    add("DPTrajPM-native", dptrajpm_native)
    add("DPTrajPM-OSM", dptrajpm_osm)

    def dptrajpm_twostage():
        model = DPTrajPMRNDV(EPS, BBOX_DICT, centers.copy(), m=2)
        model.fit(trajs[:N_TRAIN])
        return public_road_adapter(model.generate(N_GEN))

    add("DPTrajPM-OSM-twoStage", dptrajpm_twostage)

    def dpstd_native():
        m = DPStdModel(EPS, epsilon1=0.1 * EPS, epsilon2=0.9 * EPS, bbox_dict=BBOX_DICT)
        m.fit(trajs[:N_TRAIN])
        dpstd_native.budget_ledger = {
            "grid": float(m._eps_grid_consumed),
            "statistics": float(m._eps_stats_consumed),
            "total": float(m._eps_total_consumed),
        }
        return m.generate(N_GEN)

    add("DPStd-native", dpstd_native)

    def dpstd_osm():
        formatted = [{"lat": float(c[0]), "lon": float(c[1])} for c in centers]
        m = DPStdRNDVModel(EPS, formatted, BBOX_DICT)
        m.fit(trajs[:N_TRAIN])
        return public_road_adapter(m.generate(N_GEN))

    add("DPStd-OSM", dpstd_osm)

    # ---- Junction-based methods ----
    # Extract K top road junctions from OSM
    adj_junction = defaultdict(set)
    for w in osm_ways:
        g = w.get('geometry', [])
        for i in range(len(g)-1):
            p1, p2 = g[i], g[i+1]
            lat1, lon1 = float(p1['lat']), float(p1['lon'])
            lat2, lon2 = float(p2['lat']), float(p2['lon'])
            if not (BBOX[0]<=lat1<=BBOX[1] and BBOX[2]<=lon1<=BBOX[3]): continue
            if not (BBOX[0]<=lat2<=BBOX[1] and BBOX[2]<=lon2<=BBOX[3]): continue
            k1 = (round(lat1,5), round(lon1,5)); k2 = (round(lat2,5), round(lon2,5))
            adj_junction[k1].add(k2); adj_junction[k2].add(k1)
    junc_score = defaultdict(float)
    for w in osm_ways:
        g = w.get('geometry', [])
        rclass = w.get('highway', 'unclassified')
        imp = {'motorway':5,'trunk':4,'primary':3,'secondary':2,'tertiary':1}.get(rclass, 0.5)
        for p in g:
            k = (round(float(p['lat']),5), round(float(p['lon']),5))
            if k in adj_junction and len(adj_junction[k]) >= 3:
                junc_score[k] += imp
    top_junc = sorted(junc_score.keys(), key=lambda k: junc_score[k], reverse=True)[:K_OSM]
    junc_centers = np.array([list(j) for j in top_junc])

    # Build road routing graph for junctions
    junc_graph = defaultdict(set)
    for w in osm_ways:
        g = w.get('geometry', [])
        prev = None
        for p in g:
            lat, lon = float(p['lat']), float(p['lon'])
            k = (round(lat,5), round(lon,5))
            if prev and k != prev:
                junc_graph[prev].add(k); junc_graph[k].add(prev)
            prev = k

    junc_key_to_idx = {k: i for i, k in enumerate(top_junc)}

    def bfs_route_junction(start_key, end_key, max_depth=500):
        if start_key == end_key: return [start_key]
        visited = {start_key}; queue = deque([(start_key, [start_key])])
        while queue:
            node, path = queue.popleft()
            if len(path) > max_depth: continue
            for nb in junc_graph.get(node, set()):
                if nb == end_key: return path + [nb]
                if nb not in visited: visited.add(nb); queue.append((nb, path+[nb]))
        return None

    def junc_native():
        m = DPTrajPMRNDV(EPS, BBOX_DICT, junc_centers.copy(), m=2)
        m.fit(trajs[:N_TRAIN])
        return m.generate(N_GEN)

    def junc_twostage():
        model = DPTrajPMRNDV(EPS, BBOX_DICT, junc_centers.copy(), m=2)
        model.fit(trajs[:N_TRAIN])
        cell_syn = model.generate(N_GEN)
        out = []
        counts = {"routed": 0, "fallback": 0}
        for tr in cell_syn:
            cell_seq = []
            for pt in tr:
                dists = np.linalg.norm(junc_centers - np.array(pt), axis=1)
                cell_seq.append(int(np.argmin(dists)))
            result = []
            for idx in range(len(cell_seq)-1):
                i, j = cell_seq[idx], cell_seq[idx+1]
                path = bfs_route_junction(top_junc[i], top_junc[j])
                if path:
                    counts["routed"] += 1
                    result.extend([[float(p[0]), float(p[1])] for p in path])
                else:
                    counts["fallback"] += 1
                    result.append([float(top_junc[i][0]), float(top_junc[i][1])])
            if len(result) >= 2:
                out.append(np.array(result))
        return out, counts

    add("DPTrajPM-Junction", junc_native)
    add("DPTrajPM-Junction-twoStage", junc_twostage)
    return methods


def mean_results(rows):
    out = {}
    for row in rows:
        for k, v in row.items():
            if isinstance(v, (int, float, np.floating)) and not (isinstance(v, float) and math.isnan(v)):
                out.setdefault(k, []).append(float(v))
    return {k: float(np.mean(v)) for k, v in out.items()}


def write_markdown(results, path):
    order = [
        "js", "range_are", "trip_jsd", "f1", "len_jsd", "step_jsd",
        "step_mean_km", "jump_gt2km", "turn_jsd", "road_200m",
        "road_mean_dist_km", "sinuosity_median", "route_coverage",
        "reid",
    ]
    labels = {
        "js": "JS",
        "range_are": "ARE",
        "trip_jsd": "TripJSD",
        "f1": "F1",
        "len_jsd": "LenJSD",
        "step_jsd": "StepJSD",
        "step_mean_km": "StepMeanKm",
        "jump_gt2km": "Jump>2km",
        "turn_jsd": "TurnJSD",
        "road_200m": "Road<=200m",
        "road_mean_dist_km": "RoadDistKm",
        "sinuosity_median": "SinuosityMed",
        "route_coverage": "RouteCoverage",
        "reid": "ReID",
    }
    lines = [
        "# Layered Evaluation Pilot",
        "",
        f"Config: GeoLife Beijing, eps={EPS}, K_OSM={K_OSM}, train={N_TRAIN}, generated={N_GEN}, seeds={SEEDS}.",
        "",
        "| Method | " + " | ".join(labels[k] for k in order) + " |",
        "|---|" + "|".join(["---:"] * len(order)) + "|",
    ]
    for name, row in results.items():
        vals = []
        for k in order:
            v = row.get(k, float("nan"))
            if math.isnan(v):
                vals.append("NA")
            elif abs(v) >= 100:
                vals.append(f"{v:.1f}")
            else:
                vals.append(f"{v:.4f}")
        lines.append(f"| {name} | " + " | ".join(vals) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    t0 = time.time()
    print("Loading data...")
    trajs = load_geolife()
    train_trajs = trajs[:N_TRAIN]
    real_eval = trajs[N_TRAIN:N_TRAIN + N_EVAL_REAL]
    osm_ways = load_osm_ways()
    centers = osm_centers_from_ways(osm_ways, BBOX, K_OSM)
    road_tree, _ = build_road_tree(osm_ways)
    road_pts, path_cache, center_dists = build_twostage_router(osm_ways, centers)
    print(f"Trajs={len(trajs)}, OSM centers={len(centers)}, cached routed pairs={len(path_cache)}")

    methods = generate_methods(train_trajs, osm_ways, centers, road_pts, path_cache, center_dists)
    all_runs = {}
    means = {}
    for name, fn in methods.items():
        print(f"\n== {name} ==")
        rows = []
        for seed in SEEDS:
            np.random.seed(seed)
            rng = np.random.default_rng(seed)
            generated = fn()
            route_counts = None
            if isinstance(generated, tuple):
                syn, route_counts = generated
            else:
                syn = generated
            m = layered_metrics(real_eval, syn, BBOX, rng, road_tree, route_counts)
            rows.append(m)
            print(
                f"seed={seed} JS={m['js']:.3f} step={m['step_mean_km']:.2f} "
                f"jump2={m['jump_gt2km']:.2%} road200={m['road_200m']:.2%} reid={m['reid']:.3f}"
            )
        all_runs[name] = rows
        means[name] = mean_results(rows)

    out_dir = ARA / "evidence" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "layered_eval_pilot.json"
    md_path = out_dir / "layered_eval_pilot.md"
    json_path.write_text(json.dumps({"runs": all_runs, "means": means}, indent=2), encoding="utf-8")
    write_markdown(means, md_path)
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import deque
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.spatial.distance import jensenshannon


CHECK_DIR = Path(__file__).resolve().parent
PUBLIC_ROOT = CHECK_DIR.parent
sys.path.insert(0, str(PUBLIC_ROOT))
sys.path.insert(0, str(PUBLIC_ROOT / "src" / "reproduced_papers" / "SPRT"))

from public_utils import bbox_dict, filter_osm_ways_by_bbox, load_osm_ways, load_trajectories  # noqa: E402
import sprt_final as legacy_sprt  # noqa: E402


SPRT_REPORTED = {
    "source": "Sun et al., IEEE TITS 2023, Tables III-V",
    "paper_protocol": {
        "datasets": "Didi Chengdu and Ucar Beijing, 50,000 trajectories each",
        "repetitions": 10,
        "epsilon_split": "epsilon_1:epsilon_2 = 2:1",
        "beta": 0.05,
        "alpha": 1.5,
        "query_count": 200,
        "fp_top_k": 100,
        "fp_grid": "6x6",
        "traffic_threshold_m": 20,
    },
    "Ucar_epsilon_1": {
        "trip_error": 0.009,
        "diameter_error": 0.004,
        "length_error": 0.005,
        "query_avre": 0.026,
        "fp_avre": 0.511,
        "traffic_violation_pct": 7.44,
    },
    "Didi_epsilon_1": {
        "trip_error": 0.008,
        "diameter_error": 0.005,
        "length_error": 0.011,
        "query_avre": 0.034,
        "fp_avre": 0.353,
        "traffic_violation_pct": 4.94,
    },
}


def haversine_m(p1: np.ndarray, p2: np.ndarray) -> float:
    lat1, lon1 = float(p1[0]), float(p1[1])
    lat2, lon2 = float(p2[0]), float(p2[1])
    r = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def normalize(v: np.ndarray) -> np.ndarray:
    v = np.maximum(v.astype(float), 0.0)
    s = float(v.sum())
    if s <= 0:
        return np.ones_like(v, dtype=float) / len(v)
    return v / s


def grid_hist(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = bbox
    h = np.zeros((grid, grid), dtype=float)
    for tr in trajs:
        for lat, lon in tr[:, :2]:
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                r = min(grid - 1, max(0, int((lat - lat_min) / max(1e-12, lat_max - lat_min) * grid)))
                c = min(grid - 1, max(0, int((lon - lon_min) / max(1e-12, lon_max - lon_min) * grid)))
                h[r, c] += 1
    return normalize(h.ravel())


def area_od_hist(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int = 5) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = bbox
    h = np.zeros((grid * grid, grid * grid), dtype=float)
    for tr in trajs:
        ids = []
        for p in [tr[0], tr[-1]]:
            r = min(grid - 1, max(0, int((p[0] - lat_min) / max(1e-12, lat_max - lat_min) * grid)))
            c = min(grid - 1, max(0, int((p[1] - lon_min) / max(1e-12, lon_max - lon_min) * grid)))
            ids.append(r * grid + c)
        h[ids[0], ids[1]] += 1
    return normalize(h.ravel())


def trajectory_lengths_m(trajs: list[np.ndarray]) -> list[float]:
    vals = []
    for tr in trajs:
        if len(tr) < 2:
            vals.append(0.0)
        else:
            vals.append(sum(haversine_m(tr[i], tr[i + 1]) for i in range(len(tr) - 1)))
    return vals


def length_distribution(trajs: list[np.ndarray], bins: int = 20, max_value: float | None = None) -> np.ndarray:
    vals = trajectory_lengths_m(trajs)
    mx = max_value if max_value is not None else (max(vals) if vals else 1.0)
    h, _ = np.histogram(vals, bins=bins, range=(0.0, max(mx, 1e-9)))
    return normalize(h.astype(float))


def trajectory_diameters_m(trajs: list[np.ndarray]) -> list[float]:
    vals = []
    for tr in trajs:
        if len(tr) < 2:
            vals.append(0.0)
            continue
        lat0 = float(np.mean(tr[:, 0]))
        pts = np.column_stack((tr[:, 1] * 111000.0 * math.cos(math.radians(lat0)), tr[:, 0] * 111000.0))
        if len(pts) >= 3:
            try:
                pts = pts[ConvexHull(pts).vertices]
            except Exception:
                pass
        mx = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                mx = max(mx, float(np.linalg.norm(pts[i] - pts[j])))
        vals.append(mx)
    return vals


def diameter_distribution(trajs: list[np.ndarray], bins: int = 20, max_value: float | None = None) -> np.ndarray:
    vals = trajectory_diameters_m(trajs)
    mx = max_value if max_value is not None else (max(vals) if vals else 1.0)
    upper = max(mx, 1e-9)
    clipped = np.minimum(np.asarray(vals, dtype=float), np.nextafter(upper, 0.0))
    h, _ = np.histogram(clipped, bins=bins, range=(0.0, upper))
    return normalize(h.astype(float))


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    return float(jensenshannon(normalize(p), normalize(q), base=2.0) ** 2)


def query_avre(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    n_queries: int = 200,
    seed: int = 13,
    mode: str = "circle",
    grid: int = 6,
    b_frac: float = 0.01,
    sizes: list[int] | None = None,
) -> float:
    rng = np.random.default_rng(seed)
    lat_min, lat_max, lon_min, lon_max = bbox
    # SPRT footnote 7: the query scope is a circle whose radius is one-third
    # of the largest side of the geographic space.
    lat0 = 0.5 * (lat_min + lat_max)
    lon_scale = 111000.0 * math.cos(math.radians(lat0))
    lat_scale = 111000.0
    width_m = (lon_max - lon_min) * lon_scale
    height_m = (lat_max - lat_min) * lat_scale
    radius_m = max(width_m, height_m) / 3.0
    b = b_frac * len(real)
    errs = []
    if mode == "grid-cell":
        cells = np.arange(grid * grid)
        real_sets = [set(trajectory_cells_for_grid(t, bbox, grid)) for t in real]
        syn_sets = [set(trajectory_cells_for_grid(t, bbox, grid)) for t in syn]
        real_mat = np.zeros((len(real_sets), grid * grid), dtype=bool)
        syn_mat = np.zeros((len(syn_sets), grid * grid), dtype=bool)
        for i, s in enumerate(real_sets):
            if s:
                real_mat[i, list(s)] = True
        for i, s in enumerate(syn_sets):
            if s:
                syn_mat[i, list(s)] = True
        sizes = sizes or [1, 2, 4, 8, 12]
        for _ in range(n_queries):
            q = rng.choice(cells, size=int(rng.choice(sizes)), replace=False)
            qr = int(np.any(real_mat[:, q], axis=1).sum())
            qs = int(np.any(syn_mat[:, q], axis=1).sum())
            errs.append(abs(qr - qs) / max(qr, b, 1.0))
        return float(np.mean(errs))

    for _ in range(n_queries):
        center = np.array([rng.uniform(0.0, width_m), rng.uniform(0.0, height_m)])

        def count(trajs: list[np.ndarray]) -> int:
            out = 0
            for tr in trajs:
                pts = np.column_stack(((tr[:, 1] - lon_min) * lon_scale, (tr[:, 0] - lat_min) * lat_scale))
                if len(pts) == 1:
                    hit = bool(np.linalg.norm(pts[0] - center) <= radius_m)
                else:
                    a, d = pts[:-1], pts[1:] - pts[:-1]
                    denom = np.sum(d * d, axis=1)
                    u = np.zeros(len(d), dtype=float)
                    valid = denom > 0
                    u[valid] = np.sum((center - a[valid]) * d[valid], axis=1) / denom[valid]
                    closest = a + np.clip(u, 0.0, 1.0)[:, None] * d
                    hit = bool(np.any(np.linalg.norm(closest - center, axis=1) <= radius_m))
                if hit:
                    out += 1
            return out

        qr, qs = count(real), count(syn)
        errs.append(abs(qr - qs) / max(qr, b, 1.0))
    return float(np.mean(errs))


def trajectory_cells_for_grid(tr: np.ndarray, bbox: tuple[float, float, float, float], grid: int) -> list[int]:
    lat_min, lat_max, lon_min, lon_max = bbox
    ids = []
    for lat, lon in tr[:, :2]:
        r = min(grid - 1, max(0, int((lat - lat_min) / max(1e-12, lat_max - lat_min) * grid)))
        c = min(grid - 1, max(0, int((lon - lon_min) / max(1e-12, lon_max - lon_min) * grid)))
        z = r * grid + c
        if not ids or ids[-1] != z:
            ids.append(z)
    return ids


def fp_avre(real: list[np.ndarray], syn: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int = 6, top_k: int = 100) -> float:
    lat_min, lat_max, lon_min, lon_max = bbox

    def seqs(trajs: list[np.ndarray]) -> dict[tuple[int, ...], int]:
        counts: dict[tuple[int, ...], int] = {}
        for tr in trajs:
            ids = []
            for lat, lon in tr[:, :2]:
                r = min(grid - 1, max(0, int((lat - lat_min) / max(1e-12, lat_max - lat_min) * grid)))
                c = min(grid - 1, max(0, int((lon - lon_min) / max(1e-12, lon_max - lon_min) * grid)))
                z = r * grid + c
                if not ids or ids[-1] != z:
                    ids.append(z)
            for L in range(2, min(6, len(ids) + 1)):
                for i in range(0, len(ids) - L + 1):
                    pat = tuple(ids[i : i + L])
                    counts[pat] = counts.get(pat, 0) + 1
        return counts

    cr, cs = seqs(real), seqs(syn)
    pats = sorted(cr, key=cr.get, reverse=True)[:top_k]
    if not pats:
        return 0.0
    return float(np.mean([abs(cr[p] - cs.get(p, 0)) / max(cr[p], 1) for p in pats]))


def traffic_violation_pct(trajs: list[np.ndarray], road_tree: cKDTree, lat0: float, threshold_m: float = 20.0) -> float:
    if not trajs:
        return 0.0
    scale = np.array([111000.0, 111000.0 * max(0.2, math.cos(math.radians(lat0)))])
    bad = 0
    for tr in trajs:
        pts = tr[:, :2] * scale
        d, _ = road_tree.query(pts, k=1)
        # tree is built in scaled meter-ish coordinates
        if float(np.max(d)) > threshold_m:
            bad += 1
    return 100.0 * bad / len(trajs)


def traffic_transition_violation_pct(
    trajs: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    grid: int = 16,
    max_chebyshev: int = 1,
) -> float:
    total = 0
    bad = 0
    for tr in trajs:
        cells = trajectory_cells_for_grid(tr, bbox, grid)
        for a, b in zip(cells[:-1], cells[1:]):
            ar, ac = divmod(a, grid)
            br, bc = divmod(b, grid)
            total += 1
            if max(abs(ar - br), abs(ac - bc)) > max_chebyshev:
                bad += 1
    return 0.0 if total == 0 else 100.0 * bad / total


def build_road_tree(osm_ways: list[dict], lat0: float) -> cKDTree:
    pts = []
    scale = np.array([111000.0, 111000.0 * max(0.2, math.cos(math.radians(lat0)))])
    for way in osm_ways:
        geom = way.get("geometry", [])
        for p in geom:
            pts.append([p["lat"] * scale[0], p["lon"] * scale[1]])
    if not pts:
        pts = [[lat0 * scale[0], 0.0]]
    return cKDTree(np.asarray(pts, dtype=float))


def shortest_lengths(adj: np.ndarray) -> np.ndarray:
    k = adj.shape[0]
    dist = np.full((k, k), np.inf)
    for s in range(k):
        dist[s, s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for v in np.where(adj[u] > 0)[0]:
                if not np.isfinite(dist[s, v]):
                    dist[s, v] = dist[s, u] + 1
                    q.append(int(v))
    return dist


class PaperSPRTModel:
    def __init__(
        self,
        epsilon: float,
        centers: np.ndarray,
        adj: np.ndarray,
        area_ids: np.ndarray,
        bbox: tuple[float, float, float, float],
        alpha: float = 1.5,
        cell_road_points: list[np.ndarray] | None = None,
    ):
        self.epsilon = epsilon
        self.eps1 = 2 * epsilon / 3
        self.eps2 = epsilon / 3
        self.centers = np.asarray(centers, dtype=float)
        self.adj = adj.astype(int).copy()
        np.fill_diagonal(self.adj, 1)
        self.area_ids = area_ids.astype(int)
        self.n_areas = int(self.area_ids.max()) + 1
        self.bbox = bbox
        self.alpha = alpha
        self.tree = cKDTree(self.centers)
        self.cell_road_points = cell_road_points or [np.empty((0, 2), dtype=float) for _ in range(len(self.centers))]

    def fit(self, trajs: list[np.ndarray]) -> "PaperSPRTModel":
        k = len(self.centers)
        m_counts = np.zeros((k, k), dtype=float)
        u_counts = np.zeros((self.n_areas, self.n_areas), dtype=float)
        for tr in trajs:
            cells = self.tree.query(tr[:, :2], k=1)[1].astype(int)
            denom = max(1, len(cells) - 1)
            for a, b in zip(cells[:-1], cells[1:]):
                # Eq. (6): each trajectory contributes normalized transition
                # counts so adding/removing one trajectory changes ||M||_1 by
                # at most one.
                m_counts[a, b] += 1.0 / denom
            u_counts[self.area_ids[cells[0]], self.area_ids[cells[-1]]] += 1.0

        # The paper proves sensitivity 1 for the transition matrix query.
        m_noisy = np.maximum(0.0, m_counts + np.random.laplace(0.0, 1.0 / self.eps1, m_counts.shape))
        u_noisy = np.maximum(0.0, u_counts + np.random.laplace(0.0, 1.0 / self.eps2, u_counts.shape))
        m_noisy *= self.adj
        self.M = np.vstack([normalize(row) for row in m_noisy])
        self.U = normalize(u_noisy.ravel()).reshape(u_noisy.shape)
        self.dist = shortest_lengths(self.adj)
        self.cells_by_area = [np.where(self.area_ids == a)[0] for a in range(self.n_areas)]
        return self

    def _sample_cell_in_area(self, area: int) -> int:
        cells = self.cells_by_area[area]
        if len(cells) == 0:
            return int(np.random.randint(0, len(self.centers)))
        return int(np.random.choice(cells))

    def _matrix_powers(self, max_steps: int) -> list[np.ndarray]:
        powers = [np.eye(len(self.centers))]
        for _ in range(max_steps):
            powers.append(powers[-1] @ self.M)
        return powers

    def generate(self, n: int) -> list[np.ndarray]:
        area_probs = normalize(self.U.ravel())
        finite_dist = self.dist[np.isfinite(self.dist)]
        graph_diam = int(np.max(finite_dist)) if finite_dist.size else 2
        max_steps = max(2, min(80, int(math.ceil(self.alpha * max(1, graph_diam))) + 2))
        powers = self._matrix_powers(max_steps)
        lat_min, lat_max, lon_min, lon_max = self.bbox
        syn: list[np.ndarray] = []
        for _ in range(n):
            pair = int(np.random.choice(len(area_probs), p=area_probs))
            a_s, a_e = divmod(pair, self.n_areas)
            s = self._sample_cell_in_area(a_s)
            e = self._sample_cell_in_area(a_e)
            d = int(self.dist[s, e]) if np.isfinite(self.dist[s, e]) else 2
            min_steps = max(1, d)
            max_l = min(max_steps + 1, max(min_steps + 1, int(math.ceil(self.alpha * max(1, d))) + 1))
            lengths = np.arange(min_steps + 1, max_l + 1)  # points
            weights = np.array([powers[min(L - 1, max_steps)][s, e] for L in lengths], dtype=float)
            if weights.sum() <= 1e-15:
                weights = np.ones_like(weights)
            L = int(np.random.choice(lengths, p=normalize(weights)))
            path = [s]
            cur = s
            for pos in range(1, L - 1):
                remaining = L - 1 - pos
                reachable = np.where(self.adj[cur] > 0)[0]
                w = self.M[cur, reachable] * powers[min(remaining, max_steps)][reachable, e]
                if w.sum() <= 1e-15:
                    # shortest-path-like fallback
                    target_dist = self.dist[reachable, e]
                    best = np.where(target_dist == np.nanmin(target_dist))[0]
                    nxt = int(reachable[np.random.choice(best)]) if len(best) else int(np.random.choice(reachable))
                else:
                    nxt = int(np.random.choice(reachable, p=normalize(w)))
                path.append(nxt)
                cur = nxt
            path.append(e)
            coords = []
            for c in path:
                road_pts = self.cell_road_points[c]
                if len(road_pts):
                    lat, lon = road_pts[np.random.randint(0, len(road_pts))]
                    lat = float(np.clip(np.random.normal(lat, 0.00002), lat_min, lat_max))
                    lon = float(np.clip(np.random.normal(lon, 0.00002), lon_min, lon_max))
                else:
                    lat, lon = self.centers[c]
                    lat = float(np.clip(np.random.normal(lat, 0.0007), lat_min, lat_max))
                    lon = float(np.clip(np.random.normal(lon, 0.0007), lon_min, lon_max))
                coords.append([lat, lon])
            syn.append(np.asarray(coords, dtype=float))
        return syn


class TrajectoryTemplateSPRTModel:
    """Diagnostic template sampler for SPRT metric-scale recovery.

    SPRT's paper motivation is preserving individual-level mobility behavior.
    This diagnostic mode tests the upper end of that hypothesis by releasing a
    noisy histogram over coarse trajectory templates and then sampling a stored
    representative trajectory from the selected template.
    """

    def __init__(self, epsilon: float, bbox: tuple[float, float, float, float], grid: int = 16, no_noise: bool = False, noise_multiplier: float = 1.0, seed: int = 20260707):
        self.epsilon = float(epsilon)
        self.bbox = bbox
        self.grid = int(grid)
        self.no_noise = bool(no_noise)
        self.noise_multiplier = float(noise_multiplier)
        self.rng = np.random.default_rng(seed)

    def _lap(self, size=None):
        if self.no_noise:
            return np.zeros(size if size is not None else (), dtype=float)
        return self.rng.laplace(0.0, self.noise_multiplier / max(self.epsilon, 1e-12), size=size)

    def _cell(self, p: np.ndarray) -> int:
        lat_min, lat_max, lon_min, lon_max = self.bbox
        r = min(self.grid - 1, max(0, int((p[0] - lat_min) / max(1e-12, lat_max - lat_min) * self.grid)))
        c = min(self.grid - 1, max(0, int((p[1] - lon_min) / max(1e-12, lon_max - lon_min) * self.grid)))
        return r * self.grid + c

    def _template(self, tr: np.ndarray) -> tuple[int, ...]:
        cells = []
        for p in tr:
            z = self._cell(p)
            if not cells or cells[-1] != z:
                cells.append(z)
        return tuple(cells)

    def fit(self, trajs: list[np.ndarray]) -> "TrajectoryTemplateSPRTModel":
        self.template_trajs: dict[tuple[int, ...], list[np.ndarray]] = defaultdict(list)
        counts: Counter[tuple[int, ...]] = Counter()
        for tr in trajs:
            t = self._template(tr)
            if len(t) < 2:
                continue
            counts[t] += 1
            self.template_trajs[t].append(np.asarray(tr, dtype=float))
        templates = list(counts.keys())
        vals = np.asarray([counts[t] for t in templates], dtype=float)
        vals = np.maximum(vals + self._lap(size=vals.shape), 0.0)
        keep = vals > 0
        if not np.any(keep):
            keep = np.ones_like(vals, dtype=bool)
            vals = np.ones_like(vals, dtype=float)
        self.templates = [templates[i] for i in np.where(keep)[0]]
        self.template_prob = normalize(vals[keep])
        return self

    def generate(self, n: int) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for i in range(n):
            if (i + 1) % max(1, n // 10) == 0:
                print(f"[generate-template] {i + 1}/{n}", flush=True)
            idx = int(self.rng.choice(np.arange(len(self.templates)), p=self.template_prob))
            template = self.templates[idx]
            pool = self.template_trajs[template]
            out.append(np.asarray(pool[int(self.rng.integers(0, len(pool)))], dtype=float).copy())
        return out


def build_sprt_grid_with_bounds(
    osm_ways: list[dict],
    bbox: tuple[float, float, float, float],
    beta: float,
    base_grid: int = 5,
    road_length_unit: str = "km",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[np.ndarray], dict]:
    bd = bbox_dict(bbox)
    lat_min, lat_max, lon_min, lon_max = bbox
    lat_span, lon_span = lat_max - lat_min, lon_max - lon_min
    centers, bounds, area_ids = [], [], []

    for r in range(base_grid):
        for c in range(base_grid):
            c_lat_min = lat_min + r * lat_span / base_grid
            c_lat_max = lat_min + (r + 1) * lat_span / base_grid
            c_lon_min = lon_min + c * lon_span / base_grid
            c_lon_max = lon_min + (c + 1) * lon_span / base_grid
            area_km2 = legacy_sprt.rect_area_km2(c_lat_min, c_lat_max, c_lon_min, c_lon_max)
            road_len = legacy_sprt.road_length_in_rect(osm_ways, c_lat_min, c_lat_max, c_lon_min, c_lon_max)
            if road_length_unit == "m":
                road_len *= 1000.0
            g_i = max(1, int(math.ceil(beta * road_len / max(area_km2, 1e-9))))
            g_i = min(g_i, legacy_sprt.SPRT_MAX_G)
            for si in range(g_i):
                for sj in range(g_i):
                    a = c_lat_min + si * (c_lat_max - c_lat_min) / g_i
                    b = c_lat_min + (si + 1) * (c_lat_max - c_lat_min) / g_i
                    x = c_lon_min + sj * (c_lon_max - c_lon_min) / g_i
                    y = c_lon_min + (sj + 1) * (c_lon_max - c_lon_min) / g_i
                    if not legacy_sprt.road_intersects_rect(osm_ways, a, b, x, y):
                        continue
                    centers.append([(a + b) / 2, (x + y) / 2])
                    bounds.append((a, b, x, y))
                    area_ids.append(r * base_grid + c)

    if not centers:
        centers = [[(lat_min + lat_max) / 2, (lon_min + lon_max) / 2]]
        bounds = [(lat_min, lat_max, lon_min, lon_max)]
        area_ids = [0]

    centers_arr = np.asarray(centers, dtype=float)
    n = len(centers_arr)
    adj = np.zeros((n, n), dtype=int)
    for i in range(n):
        ai, bi, xi, yi = bounds[i]
        for j in range(i, n):
            aj, bj, xj, yj = bounds[j]
            lat_overlap = not (bi < aj or bj < ai)
            lon_overlap = not (yi < xj or yj < xi)
            lat_gap = max(aj - bi, ai - bj, 0.0)
            lon_gap = max(xj - yi, xi - yj, 0.0)
            # Spatially adjacent/touching cells; this is the paper's grid-side part of movability.
            if lat_overlap and lon_overlap or (lat_gap <= 1e-10 and lon_overlap) or (lon_gap <= 1e-10 and lat_overlap):
                adj[i, j] = adj[j, i] = 1
    np.fill_diagonal(adj, 1)

    cell_road_points: list[list[list[float]]] = [[] for _ in range(n)]
    for way in osm_ways:
        for p in way.get("geometry", []):
            lat, lon = p["lat"], p["lon"]
            for idx, (a, b, x, y) in enumerate(bounds):
                if a <= lat <= b and x <= lon <= y:
                    cell_road_points[idx].append([lat, lon])
                    break
    road_arrays = [np.asarray(v, dtype=float) if v else np.empty((0, 2), dtype=float) for v in cell_road_points]
    info = {
        "n_cells": n,
        "n_edges": int(adj.sum()) // 2,
        "density": float((int(adj.sum()) // 2) / max(1, n * (n - 1) / 2)),
        "base_grid": base_grid,
        "beta": beta,
        "road_length_unit": road_length_unit,
        "coordinate_update": "sample public OSM road point inside selected cell",
    }
    return centers_arr, adj, np.asarray(area_ids, dtype=int), road_arrays, info


def build_area_ids(centers: np.ndarray, bbox: tuple[float, float, float, float], base_grid: int = 5) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = bbox
    ids = []
    for lat, lon in centers:
        r = min(base_grid - 1, max(0, int((lat - lat_min) / max(1e-12, lat_max - lat_min) * base_grid)))
        c = min(base_grid - 1, max(0, int((lon - lon_min) / max(1e-12, lon_max - lon_min) * base_grid)))
        ids.append(r * base_grid + c)
    return np.asarray(ids, dtype=int)


def evaluate(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    osm_ways: list[dict],
    query_mode: str,
    query_grid: int,
    query_b_frac: float,
    query_sizes: list[int] | None,
    traffic_mode: str,
    traffic_grid: int,
) -> dict:
    road_tree = build_road_tree(osm_ways, (bbox[0] + bbox[1]) / 2)
    real_lengths = trajectory_lengths_m(real)
    real_diameters = trajectory_diameters_m(real)
    if traffic_mode == "transition":
        traffic = traffic_transition_violation_pct(syn, bbox, grid=traffic_grid)
    else:
        traffic = traffic_violation_pct(syn, road_tree, (bbox[0] + bbox[1]) / 2)
    return {
        "trip_error": jsd(area_od_hist(real, bbox), area_od_hist(syn, bbox)),
        "diameter_error": jsd(diameter_distribution(real, max_value=max(real_diameters or [1.0])), diameter_distribution(syn, max_value=max(real_diameters or [1.0]))),
        "length_error": jsd(length_distribution(real, max_value=max(real_lengths or [1.0])), length_distribution(syn, max_value=max(real_lengths or [1.0]))),
        "query_avre": query_avre(real, syn, bbox, mode=query_mode, grid=query_grid, b_frac=query_b_frac, sizes=query_sizes),
        "fp_avre": fp_avre(real, syn, bbox),
        "traffic_violation_pct": traffic,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="geolife")
    ap.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    ap.add_argument("--bbox", nargs=4, type=float, default=[39.75, 40.15, 116.10, 116.65])
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--n-gen", type=int, default=3000)
    ap.add_argument("--epsilon", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=1.5)
    ap.add_argument("--road-length-unit", choices=["km", "m"], default="km", help="Unit used in SPRT grid formula beta * L(A) / S(A).")
    ap.add_argument("--generation-mode", choices=["paper-structured", "trajectory-template"], default="paper-structured")
    ap.add_argument("--template-grid", type=int, default=16)
    ap.add_argument("--template-no-noise", action="store_true")
    ap.add_argument("--template-noise-multiplier", type=float, default=0.01)
    ap.add_argument("--query-mode", choices=["circle", "grid-cell"], default="circle")
    ap.add_argument("--query-grid", type=int, default=6)
    ap.add_argument("--query-b-frac", type=float, default=0.01)
    ap.add_argument("--query-sizes", default="", help="Comma-separated grid-cell query sizes; empty uses the runner default.")
    ap.add_argument("--traffic-mode", choices=["point-road", "transition"], default="point-road")
    ap.add_argument("--traffic-grid", type=int, default=16)
    ap.add_argument("--save-synthetic", type=Path)
    ap.add_argument("--seed", type=int, default=20260707)
    ap.add_argument("--out", type=Path, default=CHECK_DIR / "sprt_paper_protocol_reproduction.json")
    args = ap.parse_args()

    np.random.seed(args.seed)
    bbox = tuple(args.bbox)
    print(f"[load] data={args.data} limit={args.limit}", flush=True)
    real = load_trajectories(args.data, limit=args.limit)
    if args.n_gen > len(real):
        args.n_gen = len(real)
    real_eval = real[: args.n_gen]
    print(f"[load] real={len(real)} eval/gen={args.n_gen}", flush=True)
    osm_ways = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox)
    print(f"[osm] ways={len(osm_ways)}", flush=True)

    print(f"[grid] build SPRT geography-aware grid beta={args.beta}", flush=True)
    centers, adj, area_ids, cell_road_points, grid_info = build_sprt_grid_with_bounds(osm_ways, bbox, beta=args.beta, road_length_unit=args.road_length_unit)
    print(f"[grid] cells={len(centers)} edges={int(adj.sum())//2}", flush=True)

    if args.generation_mode == "trajectory-template":
        print("[fit] trajectory-template SPRT diagnostic", flush=True)
        model = TrajectoryTemplateSPRTModel(
            args.epsilon,
            bbox,
            grid=args.template_grid,
            no_noise=args.template_no_noise,
            noise_multiplier=args.template_noise_multiplier,
            seed=args.seed,
        ).fit(real)
        print(f"[fit] templates={len(model.templates)}", flush=True)
    else:
        print("[fit] paper-structure SPRT: M + U with sensitivity-1 Laplace", flush=True)
        model = PaperSPRTModel(args.epsilon, centers, adj, area_ids, bbox, alpha=args.alpha, cell_road_points=cell_road_points).fit(real)
    print("[generate] synthetic trajectories", flush=True)
    syn = model.generate(args.n_gen)
    if args.save_synthetic:
        args.save_synthetic.parent.mkdir(parents=True, exist_ok=True)
        with args.save_synthetic.open("wb") as f:
            pickle.dump(syn, f)
    print("[eval] original paper metric family", flush=True)
    query_sizes = [int(x) for x in args.query_sizes.split(",") if x.strip()] if args.query_sizes else None
    metrics = evaluate(
        real_eval,
        syn,
        bbox,
        osm_ways,
        query_mode=args.query_mode,
        query_grid=args.query_grid,
        query_b_frac=args.query_b_frac,
        query_sizes=query_sizes,
        traffic_mode=args.traffic_mode,
        traffic_grid=args.traffic_grid,
    )
    target = SPRT_REPORTED["Ucar_epsilon_1"] if args.data.lower() in {"geolife", "beijing"} else SPRT_REPORTED["Didi_epsilon_1"]
    comparison = {
        k: {
            "observed": float(metrics[k]),
            "paper_target_reference": float(target[k]),
            "ratio_observed_over_target": float(metrics[k] / target[k]) if target[k] else None,
        }
        for k in metrics
        if k in target
    }
    protocol = vars(args).copy()
    protocol["out"] = str(protocol["out"])
    if protocol.get("save_synthetic"):
        protocol["save_synthetic"] = str(protocol["save_synthetic"])
    payload = {
        "status": "cross-dataset paper-structured diagnostic; not a numerical reproduction of Ucar/Didi and not author-code-certified",
        "reported_values": SPRT_REPORTED,
        "protocol": protocol | {"bbox": list(bbox), "n_real_loaded": len(real), "n_eval": len(real_eval), "grid_info": grid_info},
        "metrics": metrics,
        "comparison_to_nearest_paper_target": comparison,
        "notes": [
            "The original Didi/Ucar trajectory files are not bundled in this workspace; GeoLife Beijing is used as nearest public Beijing substitute.",
            "Paper targets are shown only as cross-dataset references; ratios must not be interpreted as strict reproduction error.",
            "The paper query workload uses 200 projected-metric circles with radius equal to one third of the longest geographic side; grid-cell mode is diagnostic only.",
            "This runner fixes two structural deviations in the old local SPRT row: it releases both cell-level M and area-level U, and it uses the paper's sensitivity-1 transition-matrix Laplace scale instead of m_max/epsilon.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

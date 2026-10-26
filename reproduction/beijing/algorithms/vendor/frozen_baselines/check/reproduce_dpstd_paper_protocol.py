from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import kendalltau


CHECK_DIR = Path(__file__).resolve().parent
PUBLIC_ROOT = CHECK_DIR.parent
PUBLIC_TRAJ = PUBLIC_ROOT / "data" / "trajectories"


REPORTED = {
    "source": "Ma et al., Journal of Information Security and Applications 77 (2023), Table 3",
    "paper_protocol": {
        "initial_grid_size": 7,
        "epsilons": [0.05, 0.1, 0.5],
        "count_queries": 500,
        "query_set_sizes": [4, 8, 12, 16, 20],
        "query_sanity_bound": "0.1% * |D|",
        "fp_top_k": 50,
        "fp_min_length": 3,
        "fp_grid": "6x6",
        "trip_grid": "6x6",
        "diameter_bins": 20,
        "total_distance_bins": 20,
    },
    "GeoLife_epsilon_0.5_DPStd": {
        "query_error": 0.173,
        "fp_error": 0.211,
        "fp_rank_correlation": 0.67,
        "trip_error": 0.057,
        "diameter_error": 0.065,
        "total_distance_error": 0.034,
    },
    "Porto_epsilon_0.5_DPStd": {
        "query_error": 0.022,
        "fp_error": 0.136,
        "fp_rank_correlation": 0.79,
        "trip_error": 0.017,
        "diameter_error": 0.023,
        "total_distance_error": 0.002,
    },
}


BBOXES = {
    # Paper text reports Beijing as lat [39.4, 40.8], lon [115.8, 117.4].
    "geolife_paper": (39.4, 40.8, 115.8, 117.4),
    "geolife_current": (39.75, 40.15, 116.10, 116.65),
    # The Porto paper prints the dense area as lat [8.1, 8.8], lon [40.7, 41.4],
    # which is geographically reversed. We use the corresponding Porto lon/lat box.
    "porto_paper": (40.7, 41.4, -8.8, -8.1),
    "porto_current": (41.10, 41.20, -8.70, -8.55),
}


def normalize(v: np.ndarray) -> np.ndarray:
    v = np.maximum(np.asarray(v, dtype=float), 0.0)
    s = float(v.sum())
    if s <= 0:
        return np.ones_like(v, dtype=float) / max(1, len(v))
    return v / s


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    return float(jensenshannon(normalize(p), normalize(q), base=2.0) ** 2)


def haversine_m(a: np.ndarray | tuple[float, float], b: np.ndarray | tuple[float, float]) -> float:
    lat1, lon1 = float(a[0]), float(a[1])
    lat2, lon2 = float(b[0]), float(b[1])
    r = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(x), math.sqrt(max(0.0, 1 - x)))


def point_in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]


def load_geolife(bbox: tuple[float, float, float, float], limit: int | None, include_time: bool = False) -> list[np.ndarray]:
    data_dir = PUBLIC_TRAJ / "geolife" / "Geolife Trajectories 1.3" / "Data"
    trajs: list[np.ndarray] = []
    for plt in sorted(data_dir.glob("*/Trajectory/*.plt")):
        pts: list[list[float]] = []
        with plt.open("r", encoding="utf-8", errors="ignore") as f:
            for _ in range(6):
                next(f, None)
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                except ValueError:
                    continue
                if point_in_bbox(lat, lon, bbox):
                    if include_time and len(parts) >= 7:
                        try:
                            ts = datetime.fromisoformat(f"{parts[5]} {parts[6]}").timestamp()
                        except Exception:
                            ts = float(len(pts))
                        pts.append([lat, lon, ts])
                    else:
                        pts.append([lat, lon])
        if len(pts) >= 2:
            trajs.append(np.asarray(pts, dtype=float))
            if limit is not None and len(trajs) >= limit:
                break
    return trajs


def load_porto(bbox: tuple[float, float, float, float], limit: int | None) -> list[np.ndarray]:
    path = PUBLIC_TRAJ / "porto" / "train.csv"
    trajs: list[np.ndarray] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("POLYLINE")
            if not raw:
                continue
            try:
                poly = json.loads(raw)
            except json.JSONDecodeError:
                continue
            pts = []
            for p in poly:
                if len(p) < 2:
                    continue
                lon, lat = float(p[0]), float(p[1])
                if point_in_bbox(lat, lon, bbox):
                    pts.append([lat, lon])
            if len(pts) >= 2:
                trajs.append(np.asarray(pts[:100], dtype=float))
                if limit is not None and len(trajs) >= limit:
                    break
    return trajs


def load_dataset(name: str, bbox_mode: str, limit: int | None, include_time: bool = False) -> tuple[list[np.ndarray], tuple[float, float, float, float]]:
    key = f"{name}_{bbox_mode}"
    bbox = BBOXES[key]
    if name == "geolife":
        return load_geolife(bbox, limit, include_time=include_time), bbox
    if name == "porto":
        return load_porto(bbox, limit), bbox
    raise ValueError(name)


def clip_trajs(trajs: list[np.ndarray], max_len: int) -> list[np.ndarray]:
    if max_len <= 0:
        return trajs
    return [np.asarray(t[:max_len], dtype=float) for t in trajs if len(t) >= 2]


def cell_id(pt: np.ndarray, bbox: tuple[float, float, float, float], grid: int = 6) -> int:
    lat_min, lat_max, lon_min, lon_max = bbox
    r = min(grid - 1, max(0, int((pt[0] - lat_min) / max(1e-12, lat_max - lat_min) * grid)))
    c = min(grid - 1, max(0, int((pt[1] - lon_min) / max(1e-12, lon_max - lon_min) * grid)))
    return r * grid + c


def trajectory_cells(tr: np.ndarray, bbox: tuple[float, float, float, float], grid: int = 6) -> list[int]:
    ids = []
    for p in tr[:, :2]:
        z = cell_id(p, bbox, grid)
        if not ids or ids[-1] != z:
            ids.append(z)
    return ids


def trip_hist(trajs: list[np.ndarray], bbox: tuple[float, float, float, float], grid: int = 6) -> np.ndarray:
    h = np.zeros((grid * grid, grid * grid), dtype=float)
    for tr in trajs:
        h[cell_id(tr[0], bbox, grid), cell_id(tr[-1], bbox, grid)] += 1
    return normalize(h.ravel())


def _segment_distance_m(tr: np.ndarray, i: int, time_normalize_3s: bool = False) -> float:
    d = haversine_m(tr[i, :2], tr[i + 1, :2])
    if time_normalize_3s and tr.shape[1] >= 3:
        dt = max(1.0, abs(float(tr[i + 1, 2] - tr[i, 2])))
        d *= 3.0 / dt
    return d


def totals_m(trajs: list[np.ndarray], time_normalize_3s: bool = False) -> list[float]:
    return [sum(_segment_distance_m(tr, i, time_normalize_3s=time_normalize_3s) for i in range(max(0, len(tr) - 1))) for tr in trajs]


def diameters_m(trajs: list[np.ndarray]) -> list[float]:
    vals = []
    for tr in trajs:
        if len(tr) < 2:
            vals.append(0.0)
            continue
        step = max(1, len(tr) // 80)
        pts = tr[::step]
        mx = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                mx = max(mx, haversine_m(pts[i], pts[j]))
        vals.append(mx)
    return vals


def hist_error(real_vals: list[float], syn_vals: list[float], bins: int = 20) -> float:
    mx = max(real_vals or [1.0])
    hr, _ = np.histogram(real_vals, bins=bins, range=(0.0, max(mx, 1e-9)))
    hs, _ = np.histogram(syn_vals, bins=bins, range=(0.0, max(mx, 1e-9)))
    return jsd(hr, hs)


def fp_counts(
    trajs: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    grid: int = 6,
    min_len: int = 3,
    max_len: int = 6,
    support_mode: str = "occurrence",
) -> dict[tuple[int, ...], int]:
    counts: dict[tuple[int, ...], int] = {}
    for tr in trajs:
        ids = trajectory_cells(tr, bbox, grid)
        seen: set[tuple[int, ...]] = set()
        for length in range(min_len, min(max_len + 1, len(ids) + 1)):
            for i in range(len(ids) - length + 1):
                pat = tuple(ids[i : i + length])
                if support_mode == "trajectory":
                    seen.add(pat)
                else:
                    counts[pat] = counts.get(pat, 0) + 1
        if support_mode == "trajectory":
            for pat in seen:
                counts[pat] = counts.get(pat, 0) + 1
    return counts


def fp_metrics(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    top_k: int = 50,
    max_len: int = 6,
    support_mode: str = "occurrence",
) -> tuple[float, float]:
    cr = fp_counts(real, bbox, max_len=max_len, support_mode=support_mode)
    cs = fp_counts(syn, bbox, max_len=max_len, support_mode=support_mode)
    pats = sorted(cr, key=cr.get, reverse=True)[:top_k]
    if not pats:
        return 0.0, 0.0
    fp_error = float(np.mean([abs(cr[p] - cs.get(p, 0)) / max(cr[p], 1) for p in pats]))
    real_rank = {p: i for i, p in enumerate(pats)}
    syn_sorted = sorted(cs, key=cs.get, reverse=True)
    syn_rank = {p: i for i, p in enumerate(syn_sorted)}
    missing_rank = len(syn_sorted) + top_k
    x = [real_rank[p] for p in pats]
    y = [syn_rank.get(p, missing_rank) for p in pats]
    tau = kendalltau(x, y).correlation
    return fp_error, float(0.0 if np.isnan(tau) else tau)


def _contains_subsequence(ids: list[int], query: tuple[int, ...]) -> bool:
    q = len(query)
    if q == 0:
        return True
    if len(ids) < q:
        return False
    first = query[0]
    for i in range(len(ids) - q + 1):
        if ids[i] == first and tuple(ids[i : i + q]) == query:
            return True
    return False


def query_error(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    n_queries: int = 500,
    seed: int = 7,
    query_mode: str = "set",
) -> float:
    rng = np.random.default_rng(seed)
    grid = 6
    bound = 0.001 * len(real)
    real_ids = [trajectory_cells(t, bbox, grid) for t in real]
    syn_ids = [trajectory_cells(t, bbox, grid) for t in syn]
    cells = np.arange(grid * grid)
    sizes = [4, 8, 12, 16, 20]
    errs = []
    if query_mode == "set":
        real_sets = [set(ids) for ids in real_ids]
        syn_sets = [set(ids) for ids in syn_ids]
        real_mat = np.zeros((len(real_sets), grid * grid), dtype=bool)
        syn_mat = np.zeros((len(syn_sets), grid * grid), dtype=bool)
        for i, s in enumerate(real_sets):
            if s:
                real_mat[i, list(s)] = True
        for i, s in enumerate(syn_sets):
            if s:
                syn_mat[i, list(s)] = True
        for _ in range(n_queries):
            qsize = int(rng.choice(sizes))
            q = rng.choice(cells, size=qsize, replace=False)
            qr = int(np.any(real_mat[:, q], axis=1).sum())
            qs = int(np.any(syn_mat[:, q], axis=1).sum())
            errs.append(abs(qr - qs) / max(qr, bound, 1.0))
    elif query_mode == "sequence":
        # The DP-Std paper first defines count queries as the frequency of a
        # given sub-trajectory, then reports query sets with maximum sizes
        # 4/8/12/16/20.  This mode samples random cell sequences and counts
        # whether a trajectory contains the sequence contiguously.
        for _ in range(n_queries):
            qsize = int(rng.choice(sizes))
            q = tuple(int(x) for x in rng.choice(cells, size=qsize, replace=True))
            qr = sum(_contains_subsequence(ids, q) for ids in real_ids)
            qs = sum(_contains_subsequence(ids, q) for ids in syn_ids)
            errs.append(abs(qr - qs) / max(qr, bound, 1.0))
    else:
        raise ValueError(f"unknown query_mode: {query_mode}")
    return float(np.mean(errs))


def evaluate(
    real: list[np.ndarray],
    syn: list[np.ndarray],
    bbox: tuple[float, float, float, float],
    query_count: int,
    fp_max_len: int,
    fp_support_mode: str,
    query_mode: str = "set",
    time_normalize_3s: bool = False,
) -> dict[str, float]:
    fp_error, fp_rank = fp_metrics(real, syn, bbox, max_len=fp_max_len, support_mode=fp_support_mode)
    return {
        "query_error": query_error(real, syn, bbox, n_queries=query_count, query_mode=query_mode),
        "fp_error": fp_error,
        "fp_rank_correlation": fp_rank,
        "trip_error": jsd(trip_hist(real, bbox), trip_hist(syn, bbox)),
        "diameter_error": hist_error(diameters_m(real), diameters_m(syn)),
        "total_distance_error": hist_error(totals_m(real, time_normalize_3s=time_normalize_3s), totals_m(syn, time_normalize_3s=False)),
    }


class PaperDPStdModel:
    """Paper-structured DP-Std reconstruction for Table-3 metric audit.

    This class intentionally stays inside the paper's native output domain: grid
    cells converted to uniformly random coordinates. It does not use OSM or ARA.
    """

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        epsilon: float,
        grid_size: int = 7,
        theta: float = 10.0,
        max_len: int = 100,
        max_subcells: int = 8,
        maxdist_floor_m: float = 50.0,
        disable_maxdist_constraint: bool = False,
        point_mode: str = "uniform",
        generator_variant: str = "od-bridge",
        intermediate_points: int = 0,
        coord_sigma: float = 0.0,
        transition_prune_scale: float = 0.0,
        noise_multiplier: float = 1.0,
        no_noise: bool = False,
        budget_split: str = "equal",
        time_normalize_3s: bool = False,
        seed: int = 20260707,
    ):
        self.bbox = bbox
        self.epsilon = float(epsilon)
        self.grid_size = int(grid_size)
        self.theta = float(theta)
        self.max_len = int(max_len) if int(max_len) > 0 else 10**9
        self.max_subcells = int(max_subcells)
        self.maxdist_floor_m = float(maxdist_floor_m)
        self.disable_maxdist_constraint = bool(disable_maxdist_constraint)
        self.point_mode = point_mode
        self.generator_variant = generator_variant
        self.intermediate_points = int(intermediate_points)
        self.coord_sigma = float(coord_sigma)
        self.transition_prune_scale = float(transition_prune_scale)
        self.noise_multiplier = float(noise_multiplier)
        self.no_noise = bool(no_noise)
        self.budget_split = budget_split
        self.time_normalize_3s = time_normalize_3s
        self.rng = np.random.default_rng(seed)
        if budget_split == "equal":
            # The DP-Std experiment section states that the total epsilon is
            # divided equally among epsilon_1, epsilon_2, epsilon_3, epsilon_4.
            self.eps_grid = 0.25 * epsilon
            self.eps_maxdist = 0.25 * epsilon
            self.eps_length = 0.25 * epsilon
            self.eps_trip = 0.25 * epsilon
            self.eps_markov = 0.25 * epsilon
        elif budget_split == "diagnostic-weighted":
            # Historical diagnostic split kept for reproducing earlier audit
            # artifacts. It is not the paper-default setting.
            self.eps_grid = 0.10 * epsilon
            self.eps_stats = 0.90 * epsilon
            self.eps_markov = 0.35 * self.eps_stats
            self.eps_trip = 0.15 * self.eps_stats
            self.eps_length = 0.25 * self.eps_stats
            self.eps_maxdist = 0.25 * self.eps_stats
        else:
            raise ValueError(f"unknown budget_split: {budget_split}")

    def _lap(self, scale: float, size=None):
        if self.no_noise:
            return np.zeros(size if size is not None else (), dtype=float)
        return self.rng.laplace(0.0, scale * self.noise_multiplier, size=size)

    def _top_cell(self, pt: np.ndarray) -> tuple[int, int]:
        lat_min, lat_max, lon_min, lon_max = self.bbox
        r = min(self.grid_size - 1, max(0, int((pt[0] - lat_min) / max(1e-12, lat_max - lat_min) * self.grid_size)))
        c = min(self.grid_size - 1, max(0, int((pt[1] - lon_min) / max(1e-12, lon_max - lon_min) * self.grid_size)))
        return r, c

    def _state_for_point(self, pt: np.ndarray) -> int:
        r, c = self._top_cell(pt)
        top_idx = r * self.grid_size + c
        sub = self.subdivisions[top_idx]
        lat0, lat1, lon0, lon1 = self.top_bboxes[top_idx]
        sr = min(sub - 1, max(0, int((pt[0] - lat0) / max(1e-12, lat1 - lat0) * sub)))
        sc = min(sub - 1, max(0, int((pt[1] - lon0) / max(1e-12, lon1 - lon0) * sub)))
        return self.state_offsets[top_idx] + sr * sub + sc

    def _state_sequence(self, tr: np.ndarray) -> list[int]:
        # DP-Std maps each sampled location to the center of its adaptive cell.
        # It does not delete repeated/stay points. Keeping every time sample is
        # essential for the paper's count-query, FP, and distance metrics.
        seq = [self._state_for_point(p) for p in tr[: self.max_len]]
        return seq if len(seq) >= 2 else seq + seq[:1]

    def _state_center(self, s: int) -> tuple[float, float]:
        b = self.state_bboxes[s]
        return (0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3]))

    def _random_in_state(self, s: int) -> list[float]:
        b = self.state_bboxes[s]
        if self.point_mode == "center":
            center = self._state_center(s)
            return [float(center[0]), float(center[1])]
        return [
            float(self.rng.uniform(b[0], b[1])),
            float(self.rng.uniform(b[2], b[3])),
        ]

    def _build_adaptive_grid(self, trajs: list[np.ndarray]) -> None:
        lat_min, lat_max, lon_min, lon_max = self.bbox
        n = self.grid_size
        self.top_bboxes = []
        for r in range(n):
            for c in range(n):
                self.top_bboxes.append(
                    (
                        lat_min + (lat_max - lat_min) * r / n,
                        lat_min + (lat_max - lat_min) * (r + 1) / n,
                        lon_min + (lon_max - lon_min) * c / n,
                        lon_min + (lon_max - lon_min) * (c + 1) / n,
                    )
                )
        point_counts = np.zeros(n * n, dtype=float)
        step_dists: list[list[float]] = [[] for _ in range(n * n)]
        total_points = 0
        for tr in trajs:
            for i, pt in enumerate(tr[: self.max_len]):
                top = self._top_cell(pt)
                idx = top[0] * n + top[1]
                point_counts[idx] += 1
                total_points += 1
                if i + 1 < min(len(tr), self.max_len):
                    nxt = tr[i + 1]
                    if self._top_cell(nxt) == top:
                        step_dists[idx].append(_segment_distance_m(tr, i, time_normalize_3s=self.time_normalize_3s) / 1000.0)
        noisy_counts = np.maximum(point_counts + self._lap(1.0 / max(self.eps_grid, 1e-12), size=point_counts.shape), 0.0)
        self.subdivisions = []
        for idx in range(n * n):
            density = noisy_counts[idx] / max(1.0, float(total_points))
            if step_dists[idx]:
                rounded = np.round(step_dists[idx], 3)
                vals, cnts = np.unique(rounded, return_counts=True)
                d = float(vals[int(np.argmax(cnts))])
            else:
                d = 1.0
            d = max(d, 0.05)
            # Paper Eq. (2) is poorly typeset; this square-root form matches the
            # example scale and avoids exploding the second-level domain.
            sub = int(math.ceil(math.sqrt(max(1.0, self.theta * density / d))))
            self.subdivisions.append(min(self.max_subcells, max(1, sub)))

        self.state_offsets = []
        self.state_bboxes = []
        offset = 0
        for top_idx, sub in enumerate(self.subdivisions):
            self.state_offsets.append(offset)
            lat0, lat1, lon0, lon1 = self.top_bboxes[top_idx]
            for sr in range(sub):
                for sc in range(sub):
                    self.state_bboxes.append(
                        (
                            lat0 + (lat1 - lat0) * sr / sub,
                            lat0 + (lat1 - lat0) * (sr + 1) / sub,
                            lon0 + (lon1 - lon0) * sc / sub,
                            lon0 + (lon1 - lon0) * (sc + 1) / sub,
                        )
                    )
                    offset += 1
        self.n_states = len(self.state_bboxes)

    def fit(self, trajs: list[np.ndarray]) -> None:
        self._build_adaptive_grid(trajs)
        seqs = [self._state_sequence(tr) for tr in trajs]
        seqs = [s for s in seqs if len(s) >= 2]
        n = self.n_states
        od = np.zeros((n, n), dtype=float)
        init_counts = np.zeros(n, dtype=float)
        trans = np.zeros((n, n), dtype=float)
        length_counts: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        maxdist_counts: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))

        for seq in seqs:
            start, end = seq[0], seq[-1]
            init_counts[start] += 1
            od[start, end] += 1
            length_counts[start][min(len(seq), self.max_len)] += 1
            max_step = 0.0
            for a, b in zip(seq[:-1], seq[1:]):
                trans[a, b] += 1.0
                max_step = max(max_step, haversine_m(self._state_center(a), self._state_center(b)))
            # 100-meter bins are close to the paper's discretized coordinate-domain spirit.
            maxdist_counts[start][int(round(max_step / 100.0))] += 1

        self.od_prob = normalize(od + self._lap(1.0 / max(self.eps_trip, 1e-12), size=od.shape)).reshape(n, n)
        self.init_prob = normalize(init_counts + self._lap(1.0 / max(self.eps_trip, 1e-12), size=init_counts.shape))
        self.trans_prob = np.zeros_like(trans)
        markov_noise_scale = 1.0 / max(self.eps_markov, 1e-12)
        noisy_trans = np.maximum(trans + self._lap(markov_noise_scale, size=trans.shape), 0.0)
        if self.transition_prune_scale > 0:
            noisy_trans[noisy_trans < self.transition_prune_scale * markov_noise_scale] = 0.0
        for i in range(n):
            row = noisy_trans[i]
            self.trans_prob[i] = normalize(row) if row.sum() > 0 else np.ones(n) / n

        self.length_prob: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self.maxdist_prob: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        global_lengths = defaultdict(float)
        global_max = defaultdict(float)
        for s, dct in length_counts.items():
            for k, v in dct.items():
                global_lengths[k] += v
            keys = np.array(sorted(dct), dtype=int)
            vals = np.array([dct[k] for k in keys], dtype=float)
            self.length_prob[s] = (keys, normalize(vals + self._lap(1.0 / max(self.eps_length, 1e-12), size=vals.shape)))
        for s, dct in maxdist_counts.items():
            for k, v in dct.items():
                global_max[k] += v
            keys = np.array(sorted(dct), dtype=int)
            vals = np.array([dct[k] for k in keys], dtype=float)
            self.maxdist_prob[s] = (keys, normalize(vals + self._lap(1.0 / max(self.eps_maxdist, 1e-12), size=vals.shape)))
        g_len_keys = np.array(sorted(global_lengths), dtype=int)
        g_len_vals = np.array([global_lengths[k] for k in g_len_keys], dtype=float)
        g_max_keys = np.array(sorted(global_max), dtype=int)
        g_max_vals = np.array([global_max[k] for k in g_max_keys], dtype=float)
        self.global_length = (g_len_keys, normalize(g_len_vals + self._lap(1.0 / max(self.eps_length, 1e-12), size=g_len_vals.shape)))
        self.global_maxdist = (g_max_keys, normalize(g_max_vals + self._lap(1.0 / max(self.eps_maxdist, 1e-12), size=g_max_vals.shape)))
        self.predecessors = [np.flatnonzero(trans[:, i] > 0) for i in range(n)]
        self.successors = [np.flatnonzero(trans[i] > 0) for i in range(n)]
        self.state_centers_arr = np.asarray([self._state_center(i) for i in range(n)], dtype=float)

    def _decode_sequence(self, seq: list[int]) -> np.ndarray:
        coords: list[list[float]] = []
        lat_min, lat_max, lon_min, lon_max = self.bbox
        for i, s in enumerate(seq):
            if self.intermediate_points > 0 and i > 0:
                prev = self._state_center(seq[i - 1])
                cur = self._state_center(s)
                for k in range(1, self.intermediate_points + 1):
                    a = k / (self.intermediate_points + 1)
                    lat = prev[0] + a * (cur[0] - prev[0])
                    lon = prev[1] + a * (cur[1] - prev[1])
                    if self.coord_sigma > 0:
                        lat += float(self.rng.normal(0.0, self.coord_sigma * 0.5))
                        lon += float(self.rng.normal(0.0, self.coord_sigma * 0.5))
                    coords.append([float(np.clip(lat, lat_min, lat_max)), float(np.clip(lon, lon_min, lon_max))])
            lat, lon = self._random_in_state(s)
            if self.coord_sigma > 0:
                lat += float(self.rng.normal(0.0, self.coord_sigma))
                lon += float(self.rng.normal(0.0, self.coord_sigma))
            coords.append([float(np.clip(lat, lat_min, lat_max)), float(np.clip(lon, lon_min, lon_max))])
        return np.asarray(coords, dtype=float)

    def _sample_length(self, start: int) -> int:
        keys, prob = self.length_prob.get(start, self.global_length)
        return int(self.rng.choice(keys, p=prob))

    def _sample_maxdist(self, start: int) -> float:
        keys, prob = self.maxdist_prob.get(start, self.global_maxdist)
        return max(self.maxdist_floor_m, float(self.rng.choice(keys, p=prob)) * 100.0)

    def _sample_od(self) -> tuple[int, int]:
        flat = normalize(self.od_prob.ravel())
        idx = int(self.rng.choice(np.arange(flat.size), p=flat))
        return idx // self.n_states, idx % self.n_states

    def generate(self, n: int) -> list[np.ndarray]:
        out = []
        all_states = np.arange(self.n_states)
        for i in range(n):
            if (i + 1) % max(1, n // 10) == 0:
                print(f"[generate] {i + 1}/{n}", flush=True)
            if self.generator_variant == "markov-init":
                start = int(self.rng.choice(all_states, p=normalize(self.init_prob)))
                end = start
                keys, prob = self.global_length
                length = int(self.rng.choice(keys, p=prob))
            else:
                start, end = self._sample_od()
                length = self._sample_length(start)
            length = max(2, min(self.max_len, length))
            max_d = self._sample_maxdist(start)
            seq = [start]
            cur = start
            for _ in range(max(0, length - 2)):
                row = self.trans_prob[cur].copy()
                if not self.disable_maxdist_constraint:
                    cur_center = self.state_centers_arr[cur]
                    distances = np.array([haversine_m(cur_center, c) for c in self.state_centers_arr], dtype=float)
                    row[distances > max_d] = 0.0
                if row.sum() <= 0:
                    nxt = cur
                else:
                    nxt = int(self.rng.choice(all_states, p=normalize(row)))
                seq.append(nxt)
                cur = nxt
            if self.generator_variant != "markov-init":
                seq.append(end)
            elif len(seq) < length:
                seq.append(cur)
            if self.generator_variant != "markov-init" and len(seq) >= 3:
                preds = self.predecessors[seq[1]]
                succs = self.successors[seq[-2]]
                if len(preds) > 0:
                    seq[0] = int(self.rng.choice(preds))
                if len(succs) > 0:
                    seq[-1] = int(self.rng.choice(succs))
            out.append(self._decode_sequence(seq))
        return out

    def project(self, trajs: list[np.ndarray]) -> list[np.ndarray]:
        projected = []
        for tr in trajs:
            seq = self._state_sequence(tr)
            projected.append(np.asarray([[self._state_center(s)[0], self._state_center(s)[1]] for s in seq], dtype=float))
        return projected


class TemplateFeatureModel:
    """Diagnostic feature-template sampler for original-metric recovery.

    The published DP-Std paper describes extracting feature distributions and
    then sampling synthetic trajectories from the resulting mobility model. The
    text does not expose author code. This diagnostic mode measures how much of
    the original Table-3 scale can be recovered when the released feature family
    includes coarse trajectory templates in addition to marginal OD/length
    summaries.
    """

    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        epsilon: float,
        grid: int = 6,
        max_len: int = 100,
        no_noise: bool = False,
        noise_multiplier: float = 1.0,
        point_mode: str = "cell-pool",
        seed: int = 20260707,
    ):
        self.bbox = bbox
        self.epsilon = float(epsilon)
        self.grid = int(grid)
        self.max_len = int(max_len) if int(max_len) > 0 else 10**9
        self.no_noise = bool(no_noise)
        self.noise_multiplier = float(noise_multiplier)
        self.point_mode = point_mode
        self.rng = np.random.default_rng(seed)

    def _lap(self, size=None):
        if self.no_noise:
            return np.zeros(size if size is not None else (), dtype=float)
        return self.rng.laplace(0.0, self.noise_multiplier / max(self.epsilon, 1e-12), size=size)

    def _raw_cells(self, tr: np.ndarray) -> list[int]:
        clipped = tr if self.max_len >= 10**9 else tr[: self.max_len]
        return [cell_id(p, self.bbox, self.grid) for p in clipped]

    def fit(self, trajs: list[np.ndarray]) -> None:
        self.cell_points: dict[int, list[list[float]]] = defaultdict(list)
        self.template_trajs: dict[tuple[int, ...], list[np.ndarray]] = defaultdict(list)
        counts: Counter[tuple[int, ...]] = Counter()
        for tr in trajs:
            clipped = tr if self.max_len >= 10**9 else tr[: self.max_len]
            ids = self._raw_cells(tr)
            if len(ids) < 2:
                continue
            counts[tuple(ids)] += 1
            self.template_trajs[tuple(ids)].append(np.asarray(clipped, dtype=float))
            for p in clipped:
                self.cell_points[cell_id(p, self.bbox, self.grid)].append([float(p[0]), float(p[1])])

        templates = list(counts.keys())
        vals = np.asarray([counts[t] for t in templates], dtype=float)
        vals = np.maximum(vals + self._lap(size=vals.shape), 0.0)
        keep = vals > 0
        if not np.any(keep):
            keep = np.ones_like(vals, dtype=bool)
            vals = np.ones_like(vals, dtype=float)
        self.templates = [templates[i] for i in np.where(keep)[0]]
        self.template_prob = normalize(vals[keep])

    def _cell_center(self, z: int) -> list[float]:
        lat_min, lat_max, lon_min, lon_max = self.bbox
        r, c = divmod(int(z), self.grid)
        return [
            float(lat_min + (r + 0.5) * (lat_max - lat_min) / self.grid),
            float(lon_min + (c + 0.5) * (lon_max - lon_min) / self.grid),
        ]

    def _sample_point(self, z: int) -> list[float]:
        if self.point_mode == "center":
            return self._cell_center(z)
        pts = self.cell_points.get(int(z), [])
        if not pts:
            return self._cell_center(z)
        p = pts[int(self.rng.integers(0, len(pts)))]
        return [float(p[0]), float(p[1])]

    def generate(self, n: int) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for i in range(n):
            if (i + 1) % max(1, n // 10) == 0:
                print(f"[generate-template] {i + 1}/{n}", flush=True)
            idx = int(self.rng.choice(np.arange(len(self.templates)), p=self.template_prob))
            seq = self.templates[idx]
            if self.point_mode == "trajectory-pool":
                pool = self.template_trajs.get(seq, [])
                if pool:
                    out.append(np.asarray(pool[int(self.rng.integers(0, len(pool)))], dtype=float).copy())
                    continue
            out.append(np.asarray([self._sample_point(z) for z in seq], dtype=float))
        return out

    def project(self, trajs: list[np.ndarray]) -> list[np.ndarray]:
        return [
            np.asarray(
                [self._cell_center(z) for z in self._raw_cells(tr)],
                dtype=float,
            )
            for tr in trajs
        ]


def comparison(metrics: dict[str, float], data: str, epsilon: float) -> dict[str, dict[str, float | None]]:
    target_key = "GeoLife_epsilon_0.5_DPStd" if data == "geolife" else "Porto_epsilon_0.5_DPStd"
    target = REPORTED[target_key] if abs(epsilon - 0.5) < 1e-12 else {}
    return {
        k: {
            "observed": float(v),
            "paper_target_reference": float(target[k]) if k in target else None,
            "ratio_observed_over_target": float(v / target[k]) if k in target and target[k] else None,
        }
        for k, v in metrics.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", choices=["geolife", "porto"], default="geolife")
    ap.add_argument("--bbox-mode", choices=["paper", "current"], default="paper")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--n-gen", type=int, default=1000)
    ap.add_argument("--epsilon", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=20260707)
    ap.add_argument("--query-count", type=int, default=500)
    ap.add_argument("--query-mode", choices=["set", "sequence"], default="set")
    ap.add_argument("--grid-size", type=int, default=7)
    ap.add_argument("--theta", type=float, default=10.0)
    ap.add_argument("--max-subcells", type=int, default=8)
    ap.add_argument("--maxdist-floor-m", type=float, default=50.0)
    ap.add_argument("--max-len", type=int, default=100, help="Maximum points per trajectory for the generator; use 0 for full length.")
    ap.add_argument("--disable-maxdist-constraint", action="store_true")
    ap.add_argument("--point-mode", choices=["uniform", "center"], default="uniform", help="Native DP-Std coordinate decoding inside adaptive cells.")
    ap.add_argument("--generator-variant", choices=["od-bridge", "markov-init"], default="od-bridge")
    ap.add_argument("--intermediate-points", type=int, default=0)
    ap.add_argument("--coord-sigma", type=float, default=0.0)
    ap.add_argument("--transition-prune-scale", type=float, default=0.0, help="Post-process noisy DP transition entries below scale * Laplace scale to zero.")
    ap.add_argument("--noise-multiplier", type=float, default=1.0)
    ap.add_argument("--budget-split", choices=["equal", "diagnostic-weighted"], default="equal")
    ap.add_argument("--time-normalize-3s", action="store_true", help="Use the DP-Std GeoLife convention that inter-point distance is normalized to 3 seconds when timestamps are available.")
    ap.add_argument("--fp-max-len", type=int, default=6)
    ap.add_argument("--fp-support-mode", choices=["occurrence", "trajectory"], default="occurrence")
    ap.add_argument("--eval-real-projected", action="store_true")
    ap.add_argument("--eval-real-clipped", action="store_true", help="Evaluate real trajectories after the same max-len cut used by DP-Std feature extraction.")
    ap.add_argument("--no-noise", action="store_true")
    ap.add_argument("--save-synthetic", type=Path)
    ap.add_argument("--generation-mode", choices=["paper-structured", "template-feature"], default="paper-structured")
    ap.add_argument("--template-point-mode", choices=["cell-pool", "center", "trajectory-pool"], default="cell-pool")
    ap.add_argument("--out", type=Path, default=CHECK_DIR / "dpstd_paper_protocol_reproduction.json")
    args = ap.parse_args()

    np.random.seed(args.seed)
    limit = None if args.limit <= 0 else args.limit
    print(f"[load] data={args.data} bbox_mode={args.bbox_mode} limit={limit}", flush=True)
    real, bbox = load_dataset(args.data, args.bbox_mode, limit, include_time=args.time_normalize_3s)
    if len(real) < 2:
        raise RuntimeError("not enough trajectories loaded")
    n_gen = min(args.n_gen, len(real)) if args.n_gen > 0 else len(real)
    real_eval = real[:n_gen]
    print(f"[fit] n_real={len(real)} n_gen={n_gen} epsilon={args.epsilon} grid={args.grid_size}", flush=True)
    if args.generation_mode == "template-feature":
        model = TemplateFeatureModel(
            bbox=bbox,
            epsilon=args.epsilon,
            grid=6,
            max_len=args.max_len,
            noise_multiplier=args.noise_multiplier,
            point_mode=args.template_point_mode,
            no_noise=args.no_noise,
            seed=args.seed,
        )
    else:
        model = PaperDPStdModel(
            bbox=bbox,
            epsilon=args.epsilon,
            grid_size=args.grid_size,
            theta=args.theta,
            max_subcells=args.max_subcells,
        maxdist_floor_m=args.maxdist_floor_m,
            max_len=args.max_len,
            disable_maxdist_constraint=args.disable_maxdist_constraint,
            point_mode=args.point_mode,
            generator_variant=args.generator_variant,
            intermediate_points=args.intermediate_points,
            coord_sigma=args.coord_sigma,
            transition_prune_scale=args.transition_prune_scale,
            noise_multiplier=args.noise_multiplier,
            no_noise=args.no_noise,
            budget_split=args.budget_split,
            time_normalize_3s=args.time_normalize_3s,
            seed=args.seed,
        )
    model.fit(real)
    if args.generation_mode == "template-feature":
        print(f"[fit] templates={len(model.templates)}", flush=True)
    else:
        print(f"[fit] states={model.n_states} avg_sub={np.mean(model.subdivisions):.3f}", flush=True)
    syn = model.generate(n_gen)
    if args.eval_real_clipped:
        print(f"[eval] clipping real trajectories to max_len={args.max_len}", flush=True)
        real_eval = clip_trajs(real_eval, args.max_len)
    if args.eval_real_projected:
        print("[eval] projecting real trajectories to DP-Std adaptive-grid centers", flush=True)
        real_eval = model.project(real_eval)
    if args.save_synthetic:
        args.save_synthetic.parent.mkdir(parents=True, exist_ok=True)
        with args.save_synthetic.open("w", encoding="utf-8") as f:
            json.dump([tr.tolist() for tr in syn], f)
    print("[eval] original paper metric family", flush=True)
    metrics = evaluate(
        real_eval,
        syn,
        bbox,
        query_count=args.query_count,
        fp_max_len=args.fp_max_len,
        fp_support_mode=args.fp_support_mode,
        query_mode=args.query_mode,
        time_normalize_3s=args.time_normalize_3s,
    )
    protocol = vars(args).copy()
    protocol["out"] = str(protocol["out"])
    if protocol.get("save_synthetic"):
        protocol["save_synthetic"] = str(protocol["save_synthetic"])
    payload = {
        "status": "paper-structured DP-Std reproduction attempt; no author code found/certified",
        "reported_values": REPORTED,
        "protocol": protocol
        | {
            "bbox": list(bbox),
            "n_real_loaded": len(real),
            "n_eval": len(real_eval),
            "generation_mode": args.generation_mode,
            "states": int(getattr(model, "n_states", 0)),
            "avg_subdivision": float(np.mean(getattr(model, "subdivisions", [0]))),
            "epsilon_ledger": {
                "adaptive_grid": getattr(model, "eps_grid", None),
                "max_distance_distribution": getattr(model, "eps_maxdist", None),
                "length_distribution": getattr(model, "eps_length", None),
                "trip_distribution": getattr(model, "eps_trip", None),
                "markov_transition": getattr(model, "eps_markov", None),
                "template_histogram": args.epsilon if args.generation_mode == "template-feature" else None,
                "budget_split": getattr(model, "budget_split", None),
                "time_normalize_3s": args.time_normalize_3s,
            },
        },
        "metrics": metrics,
        "comparison_to_paper_target": comparison(metrics, args.data, args.epsilon),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

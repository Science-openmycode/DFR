"""
DPTraj-PM Final Implementation
===============================
Local paper-based DPTraj-PM-style reimplementation of Wang & Kankanhalli
(2024), arXiv 2404.14106. This file is not author-code-certified; see
public_release/check/BASELINE_REPRODUCTION_AUDIT.md.

Pipeline:
  Step 1: Space discretization (uniform grid or RNDV Voronoi)
  Step 2: Height-(m+2) prefix tree with decremental Laplace noise (eps/2 budget)
  Step 3: m-order Markov frequency matrix with Laplace noise (eps/2 budget)
  Step 4: Trajectory synthesis (prefix tree init + Markov continuation)

Parameters:
  m=2 (2nd-order Markov), K=7, epsilon=1.0, 5 reps
  Prefix tree height h=m+2=4
  Budget: 50% prefix tree (decaying per level), 50% Markov
"""

import numpy as np
import math
import json
import os
import time
import csv
import requests
from collections import defaultdict
from scipy.ndimage import gaussian_filter

FILE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.normpath(os.path.join(
    FILE_DIR, '..', '..', '..', '..', '..', 'semdp_traj_paper', 'experiments', 'datasets'))

EPSILON = 1.0
K = 7
M = 2
H = M + 2
N_REPS = 5
M_MAX = 100
RANDOM_SEED = 42

EPS_LEN = 0.05
G = 0.5
EPS_P = G * (EPSILON - EPS_LEN)
EPS_M = (1 - G) * (EPSILON - EPS_LEN)

PFX_BUDGET_PROP = [0.30, 0.25, 0.25, 0.20]
SENSITIVITY = 1.0
MARKOV_SENSITIVITY = M_MAX - 1

BBOXES = {
    'beijing': {'lat_min': 39.75, 'lat_max': 40.15, 'lon_min': 116.10, 'lon_max': 116.65},
    'porto':   {'lat_min': 41.10, 'lat_max': 41.20, 'lon_min': -8.70, 'lon_max': -8.55},
    'austin':  {'lat_min': 30.05, 'lat_max': 30.55, 'lon_min': -98.00, 'lon_max': -97.50},
    'london':  {'lat_min': 51.30, 'lat_max': 51.70, 'lon_min': -0.50, 'lon_max': 0.20},
}

# OSM Overpass API endpoints for road-network-aware RNDV
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_HEADERS = {'User-Agent': 'opencode/1.0'}
DENSITY_GRID_SIZE = 50
GAUSSIAN_SIGMA = 3.0


def haversine_km(lat1, lon1, lat2, lon2):
    RE = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return RE * c


def query_osm_highways(bbox_dict, timeout=180):
    bbox_str = (f"{bbox_dict['lat_min']},{bbox_dict['lon_min']},"
                f"{bbox_dict['lat_max']},{bbox_dict['lon_max']}")
    query = f'[out:json][timeout:180];(way["highway"]({bbox_str}););out geom;'
    for url in OVERPASS_URLS:
        for method in ['POST', 'GET']:
            try:
                if method == 'GET':
                    resp = requests.get(url, params={'data': query},
                                        headers=OVERPASS_HEADERS, timeout=timeout)
                else:
                    resp = requests.post(url, data={'data': query},
                                         headers=OVERPASS_HEADERS, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    elements = data.get('elements', [])
                    ways = [e for e in elements
                            if e.get('type') == 'way' and 'geometry' in e]
                    if len(ways) > 0:
                        return ways, url
            except Exception:
                continue
    return None, None


def compute_road_density_grid(ways, bbox_dict, grid_size=DENSITY_GRID_SIZE):
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    density = np.zeros((grid_size, grid_size), dtype=np.float64)
    for way in ways:
        geom = way.get('geometry', [])
        if len(geom) < 2:
            continue
        for i in range(len(geom) - 1):
            p1, p2 = geom[i], geom[i + 1]
            lat1, lon1 = p1['lat'], p1['lon']
            lat2, lon2 = p2['lat'], p2['lon']
            seg_len_km = haversine_km(lat1, lon1, lat2, lon2)
            check_points = [(lat1, lon1), (lat2, lon2),
                            ((lat1 + lat2) / 2, (lon1 + lon2) / 2)]
            for lat_c, lon_c in check_points:
                if not (lat_min <= lat_c <= lat_max and
                        lon_min <= lon_c <= lon_max):
                    continue
                row = int((lat_c - lat_min) / lat_span * grid_size)
                col = int((lon_c - lon_min) / lon_span * grid_size)
                row = min(max(row, 0), grid_size - 1)
                col = min(max(col, 0), grid_size - 1)
                density[row, col] += seg_len_km / 3.0
    return density


def select_centers_rndv(density_smooth, bbox_dict, K_cells=K):
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    gs = density_smooth.shape[0]
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    flat = density_smooth.ravel()
    sorted_indices = np.argsort(flat)[::-1]
    centers = []
    used_cells = set()
    cell_diag_km = haversine_km(lat_min, lon_min,
                                 lat_min + lat_span / gs,
                                 lon_min + lon_span / gs)
    for idx in sorted_indices:
        if len(centers) >= K_cells:
            break
        if idx in used_cells:
            continue
        row = idx // gs
        col = idx % gs
        lat = lat_min + (row + 0.5) * lat_span / gs
        lon = lon_min + (col + 0.5) * lon_span / gs
        too_close = any(
            haversine_km(lat, lon, c[0], c[1]) < cell_diag_km * 1.5
            for c in centers)
        if too_close:
            used_cells.add(idx)
            continue
        centers.append([float(lat), float(lon)])
        used_cells.add(idx)
    if len(centers) < K_cells:
        for idx in sorted_indices:
            if len(centers) >= K_cells:
                break
            row = idx // gs
            col = idx % gs
            lat = lat_min + (row + 0.5) * lat_span / gs
            lon = lon_min + (col + 0.5) * lon_span / gs
            already = any(haversine_km(lat, lon, c[0], c[1]) < 0.5
                          for c in centers)
            if not already:
                centers.append([float(lat), float(lon)])
    return np.array(centers)


def fallback_rndv_centers(bbox, K_cells=K):
    """Farthest-first sampling from a fine grid — OSM_FAILED_FALLBACK."""
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    G = int(math.ceil(math.sqrt(K_cells * 4)))
    lat_step = (lat_max - lat_min) / G
    lon_step = (lon_max - lon_min) / G
    pts = []
    for i in range(G):
        for j in range(G):
            lat = lat_min + (i + 0.5) * lat_step
            lon = lon_min + (j + 0.5) * lon_step
            pts.append(np.array([lat, lon]))
    pts = np.array(pts)
    center_pt = np.array([(lat_min + lat_max) / 2, (lon_min + lon_max) / 2])
    first = int(np.argmin(np.linalg.norm(pts - center_pt, axis=1)))
    selected = [pts[first]]
    sel_idx = {first}
    while len(selected) < K_cells:
        sel_arr = np.array(selected)
        best_idx, best_min = -1, -float('inf')
        for i, p in enumerate(pts):
            if i in sel_idx:
                continue
            d = np.min(np.linalg.norm(sel_arr - p, axis=1))
            if d > best_min:
                best_min, best_idx = d, i
        if best_idx < 0:
            break
        selected.append(pts[best_idx])
        sel_idx.add(best_idx)
    return np.array(selected)

###############################################################################
# DATA LOADING
###############################################################################

def load_geolife_beijing(data_path, max_trajs=200, bbox=None):
    trajectories = []
    count = 0
    for root, dirs, files in os.walk(data_path):
        for fname in files:
            if count >= max_trajs:
                break
            if not fname.endswith('.plt'):
                continue
            try:
                with open(os.path.join(root, fname), 'r') as f:
                    lines = f.readlines()
            except Exception:
                continue
            points = []
            for line in lines[6:]:
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[0] != '':
                    try:
                        lat = float(parts[0])
                        lon = float(parts[1])
                        if bbox is None or (
                            bbox['lat_min'] <= lat <= bbox['lat_max'] and
                            bbox['lon_min'] <= lon <= bbox['lon_max']):
                            points.append([lat, lon])
                    except ValueError:
                        pass
            if len(points) >= 2:
                trajectories.append(np.array(points))
                count += 1
    return trajectories


def load_porto_csv(data_path, max_trajs=200, bbox=None):
    trajectories = []
    count = 0
    with open(data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if count >= max_trajs:
                break
            try:
                poly = json.loads(row['POLYLINE'])
            except Exception:
                continue
            points = []
            for pt in poly:
                lon, lat = float(pt[0]), float(pt[1])
                if bbox is None or (
                    bbox['lat_min'] <= lat <= bbox['lat_max'] and
                    bbox['lon_min'] <= lon <= bbox['lon_max']):
                    points.append([lat, lon])
            if len(points) >= 2:
                trajectories.append(np.array(points))
                count += 1
    return trajectories


def load_npz_trajs(filepath, max_trajs=200):
    data = np.load(filepath, allow_pickle=True)
    trajs = data['trajectories']
    trajectories = []
    for t in trajs:
        if len(trajectories) >= max_trajs:
            break
        if len(t) >= 2:
            trajectories.append(np.array(t))
    return trajectories


###############################################################################
# STEP 1: SPACE DISCRETIZATION
###############################################################################

def compute_grid_layout(K_cells):
    rows = max(1, int(math.floor(math.sqrt(K_cells))))
    cols = max(1, int(math.ceil(K_cells / rows)))
    return rows, cols


def get_uniform_centers(bbox, K_cells):
    rows, cols = compute_grid_layout(K_cells)
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_step = (lat_max - lat_min) / rows
    lon_step = (lon_max - lon_min) / cols
    centers = []
    for i in range(rows):
        for j in range(cols):
            if len(centers) >= K_cells:
                break
            lat = lat_min + (i + 0.5) * lat_step
            lon = lon_min + (j + 0.5) * lon_step
            centers.append(np.array([lat, lon]))
    return np.array(centers)



def map_point_to_cell(point, centers):
    dists = np.linalg.norm(centers - point, axis=1)
    return int(np.argmin(dists))


###############################################################################
# STEP 2: NOISY PREFIX TREE (eps/2 budget, decremental per-level allocation)
###############################################################################

class NoisyPrefixTree:
    """
    Height-(m+2) prefix tree with decremental Laplace noise.

    Levels (h=4 for m=2):
      level 0: virtual root (|Dc| = total trajectory count)
      level 1: single-cell count prefixes
      level 2: 2-cell count prefixes
      level 3: 3-cell count prefixes

    Budget per level: budget_props[i] * eps_p
      root=30%, lvl1=25%, lvl2=25%, lvl3=20% of eps_p

    Sensitivity = 1 (adding/removing one trajectory changes each count by <=1)
    """

    def __init__(self, eps_p, h, budget_props, N):
        self.eps_p = eps_p
        self.h = h
        self.budget_props = budget_props
        self.N = N
        self.root_noisy = 0.0
        self.noisy_counts = [{} for _ in range(h)]

    def _laplace(self, eps, size=1):
        scale = SENSITIVITY / max(eps, 1e-10)
        return np.random.laplace(0, scale, size)

    def build(self, cell_trajs, total_count):
        h = self.h

        # Count all prefixes in real data (levels 1..h-1)
        prefix_counts = [defaultdict(int) for _ in range(h)]
        for traj in cell_trajs:
            for d in range(1, h):
                if d <= len(traj):
                    prefix = tuple(traj[:d])
                    prefix_counts[d][prefix] += 1

        # Level 0 (root): add Laplace noise to total trajectory count
        eps_root = self.budget_props[0] * self.eps_p
        self.root_noisy = max(1.0, total_count + self._laplace(eps_root)[0])

        # Levels 1..h-1: add Laplace noise to prefix counts
        # Each trajectory contributes to exactly ONE node per level (disjoint subsets).
        # Under parallel composition, per-node Laplace(b) is equivalent to one histogram
        # query with noise b. Total privacy cost per level = 1/b, not K * 1/b.
        # See: Dwork & Roth (2014), Theorem 3.5 (Parallel Composition)
        for level in range(1, h):
            eps_level = self.budget_props[level] * self.eps_p
            b_level = SENSITIVITY / eps_level
            scaled = {}
            for prefix, cnt in prefix_counts[level].items():
                noisy = cnt + np.random.laplace(0, b_level)
                if noisy >= 1.0:
                    scaled[prefix] = max(1.0, noisy)
            self.noisy_counts[level] = scaled

        # Top-down consistency: parent count = sum of children counts
        # Level 1: scale so sum matches root_noisy
        if self.noisy_counts[1]:
            l1_sum = sum(self.noisy_counts[1].values())
            if l1_sum > 0:
                for prefix in list(self.noisy_counts[1].keys()):
                    self.noisy_counts[1][prefix] *= self.root_noisy / l1_sum
        else:
            for i in range(self.N):
                self.noisy_counts[1][(i,)] = self.root_noisy / self.N

        # Level 2+: group by parent prefix and scale children
        for level in range(2, h):
            if not self.noisy_counts[level]:
                continue
            by_parent = defaultdict(list)
            for prefix in self.noisy_counts[level]:
                parent = prefix[:-1]
                by_parent[parent].append(prefix)

            scaled = {}
            for parent, children in by_parent.items():
                parent_cnt = self.noisy_counts[level - 1].get(parent, 0.0)
                child_sum = sum(self.noisy_counts[level][c] for c in children)
                if child_sum > 0 and parent_cnt > 0:
                    for c in children:
                        scaled[c] = self.noisy_counts[level][c] * parent_cnt / child_sum
                elif parent_cnt > 0:
                    for i, c in enumerate(children):
                        scaled[c] = parent_cnt / len(children)
                else:
                    for c in children:
                        scaled[c] = self.noisy_counts[level][c]
            self.noisy_counts[level] = scaled

        return self.noisy_counts

    def sample_initial_segment(self, max_len=None):
        """Sample a path from the prefix tree down to max_len cells."""
        if max_len is None:
            max_len = self.h - 1

        prefix = []
        for level in range(1, min(max_len + 1, self.h)):
            candidates = []
            weights = []
            for p, cnt in self.noisy_counts[level].items():
                if len(p) >= len(prefix) + 1 and list(p[:len(prefix)]) == prefix:
                    candidates.append(p)
                    weights.append(cnt)

            if not candidates or sum(weights) <= 0:
                break

            weights = np.array(weights, dtype=float)
            weights /= weights.sum()
            idx = np.random.choice(len(candidates), p=weights)
            prefix = list(candidates[idx])

        return prefix


###############################################################################
# STEP 3: NOISY M-ORDER MARKOV FREQUENCY MATRIX (eps/2 budget)
###############################################################################

class NoisyMarkovProcess:
    """
    m-order Markov process: P(cell_{t+1} | cell_t, ..., cell_{t-m+1})

    Frequency matrix F[ngram][next] -> Laplace noise -> normalize to probabilities.
    Sensitivity = 1 (each trajectory contributes 1 to each transition count).
    """

    def __init__(self, eps_m, m, N):
        self.eps_m = eps_m
        self.m = m
        self.N = N
        self.transition_probs = None
        self.mgram_to_idx = {}

    def build(self, cell_trajs):
        N = self.N
        m = self.m

        # Count (m+1)-grams: freq[mgram][next_cell]
        freq = defaultdict(lambda: np.zeros(N + 1))

        for traj in cell_trajs:
            L = len(traj)
            for start in range(L - m):
                mgram = tuple(traj[start:start + m])
                if start + m < L:
                    next_cell = traj[start + m]
                    freq[mgram][next_cell] += 1.0
                else:
                    freq[mgram][N] += 1.0
            # Trajectory end: final m-gram transitions to terminating symbol
            if L >= m:
                for start in range(max(0, L - m), L):
                    if start >= 0 and start <= L - m:
                        mgram = tuple(traj[start:start + m])
                        if start + m >= L:
                            freq[mgram][N] += 1.0

        # Generate all possible m-grams (all N^m combinations)
        all_mgrams = []
        def gen(prefix, depth):
            if depth == m:
                all_mgrams.append(tuple(prefix))
                return
            for ci in range(N):
                gen(prefix + [ci], depth + 1)
        gen([], 0)

        num_mgrams = len(all_mgrams)
        self.transition_probs = np.zeros((num_mgrams, N + 1))
        self.mgram_to_idx = {mg: i for i, mg in enumerate(all_mgrams)}

        # Whole Markov matrix as ONE query — generate all noise at once
        # Sensitivity = m_max-1: one trajectory contributes ≤ m_max-1 transitions
        b_markov = MARKOV_SENSITIVITY / self.eps_m
        total_elements = sum(len(row) for row in freq.values())
        all_noise = np.random.laplace(0.0, b_markov, total_elements)

        offset = 0
        for mgram, row in freq.items():
            if mgram in self.mgram_to_idx:
                idx = self.mgram_to_idx[mgram]
                n = len(row)
                noisy_row = np.maximum(0.0, row + all_noise[offset:offset+n])
                offset += n
                row_sum = noisy_row.sum()
                if row_sum > 0:
                    self.transition_probs[idx] = noisy_row / row_sum
                else:
                    self.transition_probs[idx] = np.ones(N + 1) / (N + 1)

        # Fill unobserved m-grams with uniform
        for i in range(num_mgrams):
            if self.transition_probs[i].sum() < 1e-10:
                self.transition_probs[i] = np.ones(N + 1) / (N + 1)

        return self.transition_probs

    def sample_next(self, mgram):
        """Sample next cell index given an m-gram context."""
        if mgram not in self.mgram_to_idx:
            return np.random.randint(0, self.N)
        idx = self.mgram_to_idx[mgram]
        probs = self.transition_probs[idx].copy()
        probs = probs / max(probs.sum(), 1e-10)
        return int(np.random.choice(self.N + 1, p=probs))


###############################################################################
# STEP 4: TRAJECTORY SYNTHESIS (prefix tree init + Markov continuation)
###############################################################################

class DPTrajPM:
    """DPTraj-PM with uniform grid discretization."""

    def __init__(self, epsilon, bbox, K_cells=7, m=2, pfx_budget_props=None):
        self.epsilon = epsilon
        self.bbox = bbox
        self.K = K_cells
        self.m = m
        self.h = m + 2
        self.pfx_budget_props = pfx_budget_props or [0.30, 0.25, 0.25, 0.20]
        self.eps_p = G * max(epsilon - EPS_LEN, 0)
        self.eps_m = (1 - G) * max(epsilon - EPS_LEN, 0)
        self.eps_len = min(EPS_LEN, epsilon)

        self.centers = get_uniform_centers(bbox, K_cells)
        self.N = len(self.centers)
        self.prefix_tree = None
        self.markov = None
        self._traj_lengths = None
        self._len_dist = None
        self._len_bins = None
        self._n_trajs = 0

    def _discretize(self, trajectories):
        cell_trajs = []
        for traj in trajectories:
            cells = [map_point_to_cell(pt, self.centers) for pt in traj[:M_MAX]]
            cell_trajs.append(cells)
        return cell_trajs

    def fit(self, trajectories):
        self._n_trajs = len(trajectories)
        self._traj_lengths = [min(len(t), M_MAX) for t in trajectories]
        cell_trajs = self._discretize(trajectories)

        # Build noisy length distribution (DP: Laplace, Δ=1, b=1/eps_len)
        len_hist = np.zeros(M_MAX + 1)
        for L in self._traj_lengths:
            if 2 <= L <= M_MAX:
                len_hist[L] += 1
        len_hist = len_hist[2:M_MAX + 1]
        if self.eps_len > 0:
            len_noisy = len_hist + np.random.laplace(0, 1.0 / self.eps_len, len(len_hist))
            len_noisy = np.maximum(len_noisy, 0)
        else:
            len_noisy = len_hist.astype(float)
        s = len_noisy.sum()
        self._len_dist = len_noisy / s if s > 0 else np.ones(len(len_hist)) / len(len_hist)
        self._len_bins = np.arange(2, M_MAX + 1)

        self.prefix_tree = NoisyPrefixTree(self.eps_p, self.h, self.pfx_budget_props, self.N)
        self.prefix_tree.build(cell_trajs, self._n_trajs)

        self.markov = NoisyMarkovProcess(self.eps_m, self.m, self.N)
        self.markov.build(cell_trajs)

    def generate(self, n_trajs=None):
        n = n_trajs if n_trajs is not None else self._n_trajs
        synthetic = []
        centers = self.centers
        bbox = self.bbox
        coord_sigma = 0.01

        for _ in range(n):
            length = int(np.random.choice(self._len_bins, p=self._len_dist)) if self._len_dist is not None else 20
            length = max(self.m + 1, min(length, M_MAX))

            # Phase A: Initialize from prefix tree
            init_seg = self.prefix_tree.sample_initial_segment(max_len=self.h - 1)
            if len(init_seg) < self.m:
                while len(init_seg) < self.m:
                    init_seg.append(np.random.randint(0, self.N))

            path = list(init_seg)

            # Phase B: Continue via m-order Markov chain
            while len(path) < length:
                mgram = tuple(path[-self.m:])
                next_cell = self.markov.sample_next(mgram)
                if next_cell >= self.N:
                    break
                path.append(int(next_cell))

            # Cell path -> GPS coordinates with Gaussian noise
            coords = []
            for cell_id in path:
                if 0 <= cell_id < len(centers):
                    c = centers[cell_id]
                    lat = c[0] + np.random.normal(0, coord_sigma)
                    lon = c[1] + np.random.normal(0, coord_sigma)
                    lat = max(bbox['lat_min'], min(bbox['lat_max'], lat))
                    lon = max(bbox['lon_min'], min(bbox['lon_max'], lon))
                    coords.append([float(lat), float(lon)])

            if len(coords) >= 2:
                synthetic.append(np.array(coords))

        return synthetic


class DPTrajPMRNDV(DPTrajPM):
    """DPTraj-PM variant using RNDV Voronoi centers (Step 1 only differs)."""

    def __init__(self, epsilon, bbox, rndv_centers_arrays, m=2, pfx_budget_props=None):
        self.epsilon = epsilon
        self.bbox = bbox
        self.m = m
        self.h = m + 2
        self.pfx_budget_props = pfx_budget_props or [0.30, 0.25, 0.25, 0.20]
        self.eps_p = G * max(epsilon - EPS_LEN, 0)
        self.eps_m = (1 - G) * max(epsilon - EPS_LEN, 0)
        self.eps_len = min(EPS_LEN, epsilon)

        self.centers = rndv_centers_arrays.copy()
        self.K = len(self.centers)
        self.N = len(self.centers)
        self.prefix_tree = None
        self.markov = None
        self._traj_lengths = None
        self._len_dist = None
        self._len_bins = None
        self._n_trajs = 0


###############################################################################
# METRICS
###############################################################################

def compute_trip_error(real, synthetic, n_bins=50):
    real_ends = []
    for t in real:
        if len(t) >= 2:
            real_ends.extend([t[0][0], t[-1][0]])
    syn_ends = []
    for t in synthetic:
        if len(t) >= 2:
            syn_ends.extend([t[0][0], t[-1][0]])

    if not real_ends or not syn_ends:
        return 1.0

    lat_min = min(min(real_ends), min(syn_ends))
    lat_max = max(max(real_ends), max(syn_ends))
    if lat_max - lat_min < 1e-10:
        return 0.0

    real_hist, _ = np.histogram(real_ends, bins=n_bins, range=(lat_min, lat_max))
    syn_hist, _ = np.histogram(syn_ends, bins=n_bins, range=(lat_min, lat_max))
    real_norm = real_hist.astype(float) / max(real_hist.sum(), 1)
    syn_norm = syn_hist.astype(float) / max(syn_hist.sum(), 1)
    return float(np.abs(real_norm - syn_norm).sum() / 2)


def compute_length_error(real, synthetic, n_bins=30):
    real_lens = np.array([len(t) for t in real])
    syn_lens = np.array([len(t) for t in synthetic])
    max_len = max(real_lens.max() if len(real_lens) > 0 else 100,
                  syn_lens.max() if len(syn_lens) > 0 else 100, 1)
    real_hist, _ = np.histogram(real_lens, bins=n_bins, range=(0, max_len))
    syn_hist, _ = np.histogram(syn_lens, bins=n_bins, range=(0, max_len))
    real_norm = real_hist.astype(float) / max(real_hist.sum(), 1)
    syn_norm = syn_hist.astype(float) / max(syn_hist.sum(), 1)
    return float(np.abs(real_norm - syn_norm).sum() / 2)


def compute_transition_error(real, synthetic, grid_size=7, bbox=None):
    if bbox is None:
        all_pts = np.vstack([t for t in real + synthetic if len(t) > 0])
        lat_min, lat_max = all_pts[:, 0].min(), all_pts[:, 0].max()
        lon_min, lon_max = all_pts[:, 1].min(), all_pts[:, 1].max()
    else:
        lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
        lon_min, lon_max = bbox['lon_min'], bbox['lon_max']

    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)
    N = grid_size * grid_size

    def grid_trans(trajs):
        trans = np.zeros((N, N))
        for t in trajs:
            for i in range(len(t) - 1):
                u = min(int((t[i][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v = min(int((t[i][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                u2 = min(int((t[i+1][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v2 = min(int((t[i+1][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                trans[u * grid_size + v, u2 * grid_size + v2] += 1
        return trans

    r_T = grid_trans(real)
    s_T = grid_trans(synthetic)
    r_norm = r_T / max(r_T.sum(), 1)
    s_norm = s_T / max(s_T.sum(), 1)
    return float(np.abs(r_norm - s_norm).sum() / 2)


def compute_range_query_error(real, synthetic, grid_size=7, n_queries=200):
    try:
        all_pts = np.vstack([t for t in real + synthetic if len(t) > 0])
        lat_min, lat_max = all_pts[:, 0].min(), all_pts[:, 0].max()
        lon_min, lon_max = all_pts[:, 1].min(), all_pts[:, 1].max()
    except Exception:
        return 1.0

    errors = []
    for _ in range(n_queries):
        r_lat = np.random.uniform(lat_min, lat_max, 2)
        r_lat.sort()
        r_lon = np.random.uniform(lon_min, lon_max, 2)
        r_lon.sort()

        real_in = sum(1 for t in real for p in t
                      if r_lat[0] <= p[0] <= r_lat[1] and r_lon[0] <= p[1] <= r_lon[1])
        syn_in = sum(1 for t in synthetic for p in t
                     if r_lat[0] <= p[0] <= r_lat[1] and r_lon[0] <= p[1] <= r_lon[1])

        if real_in > 0:
            errors.append(abs(real_in - syn_in) / real_in)
        elif syn_in == 0:
            errors.append(0.0)
        else:
            errors.append(1.0)

    return float(np.mean(errors)) if errors else 1.0


def compute_js_divergence(real, synthetic, grid_size=12, bbox=None):
    from scipy.spatial.distance import jensenshannon

    if bbox is None:
        all_pts = np.vstack([t for t in real + synthetic if len(t) > 0])
        lat_min, lat_max = all_pts[:, 0].min(), all_pts[:, 0].max()
        lon_min, lon_max = all_pts[:, 1].min(), all_pts[:, 1].max()
    else:
        lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
        lon_min, lon_max = bbox['lon_min'], bbox['lon_max']

    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def grid_hist(trajs):
        hist = np.zeros((grid_size, grid_size))
        for t in trajs:
            for p in t:
                li = min(int((p[0] - lat_min) / lat_span * grid_size), grid_size - 1)
                lj = min(int((p[1] - lon_min) / lon_span * grid_size), grid_size - 1)
                hist[li, lj] += 1
        return hist.flatten()

    r_hist = grid_hist(real)
    s_hist = grid_hist(synthetic)
    r_norm = r_hist.astype(float) / max(r_hist.sum(), 1)
    s_norm = s_hist.astype(float) / max(s_hist.sum(), 1)
    js = jensenshannon(r_norm, s_norm)
    return float(js) if not np.isnan(js) else 1.0


###############################################################################
# RUNNER
###############################################################################

def run_method(label, model_factory, trajs, bbox, n_reps):
    metrics = {
        'trip_error': [], 'length_error': [], 'transition_error': [],
        'range_query_error': [], 'js_divergence': [], 'elapsed': [],
    }
    for run_i in range(n_reps):
        np.random.seed(RANDOM_SEED + run_i * 1000)
        try:
            t0 = time.time()
            model = model_factory()
            model.fit(trajs)
            synthetic = model.generate(n_trajs=len(trajs))
            elapsed = time.time() - t0

            te = compute_trip_error(trajs, synthetic)
            le = compute_length_error(trajs, synthetic)
            tre = compute_transition_error(trajs, synthetic, grid_size=7, bbox=bbox)
            rqe = compute_range_query_error(trajs, synthetic)
            js = compute_js_divergence(trajs, synthetic, grid_size=12, bbox=bbox)

            metrics['trip_error'].append(te)
            metrics['length_error'].append(le)
            metrics['transition_error'].append(tre)
            metrics['range_query_error'].append(rqe)
            metrics['js_divergence'].append(js)
            metrics['elapsed'].append(elapsed)

            print(f"  [{label}] r{run_i+1}/{n_reps}: Trip={te:.4f} Len={le:.4f} "
                  f"Trans={tre:.4f} RQ={rqe:.4f} JS={js:.4f} ({elapsed:.1f}s)", flush=True)
        except Exception as e:
            print(f"  [{label}] r{run_i+1}/{n_reps}: FAILED - {e}", flush=True)
            import traceback
            traceback.print_exc()

    n_ok = len(metrics['trip_error'])
    if n_ok == 0:
        return {'status': 'FAILED', 'n_success': 0, 'n_total': n_reps}

    return {
        'status': 'OK',
        'n_success': n_ok, 'n_total': n_reps,
        'trip_error_mean': float(np.mean(metrics['trip_error'])),
        'trip_error_std': float(np.std(metrics['trip_error'], ddof=1)) if n_ok > 1 else 0.0,
        'length_error_mean': float(np.mean(metrics['length_error'])),
        'length_error_std': float(np.std(metrics['length_error'], ddof=1)) if n_ok > 1 else 0.0,
        'transition_error_mean': float(np.mean(metrics['transition_error'])),
        'transition_error_std': float(np.std(metrics['transition_error'], ddof=1)) if n_ok > 1 else 0.0,
        'range_query_error_mean': float(np.mean(metrics['range_query_error'])),
        'range_query_error_std': float(np.std(metrics['range_query_error'], ddof=1)) if n_ok > 1 else 0.0,
        'js_divergence_mean': float(np.mean(metrics['js_divergence'])),
        'js_divergence_std': float(np.std(metrics['js_divergence'], ddof=1)) if n_ok > 1 else 0.0,
        'avg_elapsed_s': float(np.mean(metrics['elapsed'])),
    }


def main():
    np.random.seed(RANDOM_SEED)

    beijing_path = os.path.join(DATASETS_DIR, 'geolife', 'Geolife Trajectories 1.3', 'Data')
    porto_path = os.path.join(DATASETS_DIR, 'porto', 'train.csv')
    austin_path = os.path.join(DATASETS_DIR, 'trajs_austin.npz')
    london_path = os.path.join(DATASETS_DIR, 'trajs_london_5more.npz')

    results = {
        'experiment': 'dptrajpm_final',
        'description': 'DPTraj-PM Final: Beijing/Porto/Austin/London, eps=1.0 (eps_p=0.475 + eps_m=0.475 + eps_len=0.05) K=7 m=2',
        'config': {
            'epsilon': EPSILON, 'K': K, 'm': M, 'h': H,
            'n_reps': N_REPS, 'eps_p': EPS_P, 'eps_m': EPS_M,
            'eps_len': EPS_LEN,
            'pfx_budget_props': PFX_BUDGET_PROP, 'g': G,
            'm_max': M_MAX, 'random_seed': RANDOM_SEED,
            'markov_sensitivity': MARKOV_SENSITIVITY,
            'rndv_density_grid_size': DENSITY_GRID_SIZE,
            'rndv_gaussian_sigma': GAUSSIAN_SIGMA,
            'osm_query': True,
            'total_epsilon_check': float(EPS_P + EPS_M + EPS_LEN),
        },
        'dptrajpm': {},
        'dptrajpm_rndv': {},
        'rndv_osm_status': {},
    }

    print("=" * 80)
    print("DPTraj-PM & DPTraj-PM-RNDV — Final Reproduction")
    print("=" * 80)

    datasets = {}

    print("\n[Loading Beijing (GeoLife)]")
    trajs_bj = load_geolife_beijing(beijing_path, max_trajs=200, bbox=BBOXES['beijing'])
    datasets['beijing'] = {'trajs': trajs_bj, 'bbox': BBOXES['beijing']}
    print(f"  {len(trajs_bj)} trajectories")

    print("\n[Loading Porto]")
    trajs_po = load_porto_csv(porto_path, max_trajs=200, bbox=BBOXES['porto'])
    datasets['porto'] = {'trajs': trajs_po, 'bbox': BBOXES['porto']}
    print(f"  {len(trajs_po)} trajectories")

    print("\n[Loading Austin (Gowalla)]")
    if os.path.exists(austin_path):
        trajs_au = load_npz_trajs(austin_path, max_trajs=200)
    else:
        trajs_au = []
    datasets['austin'] = {'trajs': trajs_au, 'bbox': BBOXES['austin']}
    print(f"  {len(trajs_au)} trajectories")

    print("\n[Loading London (Gowalla)]")
    if os.path.exists(london_path):
        trajs_lo = load_npz_trajs(london_path, max_trajs=200)
    else:
        trajs_lo = []
    datasets['london'] = {'trajs': trajs_lo, 'bbox': BBOXES['london']}
    print(f"  {len(trajs_lo)} trajectories")

    for city in ['beijing', 'porto', 'austin', 'london']:
        data = datasets[city]
        trajs = data['trajs']
        bbox = data['bbox']
        if len(trajs) < 5:
            results['dptrajpm'][city] = {'status': 'SKIPPED', 'reason': f'only {len(trajs)} trajs'}
            results['dptrajpm_rndv'][city] = {'status': 'SKIPPED', 'reason': f'only {len(trajs)} trajs'}
            results['rndv_osm_status'][city] = {'status': 'SKIPPED'}
            continue

        # ---- OSM RNDV Center Query ----
        print(f"\n  [RNDV OSM] Querying Overpass API for {city} road network...", flush=True)
        osm_success = False
        ways, used_url = query_osm_highways(bbox, timeout=180)
        if ways is not None and len(ways) > 0:
            density_raw = compute_road_density_grid(ways, bbox)
            density_smooth = gaussian_filter(density_raw.astype(float), sigma=GAUSSIAN_SIGMA)
            rndv_centers = select_centers_rndv(density_smooth, bbox, K_cells=K)
            osm_success = True
            print(f"    OSM success via {used_url}: {len(rndv_centers)} RNDV centers", flush=True)
        else:
            print(f"    OSM query FAILED. Using farthest-first fallback (OSM_FAILED_FALLBACK).", flush=True)
            rndv_centers = fallback_rndv_centers(bbox, K_cells=K)
        results['rndv_osm_status'][city] = {
            'osm_success': osm_success,
            'n_centers': len(rndv_centers),
            'fallback_used': not osm_success,
            'label': 'OSM' if osm_success else 'OSM_FAILED_FALLBACK',
        }

        # ---- DPTraj-PM (Uniform Grid) ----
        print(f"\n--- DPTraj-PM {city} ({len(trajs)} trajs) ---")
        def make_grid(_bbox=bbox):
            return DPTrajPM(EPSILON, _bbox, K_cells=K, m=M, pfx_budget_props=PFX_BUDGET_PROP)
        results['dptrajpm'][city] = run_method(f"DPTrajPM_{city}", make_grid, trajs, bbox, N_REPS)

        # ---- DPTraj-PM-RNDV ----
        print(f"\n--- DPTraj-PM-RNDV {city} ({len(trajs)} trajs) ---")
        def make_rndv(_bbox=bbox, _cents=rndv_centers):
            return DPTrajPMRNDV(EPSILON, _bbox, _cents, m=M, pfx_budget_props=PFX_BUDGET_PROP)
        results['dptrajpm_rndv'][city] = run_method(f"DPTrajPM_RNDV_{city}", make_rndv, trajs, bbox, N_REPS)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for city in ['beijing', 'porto', 'austin', 'london']:
        dpm = results['dptrajpm'].get(city, {})
        rndv = results['dptrajpm_rndv'].get(city, {})
        osm_status = results['rndv_osm_status'].get(city, {})
        print(f"\n{city}:")
        print(f"  RNDV OSM status: {osm_status.get('label', 'N/A')} "
              f"(n_centers={osm_status.get('n_centers', '?')})")
        if dpm.get('status') == 'OK':
            print(f"  DPTraj-PM       TripErr={dpm['trip_error_mean']:.4f} "
                  f"LenErr={dpm['length_error_mean']:.4f} "
                  f"TransErr={dpm['transition_error_mean']:.4f} "
                  f"JS={dpm['js_divergence_mean']:.4f}")
        if rndv.get('status') == 'OK':
            print(f"  DPTraj-PM-RNDV  TripErr={rndv['trip_error_mean']:.4f} "
                  f"LenErr={rndv['length_error_mean']:.4f} "
                  f"TransErr={rndv['transition_error_mean']:.4f} "
                  f"JS={rndv['js_divergence_mean']:.4f}")

    # Save
    out_dir = os.path.join(FILE_DIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'results.json')

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer, np.int_)):
                return int(obj)
            if isinstance(obj, (np.floating, np.float_)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)

    print(f"\nResults saved to: {out_path}")
    return results


if __name__ == '__main__':
    main()

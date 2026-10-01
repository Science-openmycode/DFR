"""
PrivTrace & PrivTrace-RNDV — local paper-based reimplementation
================================================================
USENIX Security 2023 (Wang et al.): "PrivTrace: Differentially Private
Trajectory Synthesis by Adaptive Markov Models"

This file implements a local PrivTrace-style pipeline for shared evaluation.
It is not author-code-certified; see public_release/check/BASELINE_REPRODUCTION_AUDIT.md.

  Step 1: Two-Level Adaptive Grid (ε1=0.2ε budget)
    - K×K uniform coarse grid (Level 1)
    - Per-cell point density query + Laplace noise
    - High-density cells subdivided into 2×2 sub-grids (Level 2)
    - Two layers merged, empty cells pruned, cell centers recorded

  Step 2: 1st-Order + 2nd-Order Markov Models (ε2=0.4ε, ε3=0.4ε)
    - 1st-order transition count matrix + Laplace noise
    - 2nd-order transition counts (trigram frequency) + Laplace noise
    - Sensitivity = m_max (one trajectory contributes max m_max transitions)
    - Normalized to transition probabilities

  Step 3: cvxpy Convex Optimization Post-processing
    - Minimize Frobenius distance to noisy transition matrix
    - Constraints: non-negative, row-sum = 1
    - SCS solver (fallback: simple row normalization)

  Step 4: Trip (OD) Distribution Estimation
    - Start-End distribution statistics + Laplace noise
    - Used for calibrating generated trajectory start/end points

  Step 5: Trajectory Synthesis
    - 1st-order AND 2nd-order Markov both generated
    - Auto-select order with lower Jensen-Shannon divergence
    - Random walk from noisy initial distribution
    - Gaussian noise on cell center coordinates for synthetic points

RNDV Variant:
  - Step 1 REPLACED by RNDV Voronoi partitioning (ZERO ε budget)
  - ε1 = 0.2ε saved, redistributed to ε2/ε3 → [0, 0.5, 0.5]
  - RNDV: OSM road network → 50×50 density grid → Gaussian KDE(σ=3) →
    select K=7 highest-density cell centers + density-guided sub-division
    (2-3 sub-centers within high-density Voronoi cells)
  - Steps 2-5 completely unchanged

Parameters: ε=1.0, 5 reps, 4 cities
Cities: Beijing (GeoLife), Porto (taxi), Austin (Gowalla), London (Gowalla)
Output: experiments/paper_comparison/final/privtrace/results.json
"""

import numpy as np
import json
import os
import sys
import time
import math
import gc
import csv
import requests
from scipy.spatial.distance import jensenshannon
from scipy.ndimage import gaussian_filter

# ── Optional dependencies ──────────────────────────────────────────────────
try:
    import cvxpy as cp
    HAS_CVXPY = True
except ImportError:
    HAS_CVXPY = False
    print("WARNING: cvxpy not installed. Using fallback normalization.", flush=True)

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("WARNING: networkx not installed. Shortest path disabled.", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

EXP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
DATASET_DIR = os.path.join(EXP_DIR, 'datasets')
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUTPUT_DIR, exist_ok=True)

M_MAX = 100                    # Maximum trajectory length
COORD_SIGMA = 0.02             # Gaussian noise σ for coordinate sampling
METRIC_GRID_SIZE = 12          # Evaluation grid resolution
N_REPS = 5                     # Number of repetitions
EPSILON = 1.0                  # Total privacy budget
DELTA = 1e-5                   # δ for (ε,δ)-DP
K_GRID = 12                    # Level-1 coarse grid: K×K cells
K_RNDV = 7                     # Number of RNDV Voronoi centers
RANDOM_SEED = 42

# Budget split [ε1, ε2, ε3] per PrivTrace paper Table 1
# ε1=grid, ε2=1st-order pool (Markov + init), ε3=2nd-order pool (Markov + trip + len)
BUDGET_PRIVTRACE = [0.2, 0.4, 0.4]

# RNDV: zero-budget grid, redistribute ε1 to Markov
BUDGET_RNDV = [0.0, 0.5, 0.5]

# Sub-budget fractions within ε2 pool: Markov matrix + initial distribution
INIT_FRAC = 0.10   # ε_init = INIT_FRAC * ε2
# Sub-budget fractions within ε3 pool: Markov matrix + trip + length
TRIP_FRAC = 0.10   # ε_trip = TRIP_FRAC * ε3
LEN_FRAC = 0.10    # ε_len  = LEN_FRAC  * ε3

# OSM Overpass API endpoints (for road-network-aware RNDV)
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
OVERPASS_HEADERS = {'User-Agent': 'privtrace-final/1.0'}
GAUSSIAN_KDE_SIGMA = 3.0       # σ for Gaussian KDE over road density
DENSITY_GRID_SIZE = 50         # Resolution of road density grid

CITY_CONFIGS = {
    'beijing': {
        'label': 'Beijing', 'type': 'geolife',
        'bbox': {'lat_min': 39.75, 'lat_max': 40.15,
                 'lon_min': 116.10, 'lon_max': 116.65},
        'data_path': os.path.join(EXP_DIR, 'datasets', 'geolife',
                                   'Geolife Trajectories 1.3', 'Data'),
    },
    'porto': {
        'label': 'Porto', 'type': 'csv',
        'bbox': {'lat_min': 41.10, 'lat_max': 41.20,
                 'lon_min': -8.70, 'lon_max': -8.55},
        'data_path': os.path.join(EXP_DIR, 'datasets', 'porto', 'train.csv'),
    },
    'austin': {
        'label': 'Austin', 'type': 'npz',
        'bbox': {'lat_min': 30.05, 'lat_max': 30.55,
                 'lon_min': -98.00, 'lon_max': -97.50},
        'data_path': os.path.join(EXP_DIR, 'datasets', 'trajs_austin.npz'),
    },
    'london': {
        'label': 'London', 'type': 'npz',
        'bbox': {'lat_min': 51.30, 'lat_max': 51.70,
                 'lon_min': -0.50, 'lon_max': 0.20},
        'data_path': os.path.join(EXP_DIR, 'datasets', 'trajs_london_5more.npz'),
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    RE = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return 2 * RE * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def map_point_to_cell(point, centers):
    dists = np.linalg.norm(centers - point, axis=1)
    return int(np.argmin(dists))


def safe_choice(candidates, probs):
    probs = np.asarray(probs, dtype=float)
    probs = np.nan_to_num(probs, nan=0.0, posinf=0.0, neginf=0.0)
    probs = np.maximum(probs, 0)
    s = probs.sum()
    if s <= 0:
        probs = np.ones(len(candidates)) / len(candidates)
    else:
        probs = probs / s
    probs = np.maximum(probs, 0)
    s = probs.sum()
    if s <= 0:
        probs = np.ones(len(candidates)) / len(candidates)
    return np.random.choice(candidates, p=probs / s)


# ═══════════════════════════════════════════════════════════════════════════════
# LAPLACE NOISE (mirrors the official tools/noise.py convention)
# ═══════════════════════════════════════════════════════════════════════════════

def add_laplace_noise(array, epsilon, sensitivity=1.0):
    if epsilon <= 0 or sensitivity <= 0:
        return array.copy()
    scale = sensitivity / epsilon
    noise = np.random.laplace(scale=scale, size=array.shape)
    return array + noise


def positive_regulation(noisy_array):
    """
    Faithful reproduction of Noise.positive_regulation from official code.
    Removes negative values by shifting negative mass to smallest positive values,
    iterating until all negative mass is absorbed.
    """
    arr = noisy_array.copy()
    while True:
        neg_mask = arr < 0
        if not neg_mask.any():
            break
        neg_sum = np.sum(arr[neg_mask])
        pos_mask = arr > 0
        if not pos_mask.any():
            arr[:] = 0
            break
        arr[neg_mask] = 0
        sorted_pos = np.sort(arr[pos_mask])
        cumsum = np.cumsum(sorted_pos)
        n_absorb = 1
        while n_absorb < len(cumsum) and cumsum[n_absorb - 1] < -neg_sum:
            n_absorb += 1
        pos_indices = np.where(pos_mask)[0]
        sort_order = np.argsort(arr[pos_mask])
        target_idx_in_sorted = n_absorb - 1
        if target_idx_in_sorted < len(sort_order):
            target_idx = pos_indices[sort_order[target_idx_in_sorted]]
            if n_absorb > 1:
                for k in range(n_absorb - 1):
                    idx = pos_indices[sort_order[k]]
                    arr[idx] = 0
            arr[target_idx] = cumsum[min(n_absorb - 1, len(cumsum) - 1)] + neg_sum
        else:
            if len(pos_indices) > 0:
                arr[pos_indices[sort_order[-1]]] = cumsum[-1] + neg_sum
            else:
                arr[:] = 0
        break
    return np.maximum(arr, 0)


def positive_regulation_for_markov_matrix(noisy_matrix):
    result = noisy_matrix.copy()
    for i in range(result.shape[0]):
        result[i] = positive_regulation(result[i])
    return result


def optimize_transition_matrix(T_noisy):
    """
    cvxpy convex optimization: denoise transition matrix.
    min ||T - T_noisy||_F^2
    s.t. T >= 0, sum_j T[i,j] = 1 for all i
    """
    if not HAS_CVXPY:
        rs = T_noisy.sum(axis=1, keepdims=True)
        rs[rs == 0] = 1
        return T_noisy / rs
    K = T_noisy.shape[0]
    T = cp.Variable((K, K))
    constraints = [T >= 0]
    for i in range(K):
        constraints.append(cp.sum(T[i, :]) == 1)
    objective = cp.Minimize(cp.sum_squares(T - T_noisy))
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(solver=cp.SCS, max_iters=5000)
        if T.value is not None:
            return np.maximum(T.value, 0)
    except Exception:
        pass
    rs = T_noisy.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1
    return T_noisy / rs


def optimize_distribution_vector(v_noisy):
    """
    cvxpy convex optimization for a 1D probability vector.
    min ||v - v_noisy||_2^2  s.t. v >= 0, sum(v) = 1
    """
    if not HAS_CVXPY:
        s = v_noisy.sum()
        return v_noisy / s if s > 0 else np.ones_like(v_noisy) / len(v_noisy)
    n = len(v_noisy)
    v = cp.Variable(n)
    constraints = [v >= 0, cp.sum(v) == 1]
    objective = cp.Minimize(cp.sum_squares(v - v_noisy))
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(solver=cp.SCS, max_iters=5000)
        if v.value is not None:
            return np.maximum(v.value, 0)
    except Exception:
        pass
    s = v_noisy.sum()
    return v_noisy / s if s > 0 else np.ones_like(v_noisy) / n


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_geolife_beijing(data_path, max_trajs=200, bbox=None):
    trajectories = []
    count = 0
    for root, dirs, files in os.walk(data_path):
        for fname in files:
            if not fname.endswith('.plt') or count >= max_trajs:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r') as f:
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
                        if (bbox['lat_min'] <= lat <= bbox['lat_max'] and
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
                if (bbox['lat_min'] <= lat <= bbox['lat_max'] and
                        bbox['lon_min'] <= lon <= bbox['lon_max']):
                    points.append([lat, lon])
            if len(points) >= 2:
                trajectories.append(np.array(points))
                count += 1
    return trajectories


def load_npz_trajs(npz_path, bbox, max_trajs=200):
    data = np.load(npz_path, allow_pickle=True)
    trajs = data['trajectories']
    kept = []
    for t in trajs:
        if len(kept) >= max_trajs:
            break
        pts = []
        for p in t:
            lat, lon = float(p[0]), float(p[1])
            if (bbox['lat_min'] <= lat <= bbox['lat_max'] and
                    bbox['lon_min'] <= lon <= bbox['lon_max']):
                pts.append([lat, lon])
        if len(pts) >= 2:
            kept.append(np.array(pts))
    return kept


def clip_trajectories(trajs, m_max=M_MAX):
    return [t[:m_max] for t in trajs]


def load_data(city_key):
    cfg = CITY_CONFIGS[city_key]
    if cfg['type'] == 'geolife':
        trajs = load_geolife_beijing(cfg['data_path'], max_trajs=200, bbox=cfg['bbox'])
    elif cfg['type'] == 'csv':
        trajs = load_porto_csv(cfg['data_path'], max_trajs=200, bbox=cfg['bbox'])
    elif cfg['type'] == 'npz':
        trajs = load_npz_trajs(cfg['data_path'], cfg['bbox'], max_trajs=200)
    else:
        raise ValueError(f"Unknown type: {cfg['type']}")
    trajs = clip_trajectories(trajs)
    return trajs, cfg['bbox']


# ═══════════════════════════════════════════════════════════════════════════════
# BBOX COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_bbox_from_trajs(trajectories):
    lat_min_v, lat_max_v = float('inf'), float('-inf')
    lon_min_v, lon_max_v = float('inf'), float('-inf')
    for t in trajectories:
        if len(t) > 0:
            arr = np.asarray(t, dtype=float)
            lat_min_v = min(lat_min_v, float(arr[:, 0].min()))
            lat_max_v = max(lat_max_v, float(arr[:, 0].max()))
            lon_min_v = min(lon_min_v, float(arr[:, 1].min()))
            lon_max_v = max(lon_max_v, float(arr[:, 1].max()))
    if lat_min_v == float('inf'):
        lat_min_v = lat_max_v = lon_min_v = lon_max_v = 0.0
    ext = 0.00001
    lat_span = lat_max_v - lat_min_v
    lon_span = lon_max_v - lon_min_v
    return {
        'lat_min': lat_min_v - ext * lat_span if lat_span > 0 else lat_min_v - 0.001,
        'lat_max': lat_max_v + ext * lat_span if lat_span > 0 else lat_max_v + 0.001,
        'lon_min': lon_min_v - ext * lon_span if lon_span > 0 else lon_min_v - 0.001,
        'lon_max': lon_max_v + ext * lon_span if lon_span > 0 else lon_max_v + 0.001,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1a: TWO-LEVEL ADAPTIVE GRID (PrivTrace)
# ─────────────────────────────────────────────────────────────────────────────
# Faithful to official code Grid.get_grid() in discretization/grid.py
# and Divide in discretization/divide.py
# ═══════════════════════════════════════════════════════════════════════════════

def build_privtrace_adaptive_grid(trajectories, bbox, K=K_GRID, eps_grid=0.2):
    """
    Two-level adaptive grid from PrivTrace paper Figure 2.

    Level 1: K×K uniform grid over bounding box
      - Count trajectory points per cell (normalized by traj length)
      - Add Laplace noise (ε1 = eps_grid * ε_total)
      - Apply positive regulation to remove negatives

    Level 2: Subdivide high-density cells into 2×2 sub-cells
      - Threshold = n_trajs * 0.05 / (K * K)  [from official divide.py]
      - Cells with noisy density > threshold are subdivided
      - Each subdivided cell → 4 fine sub-cells (2×2 grid)
      - Fine cell centers computed for coordinate recovery

    Returns:
      states: list of {lat, lon, type, n, s, w, e} dicts
      discrete: list of state-index lists (one per trajectory)
      n_coarse, n_fine: counts for reporting
    """
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)
    n_trajs = len(trajectories)

    # ── Level 1: K×K uniform grid density ──────────────────────────────
    cell_density = np.zeros((K, K))
    for traj in trajectories:
        L = max(len(traj), 1)
        for pt in traj:
            row = min(int((pt[0] - lat_min) / lat_span * K), K - 1)
            col = min(int((pt[1] - lon_min) / lon_span * K), K - 1)
            cell_density[row, col] += 1.0 / L   # normalize by trajectory length

    # ── Laplace noise on density (ε1 budget) ───────────────────────────
    if eps_grid > 0:
        noisy_density = add_laplace_noise(cell_density, eps_grid, sensitivity=1.0)
        noisy_density = positive_regulation(noisy_density)
    else:
        noisy_density = cell_density

    # ── Subdivision threshold (from official divide.py) ────────────────
    threshold = n_trajs * 0.05 / (K * K) if K * K > 0 else 0
    if threshold < 1e-10:
        nonzero = noisy_density[noisy_density > 0]
        threshold = float(np.median(nonzero)) if len(nonzero) > 0 else 1.0

    # ── Level 2: Subdivide high-density cells into 2×2 ─────────────────
    subdivide_param = np.ones((K, K), dtype=int)  # 1 = keep, 2 = subdivide
    for i in range(K):
        for j in range(K):
            if noisy_density[i, j] > threshold:
                subdivide_param[i, j] = 2

    # ── Build state list and state_map ─────────────────────────────────
    states = []
    state_map = {}   # (coarse_i, coarse_j) → list of state indices
    n_coarse, n_fine = 0, 0

    for i in range(K):
        clat_min = lat_min + i * lat_span / K
        clat_max = lat_min + (i + 1) * lat_span / K
        for j in range(K):
            clon_min = lon_min + j * lon_span / K
            clon_max = lon_min + (j + 1) * lon_span / K
            sp = subdivide_param[i, j]

            if sp > 1:
                fine_indices = []
                for fi in range(sp):
                    flat_min = clat_min + fi * (clat_max - clat_min) / sp
                    flat_max = clat_min + (fi + 1) * (clat_max - clat_min) / sp
                    for fj in range(sp):
                        flon_min = clon_min + fj * (clon_max - clon_min) / sp
                        flon_max = clon_min + (fj + 1) * (clon_max - clon_min) / sp
                        fine_indices.append(len(states))
                        states.append({
                            'lat': float((flat_min + flat_max) / 2),
                            'lon': float((flon_min + flon_max) / 2),
                            'type': 'fine',
                            'n': float(flat_max), 's': float(flat_min),
                            'w': float(flon_min), 'e': float(flon_max),
                        })
                        n_fine += 1
                state_map[(i, j)] = fine_indices
            else:
                state_map[(i, j)] = [len(states)]
                states.append({
                    'lat': float((clat_min + clat_max) / 2),
                    'lon': float((clon_min + clon_max) / 2),
                    'type': 'coarse',
                    'n': float(clat_max), 's': float(clat_min),
                    'w': float(clon_min), 'e': float(clon_max),
                })
                n_coarse += 1

    # ── Discretize trajectories to state indices ───────────────────────
    discrete = []
    for traj in trajectories:
        seq = []
        for pt in traj:
            row = min(int((pt[0] - lat_min) / lat_span * K), K - 1)
            col = min(int((pt[1] - lon_min) / lon_span * K), K - 1)
            indices = state_map[(row, col)]
            if len(indices) == 1:
                seq.append(indices[0])
            else:
                clat_min_c = lat_min + row * lat_span / K
                clon_min_c = lon_min + col * lon_span / K
                sp = subdivide_param[row, col]
                fi = min(int((pt[0] - clat_min_c) / (lat_span / K) * sp), sp - 1)
                fj = min(int((pt[1] - clon_min_c) / (lon_span / K) * sp), sp - 1)
                seq.append(indices[fi * sp + fj])
        discrete.append(seq)

    # ── State pruning: remove unused states ────────────────────────────
    used = set()
    for seq in discrete:
        for s in seq:
            used.add(s)
    usable_to_real = sorted(used)
    real_to_usable = {r: u for u, r in enumerate(usable_to_real)}
    usable_states = [states[r] for r in usable_to_real]
    discrete_usable = [[real_to_usable[s] for s in seq if s in real_to_usable]
                       for seq in discrete]
    discrete_usable = [seq for seq in discrete_usable if len(seq) >= 2]

    return usable_states, discrete_usable, n_coarse, n_fine


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1b: RNDV VORONOI PARTITIONING (PrivTrace-RNDV)
# ─────────────────────────────────────────────────────────────────────────────
# RNDV: Road-Network-Density-based Voronoi partitioning
# Zero ε budget — uses publicly available OSM road network data
# ═══════════════════════════════════════════════════════════════════════════════

def query_osm_road_density(bbox_dict, grid_size=DENSITY_GRID_SIZE, timeout=180):
    """
    Query OSM road network via Overpass API and compute density grid.
    Returns: (density_grid, bool) where bool indicates success.
    """
    bbox_str = (f"{bbox_dict['lat_min']},{bbox_dict['lon_min']},"
                f"{bbox_dict['lat_max']},{bbox_dict['lon_max']}")
    query = f'[out:json][timeout:180];(way["highway"]({bbox_str}););out geom;'

    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={'data': query},
                                 headers=OVERPASS_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                continue
            data = resp.json()
            nodes = []
            for elem in data.get('elements', []):
                geom = elem.get('geometry', [])
                for g in geom:
                    nodes.append([g['lat'], g['lon']])

            if not nodes:
                continue

            nodes = np.array(nodes)
            lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
            lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']

            density = np.zeros((grid_size, grid_size))
            lat_step = (lat_max - lat_min) / grid_size
            lon_step = (lon_max - lon_min) / grid_size
            for n in nodes:
                ri = min(int((n[0] - lat_min) / lat_step), grid_size - 1)
                ci = min(int((n[1] - lon_min) / lon_step), grid_size - 1)
                density[ri, ci] += 1

            return density, True
        except Exception:
            continue

    return np.zeros((grid_size, grid_size)), False


def rndv_select_centers(bbox_dict, road_density, K=K_RNDV, sigma=GAUSSIAN_KDE_SIGMA):
    """
    Select K Voronoi centers based on road network density.

    Pipeline:
      1. Gaussian KDE smooth the road density grid (σ=3)
      2. Select K=7 cells with highest density as primary centers
      3. For each high-density Voronoi cell, add 2-3 sub-centers
         (zero-budget density-guided subdivision)
      4. Return all [lat, lon] center coordinates
    """
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    grid_size = road_density.shape[0]

    # ── Gaussian KDE smooth ────────────────────────────────────────────
    density_smooth = gaussian_filter(road_density.astype(float), sigma=sigma)

    # ── Select K primary centers (highest density cells) ───────────────
    flat_idx = np.argsort(-density_smooth.ravel())
    selected_cells = set()
    centers = []
    min_dist_cells = 2  # minimum grid-cell distance between centers

    for idx in flat_idx:
        if len(centers) >= K:
            break
        r, c = divmod(int(idx), grid_size)
        # Check minimum distance from existing selections
        too_close = False
        for (cr, cc) in selected_cells:
            if abs(r - cr) < min_dist_cells and abs(c - cc) < min_dist_cells:
                too_close = True
                break
        if not too_close:
            selected_cells.add((r, c))
            lat_c = lat_min + (r + 0.5) * (lat_max - lat_min) / grid_size
            lon_c = lon_min + (c + 0.5) * (lon_max - lon_min) / grid_size
            centers.append({'lat': float(lat_c), 'lon': float(lon_c), 'type': 'rndv'})

    # ── Density-guided sub-division within high-density cells ──────────
    # For each primary center, add 2-3 sub-centers within the cell
    # if the density is above the median of selected cells
    if len(centers) >= 2:
        densities_of_selected = [density_smooth[cr, cc] for (cr, cc) in selected_cells]
        median_density = np.median(densities_of_selected)
        lat_step = (lat_max - lat_min) / grid_size
        lon_step = (lon_max - lon_min) / grid_size

        sub_centers = []
        for i, (cr, cc) in enumerate(selected_cells):
            if density_smooth[cr, cc] > median_density:
                # Add 2 sub-centers offset from the primary center
                offsets = [
                    (lat_step * 0.3, lon_step * 0.3),
                    (lat_step * -0.3, lon_step * -0.3),
                    (lat_step * 0.3, lon_step * -0.3),
                ]
                n_sub = min(2 if density_smooth[cr, cc] > 2 * median_density else 1, 3)
                for o in range(n_sub):
                    lat_sub = centers[i]['lat'] + offsets[o][0]
                    lon_sub = centers[i]['lon'] + offsets[o][1]
                    lat_sub = max(lat_min, min(lat_max, lat_sub))
                    lon_sub = max(lon_min, min(lon_max, lon_sub))
                    sub_centers.append({
                        'lat': float(lat_sub), 'lon': float(lon_sub), 'type': 'rndv_sub'
                    })
        centers.extend(sub_centers)

    return centers


def build_rndv_state_space(trajectories, centers):
    """
    Map trajectory points to nearest RNDV Voronoi center.
    Returns usable states list and discretized trajectories.
    """
    center_pts = np.array([[c['lat'], c['lon']] for c in centers])

    discrete = [[map_point_to_cell(pt, center_pts) for pt in t]
                for t in trajectories]
    discrete = [seq for seq in discrete if len(seq) >= 2]

    used_states = set()
    for seq in discrete:
        for s in seq:
            used_states.add(s)

    states = []
    for i in sorted(used_states):
        states.append({
            'lat': float(centers[i]['lat']),
            'lon': float(centers[i]['lon']),
            'type': centers[i]['type'],
            'n': float(centers[i]['lat']) + 0.01,
            's': float(centers[i]['lat']) - 0.01,
            'w': float(centers[i]['lon']) - 0.01,
            'e': float(centers[i]['lon']) + 0.01,
        })

    real_to_usable = {r: u for u, r in enumerate(sorted(used_states))}
    discrete_usable = [[real_to_usable[s] for s in seq if s in real_to_usable]
                       for seq in discrete]
    discrete_usable = [seq for seq in discrete_usable if len(seq) >= 2]

    return states, discrete_usable


def fallback_rndv_centers(bbox, K=K_RNDV):
    """Farthest-first sampling from a fine grid — fallback when OSM unavailable."""
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    G = int(math.ceil(math.sqrt(K * 4)))
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
    while len(selected) < K:
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
    return [{'lat': float(p[0]), 'lon': float(p[1]), 'type': 'rndv_fallback'}
            for p in selected]


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED PRIVTRACE MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class PrivTraceModel:
    """
    Complete PrivTrace pipeline supporting both:
      - Original: K×K adaptive grid (ε1 = 0.2ε)
      - RNDV:    Voronoi partition (ε1 = 0, saved to Markov budget)

    Steps:
      1. Build state space (adaptive grid or RNDV)
      2. 1st-order Markov: counts → Laplace(ε2) → positive regulation → normalize
      3. cvxpy optimization for start-end calibration
      4. 2nd-order Markov: counts → Laplace(ε3) → normalize
      5. Trip distribution + length distribution estimation
    """

    def __init__(self, epsilon, budget_config, K_grid=K_GRID, K_rndv=K_RNDV,
                 rndv_centers=None, method_name='PrivTrace'):
        self.epsilon = epsilon
        self.eps_grid = budget_config[0] * epsilon
        self.eps_order1 = budget_config[1] * epsilon
        self.eps_order2 = budget_config[2] * epsilon
        self.budget_config = list(budget_config)
        self.K_grid = K_grid
        self.K_rndv = K_rndv
        self.rndv_centers = rndv_centers
        self.method_name = method_name
        self.m_max = M_MAX

        # Sub-budget allocation: ε2 pool → 1st-order Markov + init
        self.eps_init = self.eps_order1 * INIT_FRAC
        self.eps_1st_markov = self.eps_order1 * (1 - INIT_FRAC)
        # Sub-budget allocation: ε3 pool → 2nd-order Markov + trip + length
        self.eps_trip = self.eps_order2 * TRIP_FRAC
        self.eps_len = self.eps_order2 * LEN_FRAC
        self.eps_2nd_markov = self.eps_order2 * (1 - TRIP_FRAC - LEN_FRAC)

        # Budget audit
        _total = (self.eps_grid + self.eps_init + self.eps_1st_markov +
                  self.eps_trip + self.eps_2nd_markov + self.eps_len)
        assert abs(_total - epsilon) < 1e-9, \
            f"Budget leak: ε_grid={self.eps_grid:.3f} + ε_init={self.eps_init:.3f} + "\
            f"ε_1st={self.eps_1st_markov:.3f} + ε_trip={self.eps_trip:.3f} + "\
            f"ε_2nd={self.eps_2nd_markov:.3f} + ε_len={self.eps_len:.3f} = "\
            f"{_total:.3f} != ε={epsilon}"

    def fit(self, trajectories):
        self._n_trajs = len(trajectories)
        self.bbox = compute_bbox_from_trajs(trajectories)

        # ── Step 1: Build state space ──────────────────────────────────
        rndv_osm_success = False

        if self.rndv_centers is not None:
            # RNDV mode: use pre-computed Voronoi centers
            # Variant B: if ε_grid > 0, consume it via dummy Laplace query
            if self.eps_grid > 0:
                _ = add_laplace_noise(np.zeros(1), self.eps_grid, sensitivity=1.0)
                print(f"      RNDV: dummy query consumed ε_grid={self.eps_grid:.2f} "
                      f"(no effect on state space)", flush=True)
            self.states, discrete = build_rndv_state_space(
                trajectories, self.rndv_centers)
            self.N = len(self.states)
            budget_note = "consumed via dummy" if self.eps_grid > 0 else "saved → Markov"
            print(f"      RNDV Voronoi: N={self.N} states "
                  f"(ε_grid={self.eps_grid:.2f}, {budget_note})",
                  flush=True)
        else:
            # Original PrivTrace: adaptive grid
            self.states, discrete, n_coarse, n_fine = \
                build_privtrace_adaptive_grid(
                    trajectories, self.bbox, K=self.K_grid,
                    eps_grid=self.eps_grid)
            self.N = len(self.states)
            print(f"      Adaptive grid: N={self.N} states "
                  f"({n_coarse} coarse + {n_fine} fine, ε_grid={self.eps_grid:.2f})",
                  flush=True)

        self.states_centers = np.array([[s['lat'], s['lon']] for s in self.states])

        # ── Step 2a: 1st-order Markov (ε2 budget) ──────────────────────
        self._build_1st_order_markov(discrete)

        # ── Step 3: cvxpy optimization for start-end calibration ───────
        self._calibrate_start_end()

        # ── Step 2b: 2nd-order Markov (ε3 budget) ──────────────────────
        # ── Step 4: Trip & length distribution ─────────────────────────
        self._build_2nd_order_and_stats(discrete)

    def _build_1st_order_markov(self, discrete):
        N = self.N

        # Count 1st-order transitions
        edge1_counts = np.zeros((N, N))
        init_counts = np.zeros(N)

        for seq in discrete:
            if len(seq) > 0:
                init_counts[seq[0]] += 1
            for a in range(len(seq) - 1):
                edge1_counts[seq[a]][seq[a + 1]] += 1

        # ── Laplace noise (ε2 sub: 1st-order Markov matrix) ───────────
        # Sensitivity = m_max: deleting one trajectory removes ≤ m_max transitions
        self.noisy_edge1 = add_laplace_noise(
            edge1_counts, self.eps_1st_markov, sensitivity=float(self.m_max))
        self.noisy_edge1 = positive_regulation_for_markov_matrix(
            self.noisy_edge1)

        # ── Row-normalize to transition probabilities ─────────────────
        row_sums = self.noisy_edge1.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        self.trans1 = self.noisy_edge1 / row_sums

        # ── cvxpy convex optimization on 1st-order transition matrix ──
        if HAS_CVXPY:
            self.trans1 = optimize_transition_matrix(self.trans1)

        # ── Initial state distribution ────────────────────────────────
        # Sensitivity = 1: one trajectory changes init count by at most 1
        noisy_init = add_laplace_noise(
            init_counts.astype(float), self.eps_init, sensitivity=1.0)
        noisy_init = positive_regulation(noisy_init)
        s = noisy_init.sum()
        self.init_dist = noisy_init / s if s > 0 else np.ones(N) / N

    def _calibrate_start_end(self):
        """
        cvxpy convex optimization for start-end distribution calibration.
        Faithful to official start_end_calibrator.py:

        Minimize error between length-normalized counts and noisy start/end
        frequencies, subject to non-negativity constraints.

        SCS solver used. Falls back to uniform if cvxpy/networkx unavailable.
        """
        N = self.N

        if not HAS_CVXPY or not HAS_NETWORKX:
            self.optimized_start_end = np.ones((N, N)) / (N * N)
            self.shortest_lengths = np.ones((N, N))
            return

        try:
            # ── Build distance network from transition connections ─────
            G = nx.Graph()
            for i in range(N):
                for j in range(N):
                    if i != j and (self.trans1[i, j] > 1e-6 or
                                   self.trans1[j, i] > 1e-6):
                        dist = haversine_km(
                            self.states[i]['lat'], self.states[i]['lon'],
                            self.states[j]['lat'], self.states[j]['lon'])
                        G.add_edge(i, j, weight=dist)

            if G.number_of_nodes() == 0:
                self.optimized_start_end = np.ones((N, N)) / (N * N)
                self.shortest_lengths = np.ones((N, N))
                return

            # Ensure connectivity
            for i in range(N):
                if i not in G:
                    G.add_node(i)
                for j in range(N):
                    if (i != j and j in G and i in G and
                            not nx.has_path(G, i, j)):
                        dist = haversine_km(
                            self.states[i]['lat'], self.states[i]['lon'],
                            self.states[j]['lat'], self.states[j]['lon'])
                        G.add_edge(i, j, weight=max(dist, 0.01))

            # ── Shortest path lengths ─────────────────────────────────
            shortest = np.ones((N, N))
            for i in range(N):
                for j in range(N):
                    if i == j:
                        shortest[i, j] = 1
                    elif nx.has_path(G, i, j):
                        shortest[i, j] = max(
                            nx.shortest_path_length(G, source=i, target=j), 1)
                    else:
                        shortest[i, j] = max(N, 1)
            self.shortest_lengths = shortest

            # ── cvxpy optimization ───────────────────────────────────
            start_vals = self.noisy_edge1.sum(axis=1)
            end_vals = self.noisy_edge1.sum(axis=0)

            distribution = cp.Variable((N, N))
            lengths = shortest.copy()
            lengths[lengths < 1] = 1

            # Objective: minimize error with length-normalized distribution
            objective = cp.Minimize(
                cp.norm(cp.sum(cp.multiply(distribution, 1.0 / lengths),
                               axis=1) - start_vals) +
                cp.norm(cp.sum(cp.multiply(distribution, 1.0 / lengths),
                               axis=0) - end_vals)
            )
            constraints = [distribution >= 0]
            prob = cp.Problem(objective, constraints)

            try:
                prob.solve(solver=cp.SCS, verbose=False)
            except Exception:
                prob.solve(solver='SCS', verbose=False)

            if distribution.value is not None:
                opt = distribution.value
                opt = opt / max(opt.sum(), 1) * self._n_trajs
                self.optimized_start_end = np.maximum(opt, 0)
            else:
                self.optimized_start_end = np.ones((N, N)) / (N * N) * self._n_trajs

        except Exception:
            self.optimized_start_end = np.ones((N, N)) / (N * N)
            self.shortest_lengths = np.ones((N, N))

    def _build_2nd_order_and_stats(self, discrete):
        """2nd-order Markov + trip distribution + length distribution (ε3)."""
        N = self.N

        edge2_counts = np.zeros((N, N, N))
        trip_counts = np.zeros((N, N))
        len_counts = np.zeros(self.m_max + 1)

        for seq in discrete:
            for k in range(len(seq) - 2):
                edge2_counts[seq[k]][seq[k + 1]][seq[k + 2]] += 1
            if len(seq) >= 2:
                trip_counts[seq[0]][seq[-1]] += 1
            L = len(seq)
            if 2 <= L <= self.m_max:
                len_counts[L] += 1

        # ── Laplace noise on 2nd-order counts (ε3 sub: 2nd-order Markov) ──
        # Sensitivity = m_max: deleting one trajectory removes ≤ m_max trigrams
        # SINGLE noise generation for ALL N×N blocks (sequential composition: one query)
        total_2nd_elements = sum(edge2_counts[i,j].size for i in range(N) for j in range(N))
        all_2nd_noise = add_laplace_noise(
            np.zeros(total_2nd_elements), self.eps_2nd_markov, sensitivity=float(self.m_max))
        offset = 0
        self.noisy_edge2 = np.zeros_like(edge2_counts)
        for i in range(N):
            for j in range(N):
                n_el = edge2_counts[i, j].size
                self.noisy_edge2[i, j] = np.maximum(0,
                    edge2_counts[i, j] + all_2nd_noise[offset:offset+n_el])
                offset += n_el

        # ── Normalize 2nd-order transitions ───────────────────────────
        for si in range(N):
            for sj in range(N):
                rowvals = self.noisy_edge2[si, sj]
                s = rowvals.sum()
                if s > 0:
                    self.noisy_edge2[si, sj] /= s
                else:
                    self.noisy_edge2[si, sj] = self.trans1[sj].copy()

        # ── cvxpy convex optimization on 2nd-order conditionals ─────
        if HAS_CVXPY and N <= 50:
            n_opt = 0
            for si in range(N):
                for sj in range(N):
                    rowvals = self.noisy_edge2[si, sj]
                    if rowvals.sum() <= 0:
                        continue
                    if np.count_nonzero(rowvals > 1e-8) < 2:
                        continue
                    try:
                        opt_v = optimize_distribution_vector(rowvals)
                        if opt_v is not None:
                            self.noisy_edge2[si, sj] = opt_v
                            n_opt += 1
                    except Exception:
                        pass
            if n_opt > 0:
                print(f"        cvxpy optimized {n_opt} 2nd-order conditionals", flush=True)

        # ── Trip (start-end) distribution ─────────────────────────────
        # Sensitivity = 1: one trajectory contributes 1 to one start-end pair
        noisy_trip = add_laplace_noise(
            trip_counts.astype(float), self.eps_trip, sensitivity=1.0)
        noisy_trip = positive_regulation_for_markov_matrix(noisy_trip)
        trip_sum = noisy_trip.sum()
        self.trip_dist = (noisy_trip / trip_sum if trip_sum > 0
                          else np.ones((N, N)) / (N * N))

        # ── cvxpy convex optimization on OD (trip) distribution ──────
        if HAS_CVXPY:
            row_sums_trip = self.trip_dist.sum(axis=1, keepdims=True)
            row_sums_trip[row_sums_trip == 0] = 1
            trip_row_stoch = self.trip_dist / row_sums_trip
            trip_row_stoch = optimize_transition_matrix(trip_row_stoch)
            self.trip_dist = trip_row_stoch

        # ── Length distribution ───────────────────────────────────────
        # Sensitivity = 1: one trajectory contributes 1 to one length bin
        len_arr = len_counts[2:self.m_max + 1].astype(float)
        noisy_len = add_laplace_noise(
            len_arr, self.eps_len, sensitivity=1.0)
        noisy_len = positive_regulation(noisy_len)
        len_sum = noisy_len.sum()
        self.len_dist = noisy_len / len_sum if len_sum > 0 else np.ones(len(len_arr)) / len(len_arr)

    # ── Generation ────────────────────────────────────────────────────────

    def generate_1st_order(self, n_trajs=None):
        n = n_trajs or self._n_trajs
        N = self.N
        synthetic = []
        lens_avail = np.arange(2, self.m_max + 1)

        for _ in range(n):
            L = int(safe_choice(lens_avail, self.len_dist))
            L = max(L, 2)
            curr = safe_choice(np.arange(N), self.init_dist)
            path = [curr]
            for __ in range(L - 1):
                nxt = safe_choice(np.arange(N), self.trans1[curr])
                path.append(nxt)
                curr = nxt
            synthetic.append(self._path_to_coords(path))
        return synthetic

    def generate_2nd_order(self, n_trajs=None):
        n = n_trajs or self._n_trajs
        N = self.N
        synthetic = []
        lens_avail = np.arange(2, self.m_max + 1)

        for _ in range(n):
            L = int(safe_choice(lens_avail, self.len_dist))
            L = max(L, 2)
            first = safe_choice(np.arange(N), self.init_dist)
            path = [first]
            if L >= 2:
                second = safe_choice(np.arange(N), self.trans1[first])
                path.append(second)
            prev, curr = first, second if L >= 2 else first
            for __ in range(L - 2):
                nxt = safe_choice(np.arange(N), self.noisy_edge2[prev, curr])
                path.append(nxt)
                prev, curr = curr, nxt
            synthetic.append(self._path_to_coords(path))
        return synthetic

    def _path_to_coords(self, path):
        coords = []
        for sid in path:
            sid = min(sid, len(self.states) - 1)
            st = self.states[sid]
            lat = np.random.normal(st['lat'], COORD_SIGMA)
            lon = np.random.normal(st['lon'], COORD_SIGMA)
            lat = max(self.bbox['lat_min'], min(self.bbox['lat_max'], lat))
            lon = max(self.bbox['lon_min'], min(self.bbox['lon_max'], lon))
            coords.append([float(lat), float(lon)])
        return np.array(coords)


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_js(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
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


def compute_trans_l1(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
    M = grid_size * grid_size
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def grid_trans(trajs):
        trans = np.zeros((M, M))
        for t in trajs:
            for i in range(len(t) - 1):
                u = min(int((t[i][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v = min(int((t[i][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                u2 = min(int((t[i + 1][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v2 = min(int((t[i + 1][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                trans[u * grid_size + v, u2 * grid_size + v2] += 1
        return trans

    r_T = grid_trans(real)
    s_T = grid_trans(synthetic)
    r_norm = r_T / max(r_T.sum(), 1)
    s_norm = s_T / max(s_T.sum(), 1)
    return float(np.abs(r_norm - s_norm).sum() / 2)


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_experiment(model_factory, method_name, trajs, bbox, n_reps=N_REPS,
                   base_seed=RANDOM_SEED):
    print(f"\n    [{method_name}] Running {n_reps} reps...", flush=True)
    js_vals, tl1_vals = [], []
    js1_vals, tl1_1_vals = [], []
    js2_vals, tl1_2_vals = [], []
    elapsed_times = []

    for run_i in range(n_reps):
        try:
            seed = base_seed + run_i * 1000
            np.random.seed(seed)

            t0 = time.time()
            model = model_factory()
            model.fit(trajs)
            elapsed = time.time() - t0
            elapsed_times.append(elapsed)

            # Generate 1st-order trajectories
            syn1 = model.generate_1st_order(n_trajs=len(trajs))
            js1 = compute_js(trajs, syn1, bbox)
            tl1_1 = compute_trans_l1(trajs, syn1, bbox)
            js1_vals.append(js1)
            tl1_1_vals.append(tl1_1)

            # Generate 2nd-order trajectories
            syn2 = model.generate_2nd_order(n_trajs=len(trajs))
            js2 = compute_js(trajs, syn2, bbox)
            tl1_2 = compute_trans_l1(trajs, syn2, bbox)
            js2_vals.append(js2)
            tl1_2_vals.append(tl1_2)

            # Adaptive selection: pick order with lower JS
            if js1 <= js2:
                js_vals.append(js1)
                tl1_vals.append(tl1_1)
                sel_order = 1
            else:
                js_vals.append(js2)
                tl1_vals.append(tl1_2)
                sel_order = 2

            print(f"      rep {run_i + 1}/{n_reps}: "
                  f"JS1={js1:.6f} JS2={js2:.6f} "
                  f"→ select {sel_order}-order, best_JS={js_vals[-1]:.6f}, "
                  f"TL1={tl1_vals[-1]:.6f} ({elapsed:.1f}s)", flush=True)

            del model, syn1, syn2
            gc.collect()

        except Exception as e:
            print(f"      rep {run_i + 1}/{n_reps}: FAILED - {e}", flush=True)
            import traceback
            traceback.print_exc()

    if len(js_vals) == 0:
        return {'status': 'FAILED', 'n_success': 0, 'n_total': n_reps}

    return {
        'status': 'OK',
        'n_success': len(js_vals),
        'n_total': n_reps,
        'js_mean': float(np.mean(js_vals)),
        'js_std': float(np.std(js_vals, ddof=1)) if len(js_vals) > 1 else 0.0,
        'trans_l1_mean': float(np.mean(tl1_vals)),
        'trans_l1_std': float(np.std(tl1_vals, ddof=1)) if len(tl1_vals) > 1 else 0.0,
        'js_raw': [float(v) for v in js_vals],
        'trans_l1_raw': [float(v) for v in tl1_vals],
        'js_1st_order_mean': float(np.mean(js1_vals)),
        'js_1st_order_std': float(np.std(js1_vals, ddof=1)) if len(js1_vals) > 1 else 0.0,
        'tl1_1st_order_mean': float(np.mean(tl1_1_vals)),
        'tl1_1st_order_std': float(np.std(tl1_1_vals, ddof=1)) if len(tl1_1_vals) > 1 else 0.0,
        'js_2nd_order_mean': float(np.mean(js2_vals)),
        'js_2nd_order_std': float(np.std(js2_vals, ddof=1)) if len(js2_vals) > 1 else 0.0,
        'tl1_2nd_order_mean': float(np.mean(tl1_2_vals)),
        'tl1_2nd_order_std': float(np.std(tl1_2_vals, ddof=1)) if len(tl1_2_vals) > 1 else 0.0,
        'n_select_1st': sum(1 for a, b in zip(js1_vals, js2_vals) if a <= b),
        'n_select_2nd': sum(1 for a, b in zip(js1_vals, js2_vals) if a > b),
        'elapsed_mean': float(np.mean(elapsed_times)),
        'elapsed_std': float(np.std(elapsed_times, ddof=1)) if len(elapsed_times) > 1 else 0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    np.random.seed(RANDOM_SEED)

    print("=" * 80)
    print("PrivTrace & PrivTrace-RNDV — local paper-based reimplementation")
    print("USENIX Security 2023 (Wang et al.)")
    print(f"ε={EPSILON}, {N_REPS} reps, Laplace noise, cvxpy="
          f"{'YES' if HAS_CVXPY else 'NO (fallback)'}")
    print("=" * 80)

    methods = [
        {
            'key': 'privtrace',
            'label': 'PrivTrace',
            'budget': BUDGET_PRIVTRACE,
            'desc': 'K=12 adaptive grid [ε1=0.2, ε2=0.4, ε3=0.4] + '
                     '1st/2nd Markov + cvxpy',
        },
        {
            'key': 'privtrace_rndv',
            'label': 'PrivTrace-RNDV',
            'budget': BUDGET_RNDV,
            'desc': 'K=7 RNDV Voronoi (zero ε1) [ε1=0, ε2=0.5, ε3=0.5] + '
                     'same Markov pipeline',
        },
    ]

    results = {
        'experiment': 'privtrace_final',
        'description': (
            'Local paper-based PrivTrace-style implementation (USENIX Security 2023); not author-code-certified. '
            'PrivTrace: 2-level adaptive grid + Laplace + 1st/2nd Markov + cvxpy. '
            'PrivTrace-RNDV: RNDV Voronoi (zero ε1, OSM road density) + same pipeline. '
            'ε=1.0, 5 reps per method per city.'
        ),
        'config': {
            'epsilon': EPSILON,
            'K_grid': K_GRID,
            'K_rndv': K_RNDV,
            'm_max': M_MAX,
            'coord_sigma': COORD_SIGMA,
            'metric_grid_size': METRIC_GRID_SIZE,
            'n_reps': N_REPS,
            'random_seed': RANDOM_SEED,
            'noise_type': 'Laplace',
            'budget_privtrace': {
                'eps_grid': 0.2, 'eps_init': 0.04,
                'eps_1st_markov': 0.36, 'eps_trip': 0.04,
                'eps_2nd_markov': 0.32, 'eps_len': 0.04,
                'total': 1.0,
                'markov_sensitivity': M_MAX,
            },
            'budget_rndv': {
                'eps_grid': 0.0, 'eps_init': 0.05,
                'eps_1st_markov': 0.45, 'eps_trip': 0.05,
                'eps_2nd_markov': 0.40, 'eps_len': 0.05,
                'total': 1.0,
                'markov_sensitivity': M_MAX,
            },
            'cvxpy_available': HAS_CVXPY,
            'networkx_available': HAS_NETWORKX,
            'osm_used_for_rndv': True,
            'gaussian_kde_sigma': GAUSSIAN_KDE_SIGMA,
            'density_grid_size': DENSITY_GRID_SIZE,
        },
    }

    cities = ['beijing', 'porto', 'austin', 'london']

    for city_key in cities:
        cfg = CITY_CONFIGS[city_key]
        cfg_bbox = cfg['bbox']
        print(f"\n{'=' * 80}")
        print(f"CITY: {cfg['label']} ({city_key})")
        print("=" * 80)

        print(f"  Loading data...", flush=True)
        trajs, _ = load_data(city_key)
        n_trajs = len(trajs)
        lengths = [len(t) for t in trajs]
        print(f"    Loaded {n_trajs} trajectories")
        print(f"    Lengths: min={min(lengths)}, max={max(lengths)}, "
              f"avg={np.mean(lengths):.1f}", flush=True)

        city_results = {
            'label': cfg['label'],
            'n_trajs': n_trajs,
            'length_min': int(min(lengths)),
            'length_max': int(max(lengths)),
            'length_avg': float(np.mean(lengths)),
            'bbox': cfg_bbox,
        }

        # ── Precompute RNDV centers via OSM road density ───────────────
        rndv_centers = None
        rndv_osm_success = False
        print(f"  Querying OSM road network for RNDV...", flush=True)
        road_density, osm_ok = query_osm_road_density(cfg_bbox,
                                                       DENSITY_GRID_SIZE)
        if osm_ok and road_density.sum() > 10:
            rndv_centers = rndv_select_centers(cfg_bbox, road_density,
                                                K=K_RNDV,
                                                sigma=GAUSSIAN_KDE_SIGMA)
            rndv_osm_success = True
            print(f"    OSM success: {len(rndv_centers)} RNDV centers "
                  f"(secondary sub-centers included)", flush=True)
        else:
            print(f"    OSM failed or insufficient data, using fallback "
                  f"farthest-first selection", flush=True)
            rndv_centers = fallback_rndv_centers(cfg_bbox, K=K_RNDV)
        city_results['rndv_osm_success'] = rndv_osm_success
        city_results['rndv_n_centers'] = len(rndv_centers)

        # ── Run PrivTrace (original) ───────────────────────────────────
        print(f"\n  ── PrivTrace (adaptive grid, "
              f"budget={BUDGET_PRIVTRACE}) ──", flush=True)

        def make_privtrace():
            return PrivTraceModel(EPSILON, BUDGET_PRIVTRACE,
                                  K_grid=K_GRID, method_name='PrivTrace')

        pt_result = run_experiment(make_privtrace, 'privtrace', trajs, cfg_bbox)
        city_results['privtrace'] = pt_result

        if pt_result['status'] == 'OK':
            print(f"  PrivTrace RESULT: JS={pt_result['js_mean']:.6f}+/-"
                  f"{pt_result['js_std']:.6f} "
                  f"TL1={pt_result['trans_l1_mean']:.6f}+/-"
                  f"{pt_result['trans_l1_std']:.6f}")
            print(f"    1st-order: JS={pt_result['js_1st_order_mean']:.6f} "
                  f"TL1={pt_result['tl1_1st_order_mean']:.6f}")
            print(f"    2nd-order: JS={pt_result['js_2nd_order_mean']:.6f} "
                  f"TL1={pt_result['tl1_2nd_order_mean']:.6f}")
            print(f"    Selected: {pt_result['n_select_1st']}×1st "
                  f"{pt_result['n_select_2nd']}×2nd | "
                  f"Avg time: {pt_result['elapsed_mean']:.1f}s")

        # ── Run PrivTrace-RNDV ─────────────────────────────────────────
        print(f"\n  ── PrivTrace-RNDV (RNDV Voronoi, "
              f"budget={BUDGET_RNDV}) ──", flush=True)

        def make_rndv():
            return PrivTraceModel(EPSILON, BUDGET_RNDV,
                                  K_rndv=K_RNDV,
                                  rndv_centers=rndv_centers,
                                  method_name='PrivTrace-RNDV')

        rndv_result = run_experiment(make_rndv, 'privtrace_rndv', trajs, cfg_bbox)
        city_results['privtrace_rndv'] = rndv_result

        if rndv_result['status'] == 'OK':
            print(f"  PrivTrace-RNDV RESULT: JS={rndv_result['js_mean']:.6f}+/-"
                  f"{rndv_result['js_std']:.6f} "
                  f"TL1={rndv_result['trans_l1_mean']:.6f}+/-"
                  f"{rndv_result['trans_l1_std']:.6f}")
            print(f"    1st-order: JS={rndv_result['js_1st_order_mean']:.6f} "
                  f"TL1={rndv_result['tl1_1st_order_mean']:.6f}")
            print(f"    2nd-order: JS={rndv_result['js_2nd_order_mean']:.6f} "
                  f"TL1={rndv_result['tl1_2nd_order_mean']:.6f}")
            print(f"    Selected: {rndv_result['n_select_1st']}×1st "
                  f"{rndv_result['n_select_2nd']}×2nd | "
                  f"Avg time: {rndv_result['elapsed_mean']:.1f}s")

        results[city_key] = city_results

    # ── Summary table ───────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"\n{'City':<12} {'Method':<20} {'JS':>10} {'TL1':>10} "
          f"{'1st-JS':>10} {'2nd-JS':>10}")
    print("-" * 72)

    for city_key in cities:
        cr = results[city_key]
        for method_key, label in [('privtrace', 'PrivTrace'),
                                   ('privtrace_rndv', 'PrivTrace-RNDV')]:
            mr = cr.get(method_key, {})
            if mr.get('status') == 'OK':
                js = mr.get('js_mean', 0)
                tl1 = mr.get('trans_l1_mean', 0)
                js1 = mr.get('js_1st_order_mean', 0)
                js2 = mr.get('js_2nd_order_mean', 0)
                print(f"{cr.get('label', city_key):<12} {label:<20} "
                      f"{js:>10.6f} {tl1:>10.6f} {js1:>10.6f} {js2:>10.6f}")
            else:
                print(f"{cr.get('label', city_key):<12} {label:<20} {'FAILED':>10}")

    # ── Side-by-side comparison ─────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("DIRECT COMPARISON (RNDV vs PrivTrace Δ)")
    print("=" * 80)
    for city_key in cities:
        cr = results[city_key]
        pt = cr.get('privtrace', {})
        rndv = cr.get('privtrace_rndv', {})
        if pt.get('status') == 'OK' and rndv.get('status') == 'OK':
            djs = rndv['js_mean'] - pt['js_mean']
            dtl1 = rndv['trans_l1_mean'] - pt['trans_l1_mean']
            pct_js = (djs / max(pt['js_mean'], 1e-10)) * 100
            pct_tl1 = (dtl1 / max(pt['trans_l1_mean'], 1e-10)) * 100
            print(f"  {cr['label']:<12} ΔJS={djs:+.6f} ({pct_js:+.1f}%)  "
                  f"ΔTL1={dtl1:+.6f} ({pct_tl1:+.1f}%)")

    # ── Save ────────────────────────────────────────────────────────────
    out_path = os.path.join(OUTPUT_DIR, 'results.json')

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
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

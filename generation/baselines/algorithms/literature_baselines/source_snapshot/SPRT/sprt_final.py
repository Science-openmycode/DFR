"""
================================================================================
SPRT Final — local paper-based reimplementation of SPRT
+ RNDV Variant Comparison
================================================================================

SPRT Pipeline (all 5 steps per the paper):
  Step 1: Geography-aware grid construction (zero-ε, OSM-based)
  Step 2: Path extraction (GPS → cell centers → transition counts)
  Step 3: Laplace noise injection (Δf=m_max, b=Δf/ε, all ε on transition matrix)
  Step 4: Moveable constraint post-processing (T_noisy ⊙ A → re-normalize)
  Step 5: Constrained random walk trajectory synthesis (Gaussian jitter σ=0.02°)

RNDV Variant:
  - REPLACE Step 1: RNDV Voronoi partition from OSM road density
    (50×50 grid → Gaussian KDE σ=3 → select K=7 density peaks)
  - REPLACE Moveable constraint: Delaunay triangulation adjacency
  - Steps 2-5: IDENTICAL (same Laplace noise, same synthesis logic)

Cities: Beijing (GeoLife), Porto (Taxi CSV), Austin (Gowalla NPZ), London (Gowalla NPZ)
Config: ε=1.0, K=7 (RNDV), SPRT base 5×5, β=2.0, 5 reps, m_max=100
Metric: 12×12 grid JS divergence + Transition L1

Output: experiments/paper_comparison/final/sprt/results.json
================================================================================
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
from scipy.ndimage import gaussian_filter
from scipy.spatial import Delaunay
from scipy.spatial.distance import jensenshannon

# ── Path setup ───────────────────────────────────────────────────────────────
EXP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, EXP_DIR)

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════
M_MAX = 100               # Max trajectory length (points), Δf sensitivity bound
COORD_SIGMA = 0.02        # Gaussian jitter σ in degrees (~0.02° ≈ 2.2 km at equator)
METRIC_GRID_SIZE = 12     # 12×12 grid for JS divergence evaluation
N_REPS = 5                # Number of independent runs per method/city
EPSILON = 1.0             # Total privacy budget ε
RANDOM_SEED = 42          # Base random seed

# RNDV parameters
DENSITY_GRID_SIZE = 50    # 50×50 road density grid
GAUSSIAN_SIGMA = 3.0      # Gaussian KDE bandwidth (grid cells)
K_VORONOI = 7             # Number of RNDV Voronoi cells

# SPRT adaptive grid parameters
SPRT_BASE_GRID = 5        # 5×5 base administrative areas
SPRT_BETA = 2.0           # Granularity weight β: g_i = ⌈β * L(A_i)/S(A_i)⌉
SPRT_MAX_G = 8            # Maximum sub-divisions per base cell

MAX_TRAJS = 200           # Max trajectories to load per city

# Overpass API mirrors for OSM highway queries
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_HEADERS = {'User-Agent': 'opencode/1.0'}

# ═════════════════════════════════════════════════════════════════════════════
# CITY CONFIGURATIONS
# ═════════════════════════════════════════════════════════════════════════════
CITY_CONFIGS = {
    'beijing': {
        'label': 'Beijing (GeoLife)',
        'bbox': {'lat_min': 39.75, 'lat_max': 40.15,
                 'lon_min': 116.10, 'lon_max': 116.65},
        'loader': 'geolife',
        'data_path': os.path.join(EXP_DIR, 'datasets', 'geolife',
                                   'Geolife Trajectories 1.3', 'Data'),
    },
    'porto': {
        'label': 'Porto (Taxi)',
        'bbox': {'lat_min': 41.10, 'lat_max': 41.20,
                 'lon_min': -8.70, 'lon_max': -8.55},
        'loader': 'porto',
        'data_path': os.path.join(EXP_DIR, 'datasets', 'porto', 'train.csv'),
    },
    'austin': {
        'label': 'Austin (Gowalla)',
        'bbox': {'lat_min': 30.05, 'lat_max': 30.55,
                 'lon_min': -98.00, 'lon_max': -97.50},
        'loader': 'gowalla',
        'data_path': os.path.join(EXP_DIR, 'datasets', 'trajs_austin.npz'),
    },
    'london': {
        'label': 'London (Gowalla)',
        'bbox': {'lat_min': 51.30, 'lat_max': 51.70,
                 'lon_min': -0.50, 'lon_max': 0.20},
        'loader': 'gowalla',
        'data_path': os.path.join(EXP_DIR, 'datasets', 'trajs_london_5more.npz'),
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. GEOGRAPHIC UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km using Haversine formula."""
    RE = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return RE * c


def nearest_center_idx(point, centers):
    """Find index of nearest center to a [lat, lon] point."""
    dists = np.linalg.norm(centers - point, axis=1)
    return int(np.argmin(dists))


# ═════════════════════════════════════════════════════════════════════════════
# 2. DATA LOADING
# ═════════════════════════════════════════════════════════════════════════════

def load_geolife(data_path, bbox, max_trajs=MAX_TRAJS):
    """Load Beijing GeoLife .plt files. Skip 6-line header, parse lat/lon."""
    trajectories = []
    discarded = 0
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
                trajectories.append(np.array(points, dtype=np.float64))
                count += 1
            else:
                discarded += 1
    return trajectories, {'kept': len(trajectories), 'discarded': discarded}


def load_porto(data_path, bbox, max_trajs=MAX_TRAJS):
    """Load Porto taxi CSV. POLYLINE column contains JSON [[lon,lat],...]."""
    trajectories = []
    discarded = 0
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
                trajectories.append(np.array(points, dtype=np.float64))
                count += 1
            else:
                discarded += 1
    return trajectories, {'kept': len(trajectories), 'discarded': discarded}


def load_gowalla(npz_path, bbox, max_trajs=MAX_TRAJS):
    """Load Gowalla .npz trajectories (Austin, London)."""
    data = np.load(npz_path, allow_pickle=True)
    trajs = data['trajectories']
    kept = []
    discarded = 0
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
            kept.append(np.array(pts, dtype=np.float64))
        else:
            discarded += 1
    return kept, {'kept': len(kept), 'discarded': discarded}


def clip_trajectories(trajs, m_max=M_MAX):
    """Truncate each trajectory to at most m_max points."""
    return [t[:m_max] for t in trajs]


# ═════════════════════════════════════════════════════════════════════════════
# 3. OSM HIGHWAY QUERY (Overpass API)
# ═════════════════════════════════════════════════════════════════════════════

def query_osm_highways(bbox_dict, timeout=90):
    """Query Overpass API for all highway=* ways within bbox. Returns list of
    way elements with geometry. Tries multiple mirrors and GET/POST methods.
    Short timeout to avoid hanging on overloaded servers (falls back to grid)."""
    bbox_str = (f"{bbox_dict['lat_min']},{bbox_dict['lon_min']},"
                f"{bbox_dict['lat_max']},{bbox_dict['lon_max']}")
    query = f"""[out:json][timeout:60];
(
  way["highway"]({bbox_str});
);
out geom;"""
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


# ═════════════════════════════════════════════════════════════════════════════
# 4. ROAD DENSITY COMPUTATION (shared for RNDV)
# ═════════════════════════════════════════════════════════════════════════════

def compute_road_density_grid(ways, bbox_dict, grid_size=DENSITY_GRID_SIZE):
    """Compute road length density on a grid_size×grid_size raster.
    Each road segment distributes its length across 3 sample points (endpoints +
    midpoint), each weighted by seg_len/3. Used for RNDV center selection."""
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    density = np.zeros((grid_size, grid_size), dtype=np.float64)
    total_segments = 0
    total_length_km = 0.0
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
            total_segments += 1
            total_length_km += seg_len_km
    return density, total_segments, total_length_km


# ═════════════════════════════════════════════════════════════════════════════
# 5. RNDV: VORONOI CENTER SELECTION (RNDV Step 1)
# ═════════════════════════════════════════════════════════════════════════════

def select_centers_rndv(density_smooth, bbox_dict, K=K_VORONOI):
    """Select K cell centers from smoothed road density grid.
    Picks top-K density peaks, enforcing minimum spatial separation
    (1.5× cell diagonal) to avoid clustered centers."""
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
        if len(centers) >= K:
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
    # Fallback: fill remaining slots with remaining highest-density cells
    if len(centers) < K:
        for idx in sorted_indices:
            if len(centers) >= K:
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


def build_delaunay_adjacency(centers):
    """Build adjacency matrix from Delaunay triangulation of cell centers.
    Used as moveable constraint for SPRT-RNDV variant."""
    N = len(centers)
    if N < 3:
        A = np.ones((N, N), dtype=int)
        np.fill_diagonal(A, 0)
        for i in range(N):
            A[i, i] = 1
        return A
    tri = Delaunay(centers)
    A = np.zeros((N, N), dtype=int)
    for simplex in tri.simplices:
        for i in range(3):
            for j in range(i + 1, 3):
                a, b = simplex[i], simplex[j]
                A[a, b] = 1
                A[b, a] = 1
    for i in range(N):
        if A[i].sum() == 0:
            A[i, i] = 1  # prevent isolated cells
    return A


def fallback_grid_centers(bbox_dict, K=K_VORONOI):
    """Generate uniformly-spaced centers when OSM query fails.
    Uses a K-sparse grid covering the bbox."""
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    G = int(math.ceil(math.sqrt(K * 4)))
    lat_step = (lat_max - lat_min) / G
    lon_step = (lon_max - lon_min) / G
    pts = []
    for i in range(G):
        for j in range(G):
            pts.append([lat_min + (i + 0.5) * lat_step,
                       lon_min + (j + 0.5) * lon_step])
    pts = np.array(pts)
    center_pt = np.array([(lat_min + lat_max) / 2,
                          (lon_min + lon_max) / 2])
    first = int(np.argmin(np.linalg.norm(pts - center_pt, axis=1)))
    selected = [pts[first].copy()]
    sel_idx = {first}
    while len(selected) < K:
        sel_arr = np.array(selected)
        best_idx = -1
        best_min = -float('inf')
        for i, p in enumerate(pts):
            if i in sel_idx:
                continue
            d = np.min(np.linalg.norm(sel_arr - p, axis=1))
            if d > best_min:
                best_min = d
                best_idx = i
        if best_idx < 0:
            break
        selected.append(pts[best_idx].copy())
        sel_idx.add(best_idx)
    return np.array(selected[:K])


# ═════════════════════════════════════════════════════════════════════════════
# 6. SPRT STEP 1: GEOGRAPHY-AWARE ADAPTIVE GRID CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════════════

def point_in_rect(lat, lon, lat_min, lat_max, lon_min, lon_max):
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def road_intersects_rect(ways, lat_min, lat_max, lon_min, lon_max):
    """Check if any road way has geometry intersecting a lat/lon rectangle."""
    for way in ways:
        geom = way.get('geometry', [])
        for pt in geom:
            if point_in_rect(pt['lat'], pt['lon'],
                             lat_min, lat_max, lon_min, lon_max):
                return True
        for i in range(len(geom) - 1):
            p1, p2 = geom[i], geom[i + 1]
            mid_lat = (p1['lat'] + p2['lat']) / 2
            mid_lon = (p1['lon'] + p2['lon']) / 2
            if point_in_rect(mid_lat, mid_lon,
                             lat_min, lat_max, lon_min, lon_max):
                return True
    return False


def road_length_in_rect(ways, lat_min, lat_max, lon_min, lon_max):
    """Sum length of road segments whose midpoint falls within rectangle."""
    total = 0.0
    for way in ways:
        geom = way.get('geometry', [])
        for i in range(len(geom) - 1):
            p1, p2 = geom[i], geom[i + 1]
            mid_lat = (p1['lat'] + p2['lat']) / 2
            mid_lon = (p1['lon'] + p2['lon']) / 2
            if point_in_rect(mid_lat, mid_lon,
                             lat_min, lat_max, lon_min, lon_max):
                total += haversine_km(p1['lat'], p1['lon'],
                                      p2['lat'], p2['lon'])
    return total


def rect_area_km2(lat_min, lat_max, lon_min, lon_max):
    """Approximate area of lat/lon rectangle in km^2."""
    width_km = haversine_km(lat_min, lon_min, lat_min, lon_max)
    height_km = haversine_km(lat_min, lon_min, lat_max, lon_min)
    return max(width_km * height_km, 1e-6)


def build_sprt_adaptive_grid(ways, bbox_dict,
                              base_grid=SPRT_BASE_GRID, beta=SPRT_BETA):
    """
    SPRT Step 1: Geography-aware grid construction.

    Procedure (per Section IV-B of the paper):
      a) Divide bbox into base_grid×base_grid coarse regions (like admin areas)
      b) For each region A_i, compute granularity:
         g_i = ⌈β * L(A_i) / S(A_i)⌉
         where L = total road length, S = area in km^2
      c) Subdivide each region into g_i×g_i equal-area sub-cells
      d) Remove sub-cells that contain no road segments (infeasible)
      e) Record center coordinates of each remaining cell
      f) Build adjacency matrix A for moveable constraint:
         - Cells in same base region are all mutually reachable
         - Cells in adjacent (8-neighbor) base regions are reachable if
           sub-cells share a boundary or corner

    Returns:
        cell_centers: (N, 2) array of [lat, lon] centers
        adjacency: (N, N) binary adjacency matrix
        info: dict with grid statistics
    """
    lat_min, lat_max = bbox_dict['lat_min'], bbox_dict['lat_max']
    lon_min, lon_max = bbox_dict['lon_min'], bbox_dict['lon_max']
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min

    cell_centers = []
    cell_bounds = []
    cell_row_col = []

    for r in range(base_grid):
        for c in range(base_grid):
            # Coarse region bounds
            c_lat_min = lat_min + r * lat_span / base_grid
            c_lat_max = lat_min + (r + 1) * lat_span / base_grid
            c_lon_min = lon_min + c * lon_span / base_grid
            c_lon_max = lon_min + (c + 1) * lon_span / base_grid

            area_km2 = rect_area_km2(c_lat_min, c_lat_max,
                                     c_lon_min, c_lon_max)
            r_length = road_length_in_rect(ways, c_lat_min, c_lat_max,
                                           c_lon_min, c_lon_max)

            # g_i = ⌈β * L(A_i) / S(A_i)⌉, at least 1, capped at SPRT_MAX_G
            g_i = max(1, int(math.ceil(beta * r_length / area_km2)))
            g_i = min(g_i, SPRT_MAX_G)

            # Subdivide into g_i×g_i sub-cells
            for si in range(g_i):
                for sj in range(g_i):
                    sc_lat_min = c_lat_min + si * (c_lat_max - c_lat_min) / g_i
                    sc_lat_max = c_lat_min + (si + 1) * (c_lat_max - c_lat_min) / g_i
                    sc_lon_min = c_lon_min + sj * (c_lon_max - c_lon_min) / g_i
                    sc_lon_max = c_lon_min + (sj + 1) * (c_lon_max - c_lon_min) / g_i

                    # Remove cells without roads (infeasible cell removal)
                    if not road_intersects_rect(ways, sc_lat_min, sc_lat_max,
                                                sc_lon_min, sc_lon_max):
                        continue

                    center_lat = (sc_lat_min + sc_lat_max) / 2
                    center_lon = (sc_lon_min + sc_lon_max) / 2
                    cell_centers.append([center_lat, center_lon])
                    cell_bounds.append((sc_lat_min, sc_lat_max,
                                        sc_lon_min, sc_lon_max))
                    cell_row_col.append((r, c, si, sj))

    n_cells = len(cell_centers)
    # Safety: if no cells, use center of bbox
    if n_cells == 0:
        cell_centers.append([(lat_min + lat_max) / 2,
                             (lon_min + lon_max) / 2])
        cell_bounds.append((lat_min, lat_max, lon_min, lon_max))
        cell_row_col.append((0, 0, 0, 0))
        n_cells = 1

    cell_centers = np.array(cell_centers)

    # Build adjacency matrix (moveable constraint A)
    adjacency = np.zeros((n_cells, n_cells), dtype=int)
    for i in range(n_cells):
        bi = cell_bounds[i]
        ri, ci, si_i, sj_i = cell_row_col[i]
        for j in range(i + 1, n_cells):
            bj = cell_bounds[j]
            rj, cj, si_j, sj_j = cell_row_col[j]

            # Rule 1: Same base region → all sub-cells are connected
            if ri == rj and ci == cj:
                adjacency[i, j] = 1
                adjacency[j, i] = 1
                continue

            # Rule 2: Adjacent base regions (8-neighbor) + boundary touching
            dr = abs(ri - rj)
            dc = abs(ci - cj)
            if dr <= 1 and dc <= 1 and not (dr == 0 and dc == 0):
                lat_overlap = not (bi[1] <= bj[0] or bj[1] <= bi[0])
                lon_overlap = not (bi[3] <= bj[2] or bj[3] <= bi[2])
                lat_touch = (abs(bi[1] - bj[0]) < 1e-7 or
                             abs(bj[1] - bi[0]) < 1e-7)
                lon_touch = (abs(bi[3] - bj[2]) < 1e-7 or
                             abs(bj[3] - bi[2]) < 1e-7)
                if ((lat_touch and lon_overlap) or
                    (lon_touch and lat_overlap) or
                    (lat_touch and lon_touch)):
                    adjacency[i, j] = 1
                    adjacency[j, i] = 1

    # Prevent isolated cells (self-loop fallback)
    for i in range(n_cells):
        if adjacency[i].sum() == 0:
            adjacency[i, i] = 1

    n_edges = int(adjacency.sum()) // 2
    max_possible = n_cells * (n_cells - 1) / 2 if n_cells > 1 else 1

    return cell_centers, adjacency, {
        'n_cells': n_cells,
        'n_edges': n_edges,
        'density': float(n_edges / max_possible),
        'base_grid': base_grid,
        'beta': beta,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 7. SPRT MODEL: STEPS 2-5 (Path Extraction → Laplace → Constraint → Synthesis)
# ═════════════════════════════════════════════════════════════════════════════

class SPRTModel:
    """
    SPRT Steps 2-5 as a unified model.
    This is the core DP trajectory synthesis engine shared by both
    SPRT (adaptive grid) and SPRT-RNDV (Voronoi partition).

    Step 2: Path extraction — map GPS points to nearest cell centers,
            extract cell sequences, count pairwise transitions.
            A trajectory of length L contributes L-1 transition pairs.
    Step 3: Laplace noise — add independent Laplace(0, b) to each
            element of the transition count matrix.
            Sensitivity Δf = m_max, noise scale b = Δf / ε.
    Step 4: Moveable constraint — zero out unreachable cell pairs
            (T_noisy = T_noisy ⊙ A), then re-normalize each row.
    Step 5: Constrained random walk synthesis — sample start from
            init distribution, sample length from length distribution,
            perform Markov chain constrained to adjacency, add
            Gaussian(σ=0.02°) jitter to cell centers for coordinates.
    """

    def __init__(self, epsilon, centers, adjacency_matrix, bbox_tuple):
        self.epsilon = epsilon
        self.m_max = M_MAX
        self.centers = np.array(centers, dtype=np.float64)
        self.K = len(self.centers)
        self.adjacency_matrix = adjacency_matrix.copy().astype(int)
        self.bbox = bbox_tuple  # (lat_min, lat_max, lon_min, lon_max)
        self.coord_sigma = COORD_SIGMA

    def _nearest_center(self, point):
        return nearest_center_idx(point, self.centers)

    def fit(self, trajectories):
        """
        Execute Steps 2-4 on the input trajectories.
        Stores transition probabilities, init distribution, and length
        distribution for later generation.
        """
        self._n_trajs = len(trajectories)
        clipped = [t[:self.m_max] for t in trajectories]
        K = self.K

        # ── Step 2: Path extraction ─────────────────────────────────────────
        # Map each GPS point to its nearest cell center, extract cell sequences,
        # and count all pairwise transitions.
        # A trajectory of L points produces L-1 transition pairs.
        trans_counts = np.zeros((K, K), dtype=np.float64)
        raw_lengths = []

        for traj in clipped:
            cells = [self._nearest_center(p) for p in traj]
            for i in range(len(cells) - 1):
                trans_counts[cells[i]][cells[i + 1]] += 1
            raw_lengths.append(len(cells))

        # Length distribution: build raw counts first
        len_arr = np.array(raw_lengths)
        len_counts = np.zeros(self.m_max - 1, dtype=np.float64)
        for L in range(2, self.m_max + 1):
            idx = L - 2
            count = np.sum(len_arr == L)
            len_counts[idx] = count

        # Init distribution: raw counts
        init_counts = np.zeros(K, dtype=np.float64)
        for traj in clipped:
            if len(traj) > 0:
                c = self._nearest_center(traj[0])
                init_counts[c] += 1.0

        # ── Step 3: Laplace noise injection ─────────────────────────────────
        # Budget allocation: trans 90% + init 5% + length 5%
        # Each statistic is ONE query (no per-element splitting)
        # L1 sensitivity: trans = m_max, init = 1, length = 1
        eps_trans = 0.9 * self.epsilon
        eps_init = 0.05 * self.epsilon
        eps_length = 0.05 * self.epsilon

        # Transition matrix: whole matrix as ONE query, b = m_max / eps_trans
        b_trans = self.m_max / eps_trans
        noisy_trans = trans_counts + np.random.laplace(0.0, b_trans, (K, K))
        noisy_trans = np.maximum(0.0, noisy_trans)

        # Init distribution: ONE query, b = 1.0 / eps_init
        b_init = 1.0 / eps_init
        init_noisy = init_counts + np.random.laplace(0.0, b_init, K)
        init_noisy = np.maximum(0.0, init_noisy)
        init_sum = init_noisy.sum()
        if init_sum > 0:
            self.init_dist = init_noisy / init_sum
        else:
            self.init_dist = np.ones(K) / K

        # Length distribution: ONE query, b = 1.0 / eps_length
        n_len_bins = len(len_counts)
        b_len = 1.0 / eps_length
        len_noisy = len_counts + np.random.laplace(0.0, b_len, n_len_bins)
        len_noisy = np.maximum(0.0, len_noisy)
        len_sum = len_noisy.sum()
        if len_sum > 0:
            self.len_dist = len_noisy / len_sum
        else:
            self.len_dist = np.ones(self.m_max - 1) / (self.m_max - 1)

        # ── Step 4: Moveable constraint post-processing ──────────────────────
        # T_noisy = T_noisy ⊙ A  (Hadamard product with adjacency matrix)
        # Zero out transitions between unreachable cell pairs, then re-normalize
        # each row to form valid transition probabilities.
        noisy_trans = noisy_trans * self.adjacency_matrix.astype(float)
        row_sums = noisy_trans.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        self.trans_probs = noisy_trans / row_sums

    def generate(self, n_trajs=None):
        """
        Step 5: Constrained random walk trajectory synthesis.

        For each synthetic trajectory:
          1. Sample length from stored length distribution (≥2)
          2. Sample start cell from init distribution
          3. Perform Markov chain random walk:
             - At each step, sample next cell from current cell's
               transition probabilities, constrained to only reachable
               cells (per adjacency matrix)
          4. Convert cell path to coordinates:
             - Sample lat/lon from Gaussian(center, σ=0.02°)
             - Clamp to bbox bounds
        """
        n = n_trajs or self._n_trajs
        K = self.K
        synthetic = []

        lengths_available = np.arange(2, self.m_max + 1)
        len_p = self.len_dist / max(self.len_dist.sum(), 1e-10)

        init_p = self.init_dist / max(self.init_dist.sum(), 1e-10)

        lat_min, lat_max, lon_min, lon_max = self.bbox

        for _ in range(n):
            # Sample length (at least 2 points)
            if len_p.sum() < 1e-15:
                length = 2
            else:
                length = int(np.random.choice(lengths_available, p=len_p))
                length = max(length, 2)

            # Sample start cell
            if init_p.sum() < 1e-15:
                start = np.random.randint(0, K)
            else:
                start = np.random.choice(K, p=init_p)

            path = [start]
            cur = start

            # Constrained random walk
            for __ in range(length - 1):
                reachable = np.where(self.adjacency_matrix[cur] > 0)[0]
                if len(reachable) == 0:
                    break
                # Extract transition probabilities for reachable cells only
                probs = self.trans_probs[cur][reachable].copy()
                if probs.sum() < 1e-10:
                    probs = np.ones(len(reachable)) / len(reachable)
                else:
                    probs /= probs.sum()
                cur = np.random.choice(reachable, p=probs)
                path.append(cur)

            # Convert cell path to GPS coordinates with Gaussian jitter
            coords = []
            for c in path:
                lat = np.random.normal(self.centers[c][0], self.coord_sigma)
                lon = np.random.normal(self.centers[c][1], self.coord_sigma)
                lat = max(lat_min, min(lat_max, lat))
                lon = max(lon_min, min(lon_max, lon))
                coords.append([float(lat), float(lon)])
            synthetic.append(np.array(coords, dtype=np.float64))

        return synthetic


# ═════════════════════════════════════════════════════════════════════════════
# 8. EVALUATION METRICS
# ═════════════════════════════════════════════════════════════════════════════

def compute_js_divergence(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
    """Jensen-Shannon divergence on a grid_size×grid_size spatial histogram.
    Computes 2D histogram of all point locations, normalizes to probability
    distributions, then computes JS(P_real || P_synthetic)."""
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def grid_hist(trajs):
        hist = np.zeros((grid_size, grid_size), dtype=np.float64)
        for t in trajs:
            for p in t:
                li = min(int((p[0] - lat_min) / lat_span * grid_size),
                         grid_size - 1)
                lj = min(int((p[1] - lon_min) / lon_span * grid_size),
                         grid_size - 1)
                hist[li, lj] += 1.0
        return hist.flatten()

    r_hist = grid_hist(real)
    s_hist = grid_hist(synthetic)
    r_norm = r_hist / max(r_hist.sum(), 1.0)
    s_norm = s_hist / max(s_hist.sum(), 1.0)
    js = jensenshannon(r_norm, s_norm)
    return float(js) if not np.isnan(js) else 1.0


def compute_trans_l1(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
    """L1 distance between transition matrices on a discretized grid.
    Each cell is a grid_size×grid_size spatial bin; transitions between
    bins form an N×N matrix (N = grid_size^2). Returns normalized L1/2
    (equivalent to total variation distance)."""
    N = grid_size * grid_size
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def grid_trans(trajs):
        trans = np.zeros((N, N), dtype=np.float64)
        for t in trajs:
            for i in range(len(t) - 1):
                u = min(int((t[i][0] - lat_min) / lat_span * grid_size),
                        grid_size - 1) * grid_size
                u += min(int((t[i][1] - lon_min) / lon_span * grid_size),
                         grid_size - 1)
                v = min(int((t[i + 1][0] - lat_min) / lat_span * grid_size),
                        grid_size - 1) * grid_size
                v += min(int((t[i + 1][1] - lon_min) / lon_span * grid_size),
                         grid_size - 1)
                trans[u, v] += 1.0
        return trans

    r_T = grid_trans(real)
    s_T = grid_trans(synthetic)
    r_norm = r_T / max(r_T.sum(), 1.0)
    s_norm = s_T / max(s_T.sum(), 1.0)
    return float(np.abs(r_norm - s_norm).sum() / 2.0)


def compute_length_dist_jsd(real, synthetic):
    """JSD between length distributions of real and synthetic trajectories."""
    r_lens = np.array([len(t) for t in real], dtype=int)
    s_lens = np.array([len(t) for t in synthetic], dtype=int)
    max_len = max(int(r_lens.max()) if len(r_lens) > 0 else 100,
                  int(s_lens.max()) if len(s_lens) > 0 else 100)
    bins = np.arange(1, max_len + 2)
    r_hist, _ = np.histogram(r_lens, bins=bins)
    s_hist, _ = np.histogram(s_lens, bins=bins)
    r_norm = r_hist.astype(float) / max(r_hist.sum(), 1.0)
    s_norm = s_hist.astype(float) / max(s_hist.sum(), 1.0)
    js = jensenshannon(r_norm, s_norm)
    return float(js) if not np.isnan(js) else 1.0


def compute_diameter_dist_jsd(real, synthetic):
    """JSD between trajectory diameter (start→end Haversine distance) distributions."""
    def diameters(trajs):
        ds = []
        for t in trajs:
            if len(t) >= 2:
                ds.append(haversine_km(t[0][0], t[0][1], t[-1][0], t[-1][1]))
        return np.array(ds)
    r_d = diameters(real)
    s_d = diameters(synthetic)
    if len(r_d) == 0 or len(s_d) == 0:
        return 1.0
    max_d = max(r_d.max(), s_d.max(), 1.0)
    bins = np.linspace(0, max_d, 21)
    r_hist, _ = np.histogram(r_d, bins=bins)
    s_hist, _ = np.histogram(s_d, bins=bins)
    r_norm = r_hist.astype(float) / max(r_hist.sum(), 1.0)
    s_norm = s_hist.astype(float) / max(s_hist.sum(), 1.0)
    js = jensenshannon(r_norm, s_norm)
    return float(js) if not np.isnan(js) else 1.0


def compute_density_are(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
    """Average Relative Error of per-cell trajectory density on a grid."""
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def cell_density(trajs):
        dens = np.zeros((grid_size, grid_size), dtype=np.float64)
        for t in trajs:
            for p in t:
                li = min(int((p[0] - lat_min) / lat_span * grid_size), grid_size - 1)
                lj = min(int((p[1] - lon_min) / lon_span * grid_size), grid_size - 1)
                dens[li, lj] += 1.0
        return dens

    r_dens = cell_density(real)
    s_dens = cell_density(synthetic)
    denom = np.maximum(r_dens, 1.0)
    errors = np.abs(r_dens - s_dens) / denom
    return float(np.mean(errors))


def compute_trans_are(real, synthetic, bbox, grid_size=METRIC_GRID_SIZE):
    """Average Relative Error of cell-to-cell transition probability matrix."""
    N = grid_size * grid_size
    lat_min, lat_max = bbox['lat_min'], bbox['lat_max']
    lon_min, lon_max = bbox['lon_min'], bbox['lon_max']
    lat_span = max(lat_max - lat_min, 1e-10)
    lon_span = max(lon_max - lon_min, 1e-10)

    def grid_trans(trajs):
        trans = np.zeros((N, N), dtype=np.float64)
        for t in trajs:
            for i in range(len(t) - 1):
                u = min(int((t[i][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v = min(int((t[i][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                u2 = min(int((t[i+1][0] - lat_min) / lat_span * grid_size), grid_size - 1)
                v2 = min(int((t[i+1][1] - lon_min) / lon_span * grid_size), grid_size - 1)
                trans[u * grid_size + v, u2 * grid_size + v2] += 1.0
        return trans

    r_T = grid_trans(real)
    s_T = grid_trans(synthetic)
    r_T_flat = r_T.flatten()
    s_T_flat = s_T.flatten()
    denom = np.maximum(r_T_flat, 1.0)
    errors = np.abs(r_T_flat - s_T_flat) / denom
    return float(np.mean(errors))


# ═════════════════════════════════════════════════════════════════════════════
# 9. EXPERIMENT RUNNER
# ═════════════════════════════════════════════════════════════════════════════

def run_one_method(method_name, model_factory, trajs, bbox_dict,
                   n_reps=N_REPS, base_seed=RANDOM_SEED):
    """Run a single method for n_reps independent trials.
    Each trial fits the model and generates synthetic trajectories,
    then evaluates JS divergence, Transition L1, and 4 extended metrics."""
    js_vals, tl1_vals = [], []
    len_jsd_vals, diam_jsd_vals = [], []
    dens_are_vals, trans_are_vals = [], []
    for run_i in range(n_reps):
        seed = base_seed + run_i * 1000
        np.random.seed(seed)
        try:
            t0 = time.time()
            model = model_factory()
            model.fit(trajs)
            synthetic = model.generate(n_trajs=len(trajs))
            elapsed = time.time() - t0
            js = compute_js_divergence(trajs, synthetic, bbox=bbox_dict)
            tl1 = compute_trans_l1(trajs, synthetic, bbox=bbox_dict)
            len_jsd = compute_length_dist_jsd(trajs, synthetic)
            diam_jsd = compute_diameter_dist_jsd(trajs, synthetic)
            dens_are = compute_density_are(trajs, synthetic, bbox=bbox_dict)
            trans_are = compute_trans_are(trajs, synthetic, bbox=bbox_dict)
            js_vals.append(js)
            tl1_vals.append(tl1)
            len_jsd_vals.append(len_jsd)
            diam_jsd_vals.append(diam_jsd)
            dens_are_vals.append(dens_are)
            trans_are_vals.append(trans_are)
            print(f"  [{method_name}] r{run_i+1}/{n_reps} (seed={seed}): "
                  f"JS={js:.6f} TL1={tl1:.6f} "
                  f"LenJSD={len_jsd:.6f} DiamJSD={diam_jsd:.6f} "
                  f"DensARE={dens_are:.6f} TransARE={trans_are:.6f} "
                  f"({elapsed:.1f}s)", flush=True)
            del model, synthetic
            gc.collect()
        except Exception as e:
            print(f"  [{method_name}] r{run_i+1}/{n_reps}: FAILED - {e}",
                  flush=True)
            import traceback
            traceback.print_exc()

    if len(js_vals) == 0:
        return {'status': 'FAILED', 'n_success': 0, 'n_total': n_reps}

    js_arr = np.array(js_vals)
    tl1_arr = np.array(tl1_vals)
    len_jsd_arr = np.array(len_jsd_vals)
    diam_jsd_arr = np.array(diam_jsd_vals)
    dens_are_arr = np.array(dens_are_vals)
    trans_are_arr = np.array(trans_are_vals)
    return {
        'status': 'OK',
        'n_success': len(js_vals),
        'n_total': n_reps,
        'js_mean': float(np.mean(js_arr)),
        'js_std': float(np.std(js_arr, ddof=1)) if len(js_vals) > 1 else 0.0,
        'trans_l1_mean': float(np.mean(tl1_arr)),
        'trans_l1_std': float(np.std(tl1_arr, ddof=1)) if len(tl1_arr) > 1 else 0.0,
        'len_jsd_mean': float(np.mean(len_jsd_arr)),
        'len_jsd_std': float(np.std(len_jsd_arr, ddof=1)) if len(len_jsd_arr) > 1 else 0.0,
        'diam_jsd_mean': float(np.mean(diam_jsd_arr)),
        'diam_jsd_std': float(np.std(diam_jsd_arr, ddof=1)) if len(diam_jsd_arr) > 1 else 0.0,
        'dens_are_mean': float(np.mean(dens_are_arr)),
        'dens_are_std': float(np.std(dens_are_arr, ddof=1)) if len(dens_are_arr) > 1 else 0.0,
        'trans_are_mean': float(np.mean(trans_are_arr)),
        'trans_are_std': float(np.std(trans_are_arr, ddof=1)) if len(trans_are_arr) > 1 else 0.0,
        'js_raw': [float(v) for v in js_vals],
        'trans_l1_raw': [float(v) for v in tl1_vals],
        'len_jsd_raw': [float(v) for v in len_jsd_vals],
        'diam_jsd_raw': [float(v) for v in diam_jsd_vals],
        'dens_are_raw': [float(v) for v in dens_are_vals],
        'trans_are_raw': [float(v) for v in trans_are_vals],
    }


# ═════════════════════════════════════════════════════════════════════════════
# 10. MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    np.random.seed(RANDOM_SEED)

    results = {
        'experiment': 'sprt_final',
        'description': (
            'SPRT (Sun et al., IEEE TITS 2023) local paper-based reimplementation '
            'with all 5 steps: (1) geography-aware adaptive grid from OSM, '
            '(2) path extraction, (3) Laplace noise on transition matrix '
            '(Δf=m_max=100, b=Δf/ε, all ε=1.0), (4) moveable constraint '
            'post-processing (T_noisy ⊙ A, re-normalize), (5) constrained '
            'random walk synthesis with Gaussian(σ=0.02°) jitter. '
            'SPRT-RNDV variant: replace Step 1 with RNDV Voronoi partition '
            '(50×50 density grid → Gaussian KDE σ=3 → K=7 density peaks) '
            '+ Delaunay adjacency; Steps 2-5 identical.'
        ),
        'config': {
            'epsilon': EPSILON,
            'm_max': M_MAX,
            'coord_sigma_deg': COORD_SIGMA,
            'metric_grid_size': METRIC_GRID_SIZE,
            'n_reps': N_REPS,
            'random_seed': RANDOM_SEED,
            'sprt_base_grid': SPRT_BASE_GRID,
            'sprt_beta': SPRT_BETA,
            'sprt_max_g': SPRT_MAX_G,
            'rndv_K': K_VORONOI,
            'rndv_density_grid': DENSITY_GRID_SIZE,
            'rndv_gaussian_sigma': GAUSSIAN_SIGMA,
            'noise_mechanism': 'Laplace(0, b) with b = m_max / epsilon',
            'sensitivity_delta_f': M_MAX,
            'budget_allocation': '0.90 transition + 0.05 init + 0.05 length (not full epsilon to transition)',
        },
        'cities': {},
    }

    # ═════════════════════════════════════════════════════════════════════
    # PHASE 0: Load all data
    # ═════════════════════════════════════════════════════════════════════
    print("=" * 80)
    print("SPRT Final — Faithful Reimplementation (Laplace Noise)")
    print("=" * 80)
    print("\n" + "=" * 80)
    print("PHASE 0: DATA LOADING")
    print("=" * 80)

    city_data = {}
    for city_key, cfg in CITY_CONFIGS.items():
        print(f"\n  Loading {cfg['label']}...")
        bbox = cfg['bbox']
        if cfg['loader'] == 'geolife':
            trajs, stats = load_geolife(cfg['data_path'], bbox)
        elif cfg['loader'] == 'porto':
            trajs, stats = load_porto(cfg['data_path'], bbox)
        elif cfg['loader'] == 'gowalla':
            trajs, stats = load_gowalla(cfg['data_path'], bbox)
        else:
            continue
        trajs = clip_trajectories(trajs)
        lengths = [len(t) for t in trajs]
        print(f"    Kept: {stats['kept']}, Discarded: {stats['discarded']}")
        print(f"    Lengths: min={min(lengths)}, max={max(lengths)}, "
              f"avg={np.mean(lengths):.1f}")
        city_data[city_key] = {
            'trajs': trajs,
            'stats': stats,
            'bbox': bbox,
            'label': cfg['label'],
        }

    # ═════════════════════════════════════════════════════════════════════
    # PHASE 1-2: OSM queries + Grid construction + Experiment runs
    # ═════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("PHASE 1-2: OSM QUERIES + GRID CONSTRUCTION + EXPERIMENTS")
    print("=" * 80)

    for city_key in city_data:
        city_info = city_data[city_key]
        trajs = city_info['trajs']
        bbox = city_info['bbox']
        label = city_info['label']
        bbox_tuple = (bbox['lat_min'], bbox['lat_max'],
                      bbox['lon_min'], bbox['lon_max'])

        print(f"\n{'=' * 60}")
        print(f"  CITY: {label} ({city_key})")
        print(f"{'=' * 60}")

        city_result = {
            'label': label,
            'bbox': bbox,
            'n_trajs': len(trajs),
            'data_stats': city_info['stats'],
        }

        # ── OSM Query (shared) ──────────────────────────────────────────
        ways, source_url = query_osm_highways(bbox)

        if ways is None or len(ways) == 0:
            print(f"  OSM highway query FAILED. Using fallback grid.",
                  flush=True)
            city_result['osm_status'] = 'FAILED'
            city_result['osm_source'] = None

            fallback_centers = fallback_grid_centers(bbox, K=K_VORONOI)
            N_fb = len(fallback_centers)
            fallback_adj = np.ones((N_fb, N_fb), dtype=int)
            np.fill_diagonal(fallback_adj, 0)
            for i in range(N_fb):
                fallback_adj[i, i] = 1

            # SPRT fallback
            def make_sprt_fb(c=fallback_centers, bt=bbox_tuple,
                             a=fallback_adj):
                return SPRTModel(EPSILON, c, a, bt)
            sprt_res = run_one_method(f"SPRT_{city_key}", make_sprt_fb,
                                       trajs, bbox, N_REPS)
            city_result['SPRT'] = sprt_res
            city_result['SPRT_grid_info'] = {'n_cells': N_fb, 'fallback': True}

            # SPRT-RNDV fallback
            rndv_adj = build_delaunay_adjacency(fallback_centers)
            def make_rndv_fb(c=fallback_centers, bt=bbox_tuple,
                             a=rndv_adj):
                return SPRTModel(EPSILON, c, a, bt)
            rndv_res = run_one_method(f"SPRT-RNDV_{city_key}", make_rndv_fb,
                                       trajs, bbox, N_REPS)
            city_result['SPRT_RNDV'] = rndv_res
            city_result['SPRT_RNDV_grid_info'] = {'n_cells': N_fb,
                                                   'fallback': True}

            results['cities'][city_key] = city_result
            continue

        city_result['osm_status'] = 'OK'
        city_result['osm_source'] = source_url
        city_result['osm_n_ways'] = len(ways)
        print(f"  Got {len(ways)} highway ways from {source_url}", flush=True)

        # ── SPRT Step 1: Geography-aware adaptive grid ──────────────────
        print(f"  [SPRT Step 1] Building geography-aware adaptive grid...",
              flush=True)
        sprt_centers, sprt_adj, sprt_grid_info = build_sprt_adaptive_grid(
            ways, bbox, base_grid=SPRT_BASE_GRID, beta=SPRT_BETA)
        n_sprt = len(sprt_centers)
        print(f"    Result: {n_sprt} cells, {sprt_grid_info['n_edges']} edges, "
              f"density={sprt_grid_info['density']:.4f}", flush=True)

        # ── RNDV Step 1: Voronoi partition from road density ────────────
        print(f"  [RNDV Step 1] Computing road density + selecting centers...",
              flush=True)
        density_raw, n_seg, total_km = compute_road_density_grid(ways, bbox)
        density_smooth = gaussian_filter(density_raw, sigma=GAUSSIAN_SIGMA)
        print(f"    Road density: {total_km:.1f} km, raw range "
              f"[{density_raw.min():.4f}, {density_raw.max():.4f}]",
              flush=True)

        rndv_centers = select_centers_rndv(density_smooth, bbox, K=K_VORONOI)
        n_rndv = len(rndv_centers)
        rndv_adj = build_delaunay_adjacency(rndv_centers)
        n_rndv_edges = int(rndv_adj.sum() - np.diag(rndv_adj).sum()) // 2
        max_possible = n_rndv * (n_rndv - 1) / 2 if n_rndv > 1 else 1
        print(f"    RNDV: {n_rndv} Voronoi cells, {n_rndv_edges} Delaunay "
              f"edges, connectivity={n_rndv_edges/max_possible:.4f}",
              flush=True)
        for i, c in enumerate(rndv_centers):
            print(f"      Center {i+1}: ({c[0]:.4f}, {c[1]:.4f})", flush=True)

        print(f"  SPRT centers (first 10 of {n_sprt}):", flush=True)
        for i in range(min(10, n_sprt)):
            print(f"    [{i+1}] ({sprt_centers[i][0]:.4f}, "
                  f"{sprt_centers[i][1]:.4f})", flush=True)

        city_result['SPRT_grid_info'] = sprt_grid_info
        city_result['SPRT_RNDV_grid_info'] = {
            'n_cells': n_rndv,
            'n_edges': n_rndv_edges,
            'connectivity': float(n_rndv_edges / max_possible),
            'K': K_VORONOI,
        }

        # ── Run SPRT (Steps 2-5) ────────────────────────────────────────
        print(f"\n  ── SPRT: Steps 2-5 (ε={EPSILON}, N={n_sprt}, "
              f"{N_REPS} reps, Laplace noise) ──", flush=True)
        def make_sprt(c=sprt_centers, bt=bbox_tuple, a=sprt_adj):
            return SPRTModel(EPSILON, c, a, bt)
        sprt_res = run_one_method(f"SPRT_{city_key}", make_sprt,
                                   trajs, bbox, N_REPS)
        city_result['SPRT'] = sprt_res
        if sprt_res['status'] == 'OK':
            print(f"  SPRT RESULT: JS={sprt_res['js_mean']:.6f} "
                  f"+/-{sprt_res['js_std']:.6f} "
                  f"TL1={sprt_res['trans_l1_mean']:.6f}", flush=True)

        # ── Run SPRT-RNDV (Steps 2-5 identical, only grid differs) ─────
        print(f"\n  ── SPRT-RNDV: Steps 2-5 (ε={EPSILON}, N={n_rndv}, "
              f"{N_REPS} reps, Laplace noise) ──", flush=True)
        def make_rndv(c=rndv_centers, bt=bbox_tuple, a=rndv_adj):
            return SPRTModel(EPSILON, c, a, bt)
        rndv_res = run_one_method(f"SPRT-RNDV_{city_key}", make_rndv,
                                   trajs, bbox, N_REPS)
        city_result['SPRT_RNDV'] = rndv_res
        if rndv_res['status'] == 'OK':
            print(f"  SPRT-RNDV RESULT: JS={rndv_res['js_mean']:.6f} "
                  f"+/-{rndv_res['js_std']:.6f} "
                  f"TL1={rndv_res['trans_l1_mean']:.6f}", flush=True)

        results['cities'][city_key] = city_result

    # ═════════════════════════════════════════════════════════════════════
    # PHASE 3: Summary tables
    # ═════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("COMPARISON TABLE: SPRT vs SPRT-RNDV (Laplace noise, ε=1.0)")
    print("=" * 80)

    header = (f"{'Method':<16} {'City':<22} {'N_cells':>8} "
              f"{'JS_mean':>10} {'TL1_mean':>10} "
              f"{'LenJSD':>10} {'DiamJSD':>10} {'DensARE':>10} {'TransARE':>10} {'Status':>8}")
    print(header)
    print("-" * 130)

    summary_rows = []
    for city_key, cr in results.get('cities', {}).items():
        for method_key in ['SPRT', 'SPRT_RNDV']:
            res = cr.get(method_key, {})
            grid_info = cr.get(f'{method_key}_grid_info', {})
            n_cells = grid_info.get('n_cells', '?')
            ok = res.get('status') == 'OK'
            js_m = f"{res.get('js_mean', 0):.6f}" if ok else 'N/A'
            tl1_m = f"{res.get('trans_l1_mean', 0):.6f}" if ok else 'N/A'
            len_jsd = f"{res.get('len_jsd_mean', 0):.6f}" if ok else 'N/A'
            diam_jsd = f"{res.get('diam_jsd_mean', 0):.6f}" if ok else 'N/A'
            dens_are = f"{res.get('dens_are_mean', 0):.6f}" if ok else 'N/A'
            trans_are = f"{res.get('trans_are_mean', 0):.6f}" if ok else 'N/A'
            st = res.get('status', '?')
            n_str = str(n_cells) if isinstance(n_cells, int) else str(n_cells)
            print(f"{method_key:<16} {city_key:<22} {n_str:>8} "
                  f"{js_m:>10} {tl1_m:>10} "
                  f"{len_jsd:>10} {diam_jsd:>10} {dens_are:>10} {trans_are:>10} "
                  f"{st:>8}")
            summary_rows.append({
                'method': method_key,
                'city': city_key,
                'label': cr.get('label', city_key),
                'n_cells': n_cells,
                'js_mean': res.get('js_mean'),
                'js_std': res.get('js_std'),
                'trans_l1_mean': res.get('trans_l1_mean'),
                'trans_l1_std': res.get('trans_l1_std'),
                'len_jsd_mean': res.get('len_jsd_mean'),
                'len_jsd_std': res.get('len_jsd_std'),
                'diam_jsd_mean': res.get('diam_jsd_mean'),
                'diam_jsd_std': res.get('diam_jsd_std'),
                'dens_are_mean': res.get('dens_are_mean'),
                'dens_are_std': res.get('dens_are_std'),
                'trans_are_mean': res.get('trans_are_mean'),
                'trans_are_std': res.get('trans_are_std'),
                'status': st,
            })

    # Per-city comparison
    print("\n" + "=" * 80)
    print("PER-CITY SPRT vs SPRT-RNDV COMPARISON")
    print("=" * 80)
    for city_key, cr in results.get('cities', {}).items():
        sprt = cr.get('SPRT', {})
        rndv = cr.get('SPRT_RNDV', {})
        if sprt.get('status') == 'OK' and rndv.get('status') == 'OK':
            js_diff = sprt['js_mean'] - rndv['js_mean']
            tl1_diff = sprt['trans_l1_mean'] - rndv['trans_l1_mean']
            better = 'SPRT' if js_diff < 0 else 'SPRT-RNDV'
            print(f"  {cr['label']}: JS diff={js_diff:+.6f} ({better} better), "
                  f"TL1 diff={tl1_diff:+.6f}")

    # Save results
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, 'results.json')
    os.makedirs(out_dir, exist_ok=True)

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    results['summary'] = summary_rows

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)

    print(f"\nResults saved to: {out_path}")
    return results


if __name__ == '__main__':
    main()

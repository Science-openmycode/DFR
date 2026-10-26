# Post-Audit revision — fixes F1, F2, F3
# F1: Added run_xxx_native() functions for all 4 papers
# F2: PrivTrace uses generate_2nd_order() (not downgraded to 1st-order)
# F3: Random evaluation subset + controlled RNG
# DP: Sensitivity notes for SPRT/PrivTrace using Δ=100 vs Δ=99
"""
Four-paper comparison runner — OSM Grid-Density vs paper-native discretization.
Integrates external centers into SPRT/PrivTrace/DPTraj-PM/DPStd real implementations.
"""
import numpy as np, time, gc
from collections import defaultdict
import sys, os

_EXP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_EXP_DIR, 'paper_comparison', 'final'))
try:
    from execution.evaluate import evaluate
except ImportError:
    from evaluate import evaluate

# Paper modules: try package path, fall back to flat import
try: from sprt.sprt_final import SPRTModel, build_sprt_adaptive_grid
except ImportError: from sprt_final import SPRTModel, build_sprt_adaptive_grid

try: from privtrace.privtrace_final import PrivTraceModel
except ImportError: from privtrace_final import PrivTraceModel

try: from dptrajpm.dptrajpm_final import DPTrajPM, DPTrajPMRNDV
except ImportError: from dptrajpm_final import DPTrajPM, DPTrajPMRNDV

try: from dpstd.dpstd_final import DPStdModel, DPStdRNDVModel
except ImportError: from dpstd_final import DPStdModel, DPStdRNDVModel

EPSILON = 1.0; M_MAX = 100; N_REPS = 10; SEED_BASE = 42


def build_delaunay_adjacency(centers):
    from scipy.spatial import Delaunay
    N = len(centers)
    adj = np.zeros((N, N), dtype=int)
    if N >= 4:
        tri = Delaunay(centers)
        for s in tri.simplices:
            for i in range(3):
                for j in range(i + 1, 3):
                    adj[s[i], s[j]] = adj[s[j], s[i]] = 1
    else:
        adj = np.ones((N, N), dtype=int) - np.eye(N, dtype=int)
    nbrs = adj.sum(1)
    for i in range(N):
        if nbrs[i] == 0:
            adj[i, i] = 1
    return adj


def bbox_tuple_to_dict(bbox_tup):
    return {'lat_min': bbox_tup[0], 'lat_max': bbox_tup[1],
            'lon_min': bbox_tup[2], 'lon_max': bbox_tup[3]}


def _bootstrap_ci(values, n_bootstrap=10000, ci=95):
    """Bootstrap percentile CI. Returns (low, high) tuple."""
    rng = np.random.default_rng(42)
    means = np.array([np.mean(rng.choice(values, size=len(values), replace=True))
                      for _ in range(n_bootstrap)])
    alpha = (100 - ci) / 2
    return np.percentile(means, [alpha, 100 - alpha])


def _run_with_seed(trajs, bbox_tup, n_gen, build_and_run):
    """Run a method's fit+generate, returning (means_dict, ci_dict).
    Sets np.random.seed for model reproducibility (controls Laplace/normal noise)."""
    metrics = defaultdict(list)
    for ri in range(N_REPS):
        seed = SEED_BASE + ri * 1000
        np.random.seed(seed)  # Controls model-side noise (Laplace/normal in fit/generate)
        rng = np.random.default_rng(seed)  # Controls evaluation-side randomness
        m = build_and_run(rng, trajs, bbox_tup, n_gen)
        for k, v in m.items():
            metrics[k].append(v)
        gc.collect()
    means = {k: float(np.mean(v)) for k, v in metrics.items()}
    cis = {}
    for k, v in metrics.items():
        lo, hi = _bootstrap_ci(np.array(v, dtype=np.float64))
        cis[f'{k}_ci95lo'] = float(lo)
        cis[f'{k}_ci95hi'] = float(hi)
    result = means.copy()
    result.update(cis)
    return result


# ==================== SPRT ====================

def _import_module(import_path):
    """Try import with package path, fall back to direct module name."""
    try:
        return __import__(import_path, fromlist=[''])
    except (ImportError, ModuleNotFoundError):
        module_name = import_path.split('.')[-1]
        return __import__(module_name, fromlist=[''])


def run_sprt_native(trajs, bbox_tup, osm_ways, n_gen=500):
    """SPRT original: build adaptive grid from OSM ways, use SPRTModel."""
    bd = bbox_tuple_to_dict(bbox_tup)
    paper_centers, paper_adj, _ = build_sprt_adaptive_grid(osm_ways, bd)
    def fn(rng, trajs, bbox_tup, n_gen):
        model = SPRTModel(EPSILON, paper_centers, paper_adj, bbox_tup)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), len(paper_centers)


def run_sprt_osm(trajs, bbox_tup, osm_centers, n_gen=500):
    """SPRT + OSM centers."""
    adj = build_delaunay_adjacency(osm_centers)
    def fn(rng, trajs, bbox_tup, n_gen):
        model = SPRTModel(EPSILON, osm_centers, adj, bbox_tup)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), len(osm_centers)


# ==================== PrivTrace ====================

def run_privtrace_native(trajs, n_gen=500):
    """PrivTrace original: adaptive grid [0.2, 0.4, 0.4], 2nd-order generation."""
    def fn(rng, trajs, bbox_tup, n_gen):
        model = PrivTraceModel(epsilon=EPSILON, budget_config=[0.2, 0.4, 0.4])
        model.fit(trajs)
        syn = model.generate_2nd_order(n_trajs=n_gen)  # F2 fix: use 2nd-order
        bd = model.bbox
        bt = (bd['lat_min'], bd['lat_max'], bd['lon_min'], bd['lon_max'])
        return evaluate(trajs, syn, bt, rng=rng)
    return _run_with_seed(trajs, (0, 1, 0, 1), n_gen, fn), None


def run_privtrace_osm(trajs, osm_centers, n_gen=500):
    """PrivTrace + OSM centers: full budget to 2nd-order synthesis."""
    osm_for_pt = [{'lat': float(c[0]), 'lon': float(c[1]), 'type': 'rndv'}
                  for c in osm_centers]
    def fn(rng, trajs, bbox_tup, n_gen):
        model = PrivTraceModel(epsilon=EPSILON, budget_config=[0, 0.5, 0.5],
                               rndv_centers=osm_for_pt)
        model.fit(trajs)
        syn = model.generate_2nd_order(n_trajs=n_gen)  # F2 fix
        bd = model.bbox
        bt = (bd['lat_min'], bd['lat_max'], bd['lon_min'], bd['lon_max'])
        return evaluate(trajs, syn, bt, rng=rng)
    return _run_with_seed(trajs, (0, 1, 0, 1), n_gen, fn), len(osm_centers)


def run_privtrace_osm_matched(trajs, osm_centers, n_gen=500):
    """E08: OSM + MATCHED synthesis budget (ε=0.8 synthesis = same as native's 0.4+0.4).
    Tests whether discretization alone wins without budget advantage."""
    osm_for_pt = [{'lat': float(c[0]), 'lon': float(c[1]), 'type': 'rndv'}
                  for c in osm_centers]
    def fn(rng, trajs, bbox_tup, n_gen):
        model = PrivTraceModel(epsilon=0.8, budget_config=[0, 0.5, 0.5],
                               rndv_centers=osm_for_pt)
        model.fit(trajs)
        syn = model.generate_2nd_order(n_trajs=n_gen)
        bd = model.bbox
        bt = (bd['lat_min'], bd['lat_max'], bd['lon_min'], bd['lon_max'])
        return evaluate(trajs, syn, bt, rng=rng)
    return _run_with_seed(trajs, (0, 1, 0, 1), n_gen, fn), len(osm_centers)


# ==================== DPTraj-PM ====================

def run_dptrajpm_native(trajs, bbox_tup, n_gen=500):
    """DPTraj-PM original: K=7 uniform grid, 2nd-order Markov, prefix tree."""
    bd = bbox_tuple_to_dict(bbox_tup)
    def fn(rng, trajs, bbox_tup, n_gen):
        model = DPTrajPM(epsilon=EPSILON, bbox=bd, K_cells=7, m=2)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), 49


def run_dptrajpm_osm(trajs, bbox_tup, osm_centers, n_gen=500):
    """DPTraj-PM + OSM centers."""
    bd = bbox_tuple_to_dict(bbox_tup)
    def fn(rng, trajs, bbox_tup, n_gen):
        model = DPTrajPMRNDV(epsilon=EPSILON, bbox=bd,
                             rndv_centers_arrays=osm_centers.copy(), m=2)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), len(osm_centers)


# ==================== DPStd ====================

def run_dpstd_native(trajs, bbox_tup, n_gen=500):
    """DPStd original: 3x3 adaptive grid (ε₁=0.1, ε₂=0.9)."""
    bd = bbox_tuple_to_dict(bbox_tup)
    def fn(rng, trajs, bbox_tup, n_gen):
        model = DPStdModel(epsilon=EPSILON, bbox_dict=bd)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), None


def run_dpstd_osm(trajs, bbox_tup, osm_centers, n_gen=500):
    """DPStd + OSM centers."""
    bd = bbox_tuple_to_dict(bbox_tup)
    osm_for_ds = [{'lat': float(c[0]), 'lon': float(c[1])}
                  for c in osm_centers]
    def fn(rng, trajs, bbox_tup, n_gen):
        model = DPStdRNDVModel(epsilon=EPSILON, rndv_centers=osm_for_ds,
                               bbox_dict=bd)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), len(osm_centers)


def run_dpstd_osm_matched(trajs, bbox_tup, osm_centers, n_gen=500):
    """E08: OSM + MATCHED stats budget (total ε=0.9, all to stats = same as native)."""
    bd = bbox_tuple_to_dict(bbox_tup)
    osm_for_ds = [{'lat': float(c[0]), 'lon': float(c[1])} for c in osm_centers]
    def fn(rng, trajs, bbox_tup, n_gen):
        model = DPStdRNDVModel(epsilon=0.9, rndv_centers=osm_for_ds, bbox_dict=bd)
        model.fit(trajs)
        syn = model.generate(n_trajs=n_gen)
        return evaluate(trajs, syn, bbox_tup, rng=rng)
    return _run_with_seed(trajs, bbox_tup, n_gen, fn), len(osm_centers)

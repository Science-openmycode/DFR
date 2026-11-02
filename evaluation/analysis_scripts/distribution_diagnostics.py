"""Shared count/OD distribution diagnostics; no predictive task or training."""
from __future__ import annotations
import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import spearmanr

BBOX = None  # Set explicitly by the coordinate evaluator configuration.

def cell_id(points: np.ndarray, grid: int) -> np.ndarray:
    lat_min, lat_max, lon_min, lon_max = BBOX
    y = np.floor((points[:, 0] - lat_min) / max(lat_max - lat_min, 1e-12) * grid).astype(int)
    x = np.floor((points[:, 1] - lon_min) / max(lon_max - lon_min, 1e-12) * grid).astype(int)
    y = np.clip(y, 0, grid - 1)
    x = np.clip(x, 0, grid - 1)
    return y * grid + x


def occupancy_counts(trajs: list[np.ndarray], grid: int) -> np.ndarray:
    counts = np.zeros(grid * grid, dtype=float)
    for traj in trajs:
        ids = np.unique(cell_id(np.asarray(traj, dtype=float), grid))
        counts[ids] += 1.0
    return counts


def js_counts(a: np.ndarray, b: np.ndarray) -> float:
    av = np.asarray(a, dtype=float).ravel()
    bv = np.asarray(b, dtype=float).ravel()
    if av.sum() <= 0 or bv.sum() <= 0:
        return 1.0
    return float(jensenshannon(av / av.sum(), bv / bv.sum()))


def make_range_queries(grid: int, n_queries: int = 256, seed: int = 20260704):
    rng = np.random.default_rng(seed + grid)
    queries = []
    for _ in range(n_queries):
        h = int(rng.integers(1, max(2, grid // 2 + 1)))
        w = int(rng.integers(1, max(2, grid // 2 + 1)))
        y0 = int(rng.integers(0, grid - h + 1))
        x0 = int(rng.integers(0, grid - w + 1))
        cells = [y * grid + x for y in range(y0, y0 + h) for x in range(x0, x0 + w)]
        queries.append(np.asarray(cells, dtype=int))
    return queries


def count_query_metrics(real: list[np.ndarray], syn: list[np.ndarray]) -> dict[str, float]:
    jsds = []
    smapes = []
    ares = []
    for grid in [8, 16, 32]:
        rc = occupancy_counts(real, grid)
        sc = occupancy_counts(syn, grid)
        jsds.append(js_counts(rc, sc))
        for cells in make_range_queries(grid):
            r = float(rc[cells].sum())
            s = float(sc[cells].sum())
            smapes.append(abs(s - r) / max(s + r, 1.0))
            if r >= 5:
                ares.append(abs(s - r) / r)
    return {
        "A1_count_jsd_mean": float(np.mean(jsds)),
        "A1_range_smape": float(np.mean(smapes)),
        "A1_range_are_nonzero": float(np.mean(ares)) if ares else math.nan,
    }


def od_counts(trajs: list[np.ndarray], grid: int = 8) -> np.ndarray:
    mat = np.zeros((grid * grid, grid * grid), dtype=float)
    for traj in trajs:
        arr = np.asarray(traj, dtype=float)
        if len(arr) < 2:
            continue
        o = int(cell_id(arr[:1], grid)[0])
        d = int(cell_id(arr[-1:], grid)[0])
        mat[o, d] += 1.0
    return mat


def ndcg_at_k(real_scores: np.ndarray, syn_scores: np.ndarray, k: int = 20) -> float:
    order = np.argsort(-syn_scores)[:k]
    gains = real_scores[order]
    discounts = 1.0 / np.log2(np.arange(2, len(order) + 2))
    dcg = float(np.sum(gains * discounts))
    ideal = np.sort(real_scores)[::-1][:k]
    idcg = float(np.sum(ideal * discounts[: len(ideal)]))
    return dcg / idcg if idcg > 0 else 0.0


def od_demand_metrics(real: list[np.ndarray], syn: list[np.ndarray]) -> dict[str, float]:
    ro = od_counts(real, 8).ravel()
    so = od_counts(syn, 8).ravel()
    rho = spearmanr(ro, so).statistic
    rho = 0.0 if not np.isfinite(rho) else float(rho)
    top_real = set(np.argsort(-ro)[:20].tolist())
    top_syn = set(np.argsort(-so)[:20].tolist())
    return {
        "OD_spearman": rho,
        "OD_top20_overlap": len(top_real & top_syn) / 20.0,
        "OD_ndcg20": ndcg_at_k(ro, so, 20),
        "OD_jsd": js_counts(ro, so),
    }

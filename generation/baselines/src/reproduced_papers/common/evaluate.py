# Fixed evaluate.py — Post-Audit Revision
# Fixes: ARE (100 fixed queries, no max(rc,1)), ReID (200 victims, full search, proper RNG),
#        random evaluation subset, deterministic RNG throughout.
"""
11-Metric evaluation framework for DP trajectory synthesis.

Metrics: global (JS, ARE, HQE, KT), trajectory (Trip/Len/Diam JSD),
semantic (F1, Pattern Error), security (ReID, Outlier Resilience).

All randomness controlled via explicit rng parameter.
"""
import numpy as np, math
from collections import defaultdict
from scipy.spatial.distance import jensenshannon
from scipy.stats import kendalltau


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dl, do = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dl / 2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(do / 2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_fixed_queries(bbox, n_queries=100):
    """Build deterministic fixed workload of range queries (grid-sampled)."""
    lat_min, lat_max, lon_min, lon_max = bbox
    ls = lat_max - lat_min
    ll = lon_max - lon_min
    queries = []
    grid = int(np.ceil(np.sqrt(n_queries)))
    # Fixed grid of query centers
    for i in range(grid):
        for j in range(grid):
            if len(queries) >= n_queries:
                break
            qlat = lat_min + (i + 0.5) * ls / grid
            qlon = lon_min + (j + 0.5) * ll / grid
            # Fixed query size: 3% of bbox half-width
            qs = min(ls, ll) * 0.05
            queries.append((qlat, qlon, qs))
        if len(queries) >= n_queries:
            break
    return queries


def _precompute_query_counts(trajectories, queries):
    """Precompute point counts per query (performance optimization)."""
    counts = np.zeros(len(queries), dtype=np.int64)
    for qi, (qlat, qlon, qs) in enumerate(queries):
        for t in trajectories:
            for p in t:
                if abs(p[0] - qlat) < qs and abs(p[1] - qlon) < qs:
                    counts[qi] += 1
    return counts


def evaluate(real_traj, syn_traj, bbox, rng=None, mgs=12,
             n_are_queries=100, n_reid_victims=200,
             eval_subset_size=500):
    """
    Evaluate all 11 utility metrics with controlled randomness.

    Args:
        real_traj: list of numpy arrays [N_i, 2]
        syn_traj: list of numpy arrays [N_j, 2]
        bbox: tuple (lat_min, lat_max, lon_min, lon_max)
        rng: numpy.random.Generator (deterministic if seeded)
        mgs: grid size for density computation
        n_are_queries: number of fixed-grid range queries
        n_reid_victims: number of re-identification attack victims
        eval_subset_size: random subsample of real trajectories for evaluation
    """
    if rng is None:
        rng = np.random.default_rng(42)
    lat_min, lat_max, lon_min, lon_max = bbox
    ls = max(lat_max - lat_min, 1e-10)
    ll = max(lon_max - lon_min, 1e-10)
    gs2 = 8

    # --- Random evaluation subset (FIX F3: non-random trajs[:500]) ---
    n_eval = min(eval_subset_size, len(real_traj))
    eval_indices = rng.choice(len(real_traj), size=n_eval, replace=False)
    eval_real = [real_traj[i] for i in eval_indices]

    def dh(t):
        h = np.zeros((mgs, mgs))
        for tr in t:
            for p in tr:
                r = min(int((p[0] - lat_min) / ls * mgs), mgs - 1)
                c = min(int((p[1] - lon_min) / ll * mgs), mgs - 1)
                h[r, c] += 1
        return h

    # 1. JS divergence
    rd = dh(eval_real)
    sd = dh(syn_traj)
    rdf = rd.flatten() / max(rd.sum(), 1)
    sdf = sd.flatten() / max(sd.sum(), 1)
    js_v = float(jensenshannon(rdf, sdf))

    # 2. ARE — FIXED: 100 grid-sampled queries, no max(rc,1) spike
    queries = _build_fixed_queries(bbox, n_are_queries)
    rc_counts = _precompute_query_counts(eval_real, queries)
    sc_counts = _precompute_query_counts(syn_traj, queries)
    are_vals = np.zeros(n_are_queries)
    for qi in range(n_are_queries):
        rc = rc_counts[qi]
        sc = sc_counts[qi]
        # Normalize: relative error averaged over all queries (0/0 = 0)
        if rc == 0 and sc == 0:
            are_vals[qi] = 0.0
        elif rc == 0:
            are_vals[qi] = 1.0  # false positives in empty regions
        else:
            are_vals[qi] = abs(rc - sc) / rc
    range_are = float(np.mean(are_vals))

    # 3. HQE
    top_n = 10
    r_top = set(np.argsort(rd.flatten())[-top_n:])
    s_top = set(np.argsort(sd.flatten())[-top_n:])
    hqe = 1.0 - len(r_top & s_top) / top_n

    # 4. Kendall tau
    r_rank = np.argsort(np.argsort(-rd.flatten()))
    s_rank = np.argsort(np.argsort(-sd.flatten()))
    kt, _ = kendalltau(r_rank, s_rank)
    kt_v = float(kt) if not np.isnan(kt) else 0.0

    # 5. Trip JSD
    def od(t):
        h = np.zeros((gs2 * gs2, gs2 * gs2))
        for tr in t:
            if len(tr) < 2:
                continue
            si = (min(int((tr[0][0] - lat_min) / ls * gs2), gs2 - 1) * gs2 +
                  min(int((tr[0][1] - lon_min) / ll * gs2), gs2 - 1))
            ei = (min(int((tr[-1][0] - lat_min) / ls * gs2), gs2 - 1) * gs2 +
                  min(int((tr[-1][1] - lon_min) / ll * gs2), gs2 - 1))
            h[si, ei] += 1
        return h.flatten()
    rod = od(eval_real)
    sod = od(syn_traj)
    trip_jsd = float(jensenshannon(
        rod / max(rod.sum(), 1), sod / max(sod.sum(), 1)))

    # 6-7. Length and diameter JSD
    rl = np.array([len(t) for t in eval_real])
    sl = np.array([len(t) for t in syn_traj])
    ml = max(rl.max(), sl.max())
    rb = np.bincount(rl, minlength=ml + 1)[2:].astype(float)
    sb = np.bincount(sl, minlength=ml + 1)[2:].astype(float)
    len_jsd = float(jensenshannon(
        rb / max(rb.sum(), 1), sb / max(sb.sum(), 1)))

    diam = lambda t: [haversine(tr[0][0], tr[0][1], tr[-1][0], tr[-1][1])
                      for tr in t if len(tr) >= 2]
    rdiam = np.array(diam(eval_real))
    sdiam = np.array(diam(syn_traj))
    mx_d = max(rdiam.max() if len(rdiam) > 0 else 10,
               sdiam.max() if len(sdiam) > 0 else 10)
    bins = np.linspace(0, mx_d, 20)
    rh = (np.histogram(rdiam, bins=bins)[0].astype(float)
          if len(rdiam) > 0 else np.ones(19))
    sh = (np.histogram(sdiam, bins=bins)[0].astype(float)
          if len(sdiam) > 0 else np.ones(19))
    diam_jsd = float(jensenshannon(
        rh / max(rh.sum(), 1), sh / max(sh.sum(), 1)))

    # 8-9. Pattern F1 and Pattern Error
    def top_od(t):
        pats = defaultdict(int)
        for tr in t:
            if len(tr) < 2:
                continue
            si = (min(int((tr[0][0] - lat_min) / ls * gs2), gs2 - 1) * gs2 +
                  min(int((tr[0][1] - lon_min) / ll * gs2), gs2 - 1))
            ei = (min(int((tr[-1][0] - lat_min) / ls * gs2), gs2 - 1) * gs2 +
                  min(int((tr[-1][1] - lon_min) / ll * gs2), gs2 - 1))
            pats[(si, ei)] += 1
        return set(sorted(pats.keys(), key=lambda x: pats[x], reverse=True)[:20]), pats
    rp, rp_c = top_od(eval_real)
    sp, sp_c = top_od(syn_traj)
    tp = len(rp & sp)
    prec = tp / max(len(sp), 1)
    rec = tp / max(len(rp), 1)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    ap = set(list(rp_c.keys()) + list(sp_c.keys()))
    pe = sum(
        abs(rp_c.get(p, 0) - sp_c.get(p, 0)) /
        max(rp_c.get(p, 0), sp_c.get(p, 0), 1)
        for p in ap
    ) / max(len(ap), 1)

    # 10. ReID — FIXED: 200 victims, search ALL synthetic, threshold ablation
    reid_victim_count = min(n_reid_victims, len(eval_real))
    victim_indices = rng.choice(len(eval_real), size=reid_victim_count, replace=False)
    # Pre-compute all synthetic trajectory lengths for fast comparison
    syn_lengths = np.array([len(t) for t in syn_traj])
    syn_starts = np.array([t[0] for t in syn_traj if len(t) >= 2])
    # For efficiency: only compare victim starts to synthetic starts first
    total_matched = 0
    thresholds_km = [0.1, 0.5, 1.0]
    matches_by_threshold = {t: 0 for t in thresholds_km}
    for vi in victim_indices:
        victim = eval_real[vi]
        if len(victim) < 4:
            total_matched += 1  # too short, conservatively count as matchable
            for tkm in thresholds_km:
                matches_by_threshold[tkm] += 1
            continue
        sub_len = max(2, len(victim) // 3)
        vsub = victim[:sub_len]
        vstart = victim[0]
        # Coarse filter: only compare to synthetic trajectories whose start is nearby
        nearby = np.where(np.linalg.norm(syn_starts - vstart, axis=1) < 2.0)[0]
        matched_any = False
        matched_at_threshold = {t: False for t in thresholds_km}
        for si in nearby:
            s = syn_traj[si]
            if len(s) < sub_len:
                continue
            ssub = s[:sub_len]
            avg_dist = np.mean([haversine(vsub[pi][0], vsub[pi][1],
                                           ssub[pi][0], ssub[pi][1])
                                for pi in range(sub_len)])
            for tkm in thresholds_km:
                if avg_dist < tkm:
                    matched_at_threshold[tkm] = True
            # (detection is per-victim: yes/no)
        if matched_at_threshold[thresholds_km[1]]:  # 0.5 km default
            total_matched += 1
        for tkm in thresholds_km:
            if matched_at_threshold[tkm]:
                matches_by_threshold[tkm] += 1
    reid = 1.0 - total_matched / reid_victim_count
    # Also store breakdown for diagnosis
    reid_breakdown = {f'reid_{int(t*1000)}m': 1.0 - matches_by_threshold[t] / reid_victim_count
                      for t in thresholds_km}

    # 11. Outlier resilience
    out_res = 1.0
    if len(rl) > 0 and len(rdiam) > 0:
        lq95 = np.percentile(rl, 95)
        dq95 = np.percentile(rdiam, 95)
        so_o = (sum(1 for l in sl if l > lq95 * 1.5) +
                sum(1 for d in sdiam if d > dq95 * 1.5))
        out_res = 1.0 - min(so_o / max(len(syn_traj), 1), 1.0)

    result = {
        'js': js_v, 'range_are': range_are, 'hqe': hqe,
        'kendall_tau': kt_v, 'trip_jsd': trip_jsd,
        'len_jsd': len_jsd, 'diam_jsd': diam_jsd,
        'f1': f1, 'pattern_err': pe,
        'reid': reid, 'outlier': out_res,
    }
    result.update(reid_breakdown)
    return result

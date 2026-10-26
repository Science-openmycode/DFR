"""Build controlled MTNet shadow corpora for conditional LiRA.

Each candidate is independently included/excluded from each shadow corpus.
All road-network files are public copies; only author-format route/time rows
are selected.  Candidate routes that collide in the base corpus are excluded
from the background so an inclusion flag has its intended meaning.
"""
from __future__ import annotations

import argparse, json, pickle, shutil
from pathlib import Path
import numpy as np


def key(route) -> tuple[int, ...]:
    return tuple(int(x) for x in route if int(x) > 0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-parent', type=Path, required=True)
    p.add_argument('--base-city', required=True)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--out-parent', type=Path, required=True)
    p.add_argument('--shadows', type=int, default=4)
    p.add_argument('--background-size', type=int, default=3000)
    p.add_argument('--inclusion-probability', type=float, default=.5)
    p.add_argument('--append-balanced', action='store_true',
                   help='Append four shadows whose flags make each existing candidate 4-in/4-out overall.')
    p.add_argument('--seed', type=int, default=20260720)
    a = p.parse_args()
    if not (0 < a.inclusion_probability < 1): p.error('inclusion probability must be in (0,1)')
    source = a.base_parent / a.base_city
    with (source / 'trajs_demo.csv').open(encoding='utf-8') as f: base_routes = [line.strip() for line in f if line.strip()]
    with (source / 'tstamps_demo.csv').open(encoding='utf-8') as f: base_times = [line.strip() for line in f if line.strip()]
    if len(base_routes) != len(base_times): raise RuntimeError('base route/time row counts differ')
    with a.candidates.open('rb') as f: records = pickle.load(f)['records']
    # A LiRA candidate must have a unique route representation in the base
    # member corpus; otherwise source-record membership is not identifiable.
    route_to_rows: dict[tuple[int, ...], list[int]] = {}
    for i, text in enumerate(base_routes): route_to_rows.setdefault(key(text.split()), []).append(i)
    usable = []
    for row in records:
        route_key = key(row['route'])
        rows = route_to_rows.get(route_key, [])
        if int(row['label']) == 1 and len(rows) != 1: continue
        if int(row['label']) == 0 and rows: continue
        usable.append(row)
    # L=100 FMM paths collapse many distinct GPS traces to identical road-edge
    # sequences.  Keep only identifiable records and allow a small pilot here;
    # the manifest makes the resulting sample size explicit so it cannot be
    # mistaken for the final large-scale audit.
    if min(sum(int(x['label']) == label for x in usable) for label in (0,1)) < 10:
        raise RuntimeError('insufficient uniquely mappable member/nonmember candidates even for a LiRA pilot')
    candidate_keys = {key(row['route']) for row in usable}
    background = [i for i, route in enumerate(base_routes) if key(route.split()) not in candidate_keys]
    if a.background_size > len(background): p.error('background-size exceeds noncandidate base rows')
    a.out_parent.mkdir(parents=True, exist_ok=True)
    manifest_path = a.out_parent / 'shadow_manifest.json'
    prior = None
    if a.append_balanced:
        if a.shadows != 4:
            p.error('--append-balanced requires --shadows 4')
        if not manifest_path.exists():
            p.error('--append-balanced requires an existing shadow_manifest.json')
        prior = json.loads(manifest_path.read_text(encoding='utf-8'))
        old_membership = prior.get('candidate_membership', {})
        if set(old_membership) != {str(row['source_index']) for row in usable}:
            raise RuntimeError('existing manifest and recomputed identifiable candidates differ')
        if any(len(bits) != 4 for bits in old_membership.values()):
            raise RuntimeError('existing manifest must contain exactly four shadow flags per candidate')
        all_flags = dict(prior['shadows'])
        start_shadow = 4
    else:
        old_membership = None
        all_flags = {}
        start_shadow = 0
    balanced_extension = None
    if old_membership is not None:
        balanced_extension = {}
        assignment_rng = np.random.default_rng(a.seed + 1000)
        for row in usable:
            needed = 4 - sum(bool(x) for x in old_membership[str(row['source_index'])])
            pattern = np.array([True] * needed + [False] * (4 - needed), dtype=bool)
            assignment_rng.shuffle(pattern)
            balanced_extension[str(row['source_index'])] = pattern.tolist()
    for shadow in range(start_shadow, start_shadow + a.shadows):
        rng = np.random.default_rng(a.seed + shadow)
        if old_membership is None:
            flags = rng.random(len(usable)) < a.inclusion_probability
        else:
            # Complement the first four random assignments.  Each candidate
            # then has four in and four out shadow observations, eliminating
            # the arbitrary 2-in/2-out attrition of the pilot design.
            flags = np.asarray([
                balanced_extension[str(row['source_index'])][shadow - start_shadow]
                for row in usable
            ], dtype=bool)
        selected = rng.choice(background, a.background_size, replace=False).tolist()
        rows = [(base_routes[i], base_times[i]) for i in selected]
        for include, record in zip(flags, usable):
            if not include: continue
            route_key = key(record['route'])
            if int(record['label']) == 1:
                index = route_to_rows[route_key][0]
                rows.append((base_routes[index], base_times[index]))
            else:
                route = list(route_key) + [0]
                count = len(route)
                start = float(record['departure'])
                duration = max(1.0, float(record['duration_seconds']))
                times = [start] + [start + duration * i / max(1, count - 1) for i in range(1, count)]
                rows.append((' '.join(map(str, route)), ' '.join(f'{x:.3f}' for x in times)))
        city = f'{a.base_city}_lira_shadow_{shadow:02d}'
        target = a.out_parent / city; target.mkdir(parents=True, exist_ok=True)
        for name in ('edge_adj.txt', 'edge_property.txt', 'temporal_32.emb'):
            shutil.copy2(source / name, target / name)
        with (target / 'trajs_demo.csv').open('w', encoding='utf-8') as fr, (target / 'tstamps_demo.csv').open('w', encoding='utf-8') as ft:
            for route, times in rows: fr.write(route + '\n'); ft.write(times + '\n')
        all_flags[str(shadow)] = {'city': city, 'records': len(rows), 'candidate_inclusion': {str(row['source_index']): bool(flag) for row, flag in zip(usable, flags)}}
    # Transpose into the format consumed by run_mtnet_conditional_lira.py.
    total_shadows = start_shadow + a.shadows
    membership = {str(row['source_index']): [all_flags[str(s)]['candidate_inclusion'][str(row['source_index'])] for s in range(total_shadows)] for row in usable}
    manifest_path.write_text(json.dumps({'base_city': a.base_city, 'shadows': all_flags, 'usable_candidates': len(usable), 'candidate_membership': membership, 'seed': a.seed, 'background_size': a.background_size, 'inclusion_probability': a.inclusion_probability}, indent=2), encoding='utf-8')
    print(json.dumps({'shadows': total_shadows, 'added_shadows': a.shadows, 'usable_candidates': len(usable), 'base_rows': len(base_routes), 'background_rows': len(background)}, indent=2), flush=True)


if __name__ == '__main__': main()

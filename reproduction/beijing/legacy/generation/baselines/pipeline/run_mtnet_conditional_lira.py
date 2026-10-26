"""Conditional LiRA for an autoregressive MTNet trajectory model.

The attack conditions on exactly the values accepted by the loaded MTNet
implementation (origin road edge and departure time), then uses teacher-forced
route likelihood.  A shadow-membership JSON maps each candidate source index to
the Boolean inclusion indicators of the correspondingly ordered shadow models.
"""
from __future__ import annotations

import argparse, csv, json, math, os, pickle, random, sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score


def normal_logpdf(value: float, samples: np.ndarray) -> float:
    # A small variance floor keeps a single unusually stable shadow score from
    # manufacturing infinite evidence.
    mean = float(samples.mean())
    variance = max(float(samples.var(ddof=1)), 1e-4)
    return -0.5 * (math.log(2.0 * math.pi * variance) + (value - mean) ** 2 / variance)


def bootstrap(scores: np.ndarray, labels: np.ndarray, seed: int, rounds: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    pos, neg = np.flatnonzero(labels == 1), np.flatnonzero(labels == 0)
    values = []
    for _ in range(rounds):
        ix = np.r_[rng.choice(pos, len(pos), replace=True), rng.choice(neg, len(neg), replace=True)]
        values.append(float(roc_auc_score(labels[ix], scores[ix])))
    return float(np.quantile(values, .025)), float(np.quantile(values, .975))


def tpr_at_fpr(scores: np.ndarray, labels: np.ndarray, fpr: float) -> tuple[float, float]:
    negatives = np.sort(scores[labels == 0])[::-1]
    rank = max(1, int(math.ceil(fpr * len(negatives))))
    threshold = float(negatives[rank - 1])
    predicted = scores >= threshold
    return float(predicted[labels == 0].mean()), float(predicted[labels == 1].mean())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--mtnet-root', type=Path, required=True)
    p.add_argument('--data-parent', type=Path, required=True)
    p.add_argument('--city', required=True)
    p.add_argument('--target-model', type=Path, required=True)
    p.add_argument('--shadow-model', type=Path, action='append', required=True)
    p.add_argument('--shadow-membership', type=Path, required=True)
    p.add_argument('--max-route-edges', type=int, default=100)
    p.add_argument('--max-per-class', type=int, default=100)
    p.add_argument('--mc-draws', type=int, default=8)
    p.add_argument('--bootstrap', type=int, default=2000)
    p.add_argument('--seed', type=int, default=20260720)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    # The official MTNet import changes the process working directory.  Resolve
    # all release-local outputs before that import so audit artifacts do not
    # silently land inside the upstream source tree.
    a.out = a.out.resolve()
    if len(a.shadow_model) < 4:
        p.error('LiRA requires at least four shadow models')
    membership_payload = json.loads(a.shadow_membership.read_text(encoding='utf-8'))
    membership = membership_payload.get('candidate_membership', membership_payload)
    with a.candidates.open('rb') as handle:
        all_records = pickle.load(handle)['records']
    rng = np.random.default_rng(a.seed)
    chosen = []
    for label in (0, 1):
        rows = [row for row in all_records if int(row['label']) == label and str(row['source_index']) in membership]
        chosen.extend(rows[i] for i in rng.choice(len(rows), min(len(rows), a.max_per_class), replace=False))
    rng.shuffle(chosen)

    root = a.mtnet_root.resolve(); os.chdir(root); sys.path.insert(0, str(root))
    import torch
    from util import config
    import mtnet
    config.DATA_BASE = str(a.data_parent.resolve()) + os.sep
    config.CITY = a.city; config.TRAJ_FIX_LEN = a.max_route_edges + 1
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(a.seed)

    def load(path: Path):
        model = mtnet.Model()
        state = torch.load(path.resolve(), map_location=config.device)
        model.load_state_dict(state['state_dict']); model.eval()
        official = model.step
        def compatible(xt, slots, hs, cs):
            return official(xt, slots.long(), hs, cs)
        model.step = compatible
        return model

    models = [load(a.target_model)] + [load(path) for path in a.shadow_model]
    lengths = [0.0]
    with (a.data_parent / a.city / 'edge_property.txt').open(encoding='utf-8') as handle:
        for line in handle:
            lengths.append(float(line.split(',', 4)[1]))

    def likelihood(model, item: dict) -> float:
        route = [int(x) for x in item['route']][:a.max_route_edges]
        valid = len(route) - 1
        x = route + [0] * (a.max_route_edges - len(route))
        y = route[1:] + [0] * (a.max_route_edges - len(route) + 1)
        weights = np.maximum(np.asarray([lengths[e] if e < len(lengths) else 1.0 for e in route]), 1.0)
        elapsed = np.r_[0.0, np.cumsum(weights[:-1]) / weights.sum() * float(item['duration_seconds'])]
        start = (float(item['departure']) + 8 * 3600) % config.T_LOOP
        slots = (start + np.r_[elapsed, np.zeros(a.max_route_edges - len(route))]) % config.T_LOOP
        xt = torch.tensor([x], dtype=torch.long, device=config.device)
        dt = torch.tensor([slots / config.TRANGE_BASE], dtype=torch.float32, device=config.device)
        yt = torch.tensor(y[:valid], dtype=torch.long, device=config.device)
        values = []
        with torch.no_grad():
            for _ in range(a.mc_draws):
                logp, _ = model(xt, dt)
                logp = logp.view(1, a.max_route_edges, -1)[0, :valid]
                adj = model.adj[xt[0, :valid]]
                target_column = (adj == yt[:, None]).float().argmax(dim=1)
                values.append(float(logp[torch.arange(valid, device=config.device), target_column].mean().item()))
        return float(np.mean(values))

    scores, labels, rows = [], [], []
    for i, item in enumerate(chosen, start=1):
        values = np.asarray([likelihood(model, item) for model in models], dtype=float)
        indicators = np.asarray(membership[str(item['source_index'])], dtype=bool)
        if len(indicators) != len(a.shadow_model):
            raise ValueError('shadow-membership indicator length differs from --shadow-model count')
        in_scores, out_scores = values[1:][indicators], values[1:][~indicators]
        if len(in_scores) < 2 or len(out_scores) < 2:
            continue
        score = normal_logpdf(values[0], in_scores) - normal_logpdf(values[0], out_scores)
        scores.append(score); labels.append(int(item['label']))
        rows.append({'source_index': item['source_index'], 'label': int(item['label']), 'target_loglik': values[0],
                     'shadow_in_mean': float(in_scores.mean()), 'shadow_out_mean': float(out_scores.mean()),
                     'lira_score': score, 'n_shadow_in': len(in_scores), 'n_shadow_out': len(out_scores)})
        print(f'[conditional LiRA] scored {i}/{len(chosen)}', flush=True)
    scores, labels = np.asarray(scores), np.asarray(labels)
    if len(np.unique(labels)) != 2:
        raise RuntimeError('no balanced candidates remained after shadow inclusion filtering')
    low, high = bootstrap(scores, labels, a.seed, a.bootstrap)
    fpr01, tpr01 = tpr_at_fpr(scores, labels, .001)
    fpr1, tpr1 = tpr_at_fpr(scores, labels, .01)
    summary = {'attack': 'conditional_LiRA_teacher_forced_route_likelihood', 'auc': float(roc_auc_score(labels, scores)),
               'auc_bootstrap95_low': low, 'auc_bootstrap95_high': high,
               'tpr_at_0.1pct_fpr': tpr01, 'realized_fpr_at_0.1pct': fpr01,
               'tpr_at_1pct_fpr': tpr1, 'realized_fpr_at_1pct': fpr1,
               'members': int((labels == 1).sum()), 'nonmembers': int((labels == 0).sum()),
               'shadow_models': len(a.shadow_model), 'mc_draws': a.mc_draws}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix('.json').write_text(json.dumps({'threat_model': 'white-box logits; known route, origin edge, and departure time; shadow-calibrated likelihood ratio', 'result': summary, 'rows': rows}, indent=2), encoding='utf-8')
    with a.out.with_suffix('.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
